import json, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import yfinance as yf
import joblib

APP=Path('/home/liubaining/AI-Option-Trader'); OUT=APP/'models/v32'; LOG=APP/'logs/v32'
LOG.mkdir(parents=True,exist_ok=True)
cfg=json.loads((OUT/'regime_config.json').read_text()); features=cfg['features']; BASE=cfg['base_states']; mapping={int(k):v for k,v in cfg['raw_to_semantic'].items()}
scaler=joblib.load(OUT/'regime_scaler.joblib'); gmm=joblib.load(OUT/'regime_gmm.joblib'); trans=np.load(OUT/'transition_matrix.npy')
TICKERS=['TSLA','AAPL','NVDA','MSFT','AMZN','META','GOOGL','AMD']

def clean(h):
    h=h.copy(); h.index=pd.to_datetime(h.index).tz_localize(None).normalize(); return h
raw={s:clean(yf.Ticker(s).history(period='3y',auto_adjust=False)) for s in ['SPY','QQQ','^VIX']+TICKERS}
spy,qqq,vix=raw['SPY'],raw['QQQ'],raw['^VIX']; idx=spy.index.intersection(qqq.index).intersection(vix.index)
m=pd.DataFrame(index=idx)
m['spy_r5']=spy.Close.reindex(idx).pct_change(5); m['spy_r20']=spy.Close.reindex(idx).pct_change(20); m['spy_r60']=spy.Close.reindex(idx).pct_change(60)
m['qqq_r5']=qqq.Close.reindex(idx).pct_change(5); m['qqq_r20']=qqq.Close.reindex(idx).pct_change(20); m['qqq_r60']=qqq.Close.reindex(idx).pct_change(60)
m['spy_t20']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(20).mean()-1; m['spy_t50']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(50).mean()-1; m['spy_t200']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(200).mean()-1
m['qqq_t20']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(20).mean()-1; m['qqq_t50']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(50).mean()-1; m['qqq_t200']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(200).mean()-1
sr=spy.Close.reindex(idx).pct_change(); m['rv20']=sr.rolling(20).std()*np.sqrt(252); m['rv60']=sr.rolling(60).std()*np.sqrt(252); m['vol_ratio']=m.rv20/m.rv60.replace(0,np.nan)
m['vix_n']=(vix.Close.reindex(idx)-20)/20; m['vix_d5']=vix.Close.reindex(idx).pct_change(5); m['vix_d20']=vix.Close.reindex(idx).pct_change(20)
rets=pd.DataFrame({t:raw[t].Close.reindex(idx).pct_change() for t in TICKERS}); corr=[]
for i in range(len(rets)):
    if i<20: corr.append(np.nan); continue
    c=rets.iloc[i-19:i+1].corr().to_numpy(); vals=c[np.triu_indices_from(c,1)]; corr.append(float(np.nanmean(vals)))
m['corr20']=corr; m=m.replace([np.inf,-np.inf],np.nan).dropna().copy()
Z=scaler.transform(m[features]); emit=gmm.predict_proba(Z); filt=np.zeros_like(emit); filt[0]=emit[0]/emit[0].sum()
for i in range(1,len(m)):
    prior=filt[i-1]@trans; post=emit[i]*prior; filt[i]=post/max(post.sum(),1e-12)
sem=np.zeros((len(m),len(BASE)))
for k,name in mapping.items(): sem[:,BASE.index(name)]=filt[:,k]
ent=-np.sum(np.clip(sem,1e-12,1)*np.log(np.clip(sem,1e-12,1)),axis=1)/math.log(len(BASE))
zdf=pd.DataFrame(Z,index=m.index); jump=(zdf-zdf.shift(5)).pow(2).mean(axis=1).pow(.5).fillna(0).to_numpy(); cp=1/(1+np.exp(-1.6*(jump-1.45))); transition=np.clip(.68*cp+.32*ent,0,1)
market_date=str(m.index[-1].date()); p={s:float(sem[-1,BASE.index(s)]) for s in BASE}; dominant=max(p,key=p.get); uncertainty=float(ent[-1]); change=float(cp[-1]); trans_p=float(transition[-1])
mem_path=LOG/'regime_memory.json'
if mem_path.exists(): mem=json.loads(mem_path.read_text())
else: mem={'stable_regime':dominant,'pending_regime':None,'pending_count':0,'last_market_date':None}
new_day=mem.get('last_market_date')!=market_date; stable=mem.get('stable_regime',dominant)
if new_day:
    if p.get('STRESS',0)>=.85:
        stable='STRESS'; mem['pending_regime']=None; mem['pending_count']=0
    elif dominant==stable:
        mem['pending_regime']=None; mem['pending_count']=0
    elif p[dominant]>=.65:
        if mem.get('pending_regime')==dominant: mem['pending_count']=int(mem.get('pending_count',0))+1
        else: mem['pending_regime']=dominant; mem['pending_count']=1
        if mem['pending_count']>=3:
            stable=dominant; mem['pending_regime']=None; mem['pending_count']=0
    mem['stable_regime']=stable; mem['last_market_date']=market_date
mem_path.write_text(json.dumps(mem,indent=2))
display='TRANSITION' if (trans_p>=.55 or uncertainty>=.65) else stable
v31_context={}
v31=APP/'logs/v31/forward_state.json'
if v31.exists():
    try:
        q=json.loads(v31.read_text()); v31_context={'v31_market_date':q.get('market_date'),'v31_shadow_tickers':[x.get('ticker') for x in q.get('signals',[])]}
    except Exception: pass
payload={'run_at_utc':datetime.now(timezone.utc).isoformat(),'market_date':market_date,'display_regime':display,'stable_regime':stable,'dominant_instantaneous':dominant,'regime_probabilities':p,'change_probability':change,'transition_probability':trans_p,'uncertainty':uncertainty,'pending_regime':mem.get('pending_regime'),'pending_count':mem.get('pending_count',0),'mode':'FORWARD_SHADOW_OBSERVER','changes_trade_decisions':False,'broker_orders_enabled':False,**v31_context}
with (LOG/'regime_forward.jsonl').open('a') as fh: fh.write(json.dumps(payload)+'\n')
(LOG/'regime_state.json').write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))
