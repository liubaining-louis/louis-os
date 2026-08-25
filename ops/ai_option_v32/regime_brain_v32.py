import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture

APP=Path('/home/liubaining/AI-Option-Trader')
OUT=APP/'models/v32'; DATA=APP/'data/v32'; LOG=APP/'logs/v32'
for p in (OUT,DATA,LOG): p.mkdir(parents=True,exist_ok=True)
TICKERS=['TSLA','AAPL','NVDA','MSFT','AMZN','META','GOOGL','AMD']
BASE=['RISK_ON','SIDEWAYS','RISK_OFF','STRESS']

def clean(h):
    h=h.copy(); h.index=pd.to_datetime(h.index).tz_localize(None).normalize(); return h

raw={s:clean(yf.Ticker(s).history(period='8y',auto_adjust=False)) for s in ['SPY','QQQ','^VIX']+TICKERS}
for s,h in raw.items():
    if h is None or len(h)<1200: raise RuntimeError(f'{s} insufficient history')
spy,qqq,vix=raw['SPY'],raw['QQQ'],raw['^VIX']
idx=spy.index.intersection(qqq.index).intersection(vix.index)
m=pd.DataFrame(index=idx)
m['spy_r5']=spy.Close.reindex(idx).pct_change(5); m['spy_r20']=spy.Close.reindex(idx).pct_change(20); m['spy_r60']=spy.Close.reindex(idx).pct_change(60)
m['qqq_r5']=qqq.Close.reindex(idx).pct_change(5); m['qqq_r20']=qqq.Close.reindex(idx).pct_change(20); m['qqq_r60']=qqq.Close.reindex(idx).pct_change(60)
m['spy_t20']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(20).mean()-1; m['spy_t50']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(50).mean()-1; m['spy_t200']=spy.Close.reindex(idx)/spy.Close.reindex(idx).rolling(200).mean()-1
m['qqq_t20']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(20).mean()-1; m['qqq_t50']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(50).mean()-1; m['qqq_t200']=qqq.Close.reindex(idx)/qqq.Close.reindex(idx).rolling(200).mean()-1
sr=spy.Close.reindex(idx).pct_change(); m['rv20']=sr.rolling(20).std()*np.sqrt(252); m['rv60']=sr.rolling(60).std()*np.sqrt(252); m['vol_ratio']=m.rv20/m.rv60.replace(0,np.nan)
m['vix_n']=(vix.Close.reindex(idx)-20)/20; m['vix_d5']=vix.Close.reindex(idx).pct_change(5); m['vix_d20']=vix.Close.reindex(idx).pct_change(20)
rets=pd.DataFrame({t:raw[t].Close.reindex(idx).pct_change() for t in TICKERS})
corr=[]
for i in range(len(rets)):
    if i<20: corr.append(np.nan); continue
    c=rets.iloc[i-19:i+1].corr().to_numpy(); vals=c[np.triu_indices_from(c,1)]; corr.append(float(np.nanmean(vals)))
m['corr20']=corr
features=list(m.columns); m=m.replace([np.inf,-np.inf],np.nan).dropna().copy()
cut=m.index[int(len(m)*.72)]
scaler=StandardScaler().fit(m.loc[m.index<cut,features]); Z=scaler.transform(m[features]); train=m.index<cut
gmm=GaussianMixture(n_components=4,covariance_type='full',reg_covar=1e-5,n_init=8,random_state=17).fit(Z[train])
emit=gmm.predict_proba(Z); hard=np.argmax(emit,axis=1)
trans=np.ones((4,4),float); ix=np.where(train)[0]
for a,b in zip(hard[ix[:-1]],hard[ix[1:]]): trans[a,b]+=1
trans/=trans.sum(axis=1,keepdims=True)
filt=np.zeros_like(emit); filt[0]=emit[0]/emit[0].sum()
for i in range(1,len(m)):
    prior=filt[i-1]@trans; post=emit[i]*prior; filt[i]=post/max(post.sum(),1e-12)
# Semantic names are derived only from the frozen training segment.
stats=[]
for k in range(4):
    q=m.iloc[np.where((hard==k)&train)[0]]
    stats.append({'k':k,'r20':float(q.spy_r20.mean()),'r60':float(q.spy_r60.mean()),'trend':float((q.spy_t50+q.qqq_t50).mean()),'vix':float(q.vix_n.mean()),'rv':float(q.rv20.mean())})
stress=max(stats,key=lambda x:x['vix']+1.5*x['rv']-.5*x['r20'])['k']
rem=[x for x in stats if x['k']!=stress]
risk_on=max(rem,key=lambda x:x['r20']+.7*x['r60']+x['trend']-.25*x['vix'])['k']
rem=[x for x in rem if x['k']!=risk_on]
sideways=min(rem,key=lambda x:abs(x['r20'])+.7*abs(x['r60'])+abs(x['trend'])+.25*x['rv'])['k']
risk_off=[x['k'] for x in rem if x['k']!=sideways][0]
map_raw={risk_on:'RISK_ON',sideways:'SIDEWAYS',risk_off:'RISK_OFF',stress:'STRESS'}
sem=np.zeros((len(m),4))
for k,name in map_raw.items(): sem[:,BASE.index(name)]=filt[:,k]
ent=-np.sum(np.clip(sem,1e-12,1)*np.log(np.clip(sem,1e-12,1)),axis=1)/math.log(4)
zdf=pd.DataFrame(Z,index=m.index); jump=(zdf-zdf.shift(5)).pow(2).mean(axis=1).pow(.5).fillna(0).to_numpy(); cp=1/(1+np.exp(-1.6*(jump-1.45)))
transition=np.clip(.68*cp+.32*ent,0,1)
for j,s in enumerate(BASE): m['p_'+s.lower()]=sem[:,j]
m['uncertainty']=ent; m['change_probability']=cp; m['transition_probability']=transition; m['dominant']=[BASE[i] for i in np.argmax(sem,axis=1)]
joblib.dump(scaler,OUT/'regime_scaler.joblib'); joblib.dump(gmm,OUT/'regime_gmm.joblib'); np.save(OUT/'transition_matrix.npy',trans)
meta={'version':'v3.2-regime-observer','features':features,'base_states':BASE,'raw_to_semantic':{str(k):v for k,v in map_raw.items()},'cluster_stats_training_only':stats,'fit_cutoff_date':str(pd.Timestamp(cut).date()),'semantic_mapping_fit_training_only':True,'release_status':'SHADOW_ONLY','changes_trade_decisions':False,'broker_orders_enabled':False}
(OUT/'regime_config.json').write_text(json.dumps(meta,indent=2)); m.to_csv(DATA/'regime_history.csv')
last=m.iloc[-1]
payload={'market_date':str(m.index[-1].date()),'regime_probabilities':{s:float(last['p_'+s.lower()]) for s in BASE},'dominant':str(last.dominant),'change_probability':float(last.change_probability),'transition_probability':float(last.transition_probability),'uncertainty':float(last.uncertainty),'mode':'SHADOW_ONLY','changes_trade_decisions':False,'broker_orders_enabled':False}
(LOG/'regime_state.json').write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))
