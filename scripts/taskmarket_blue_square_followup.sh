#!/usr/bin/env bash
set -euo pipefail
ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
TASK='0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
SUBMISSION='99cba5cc-7c8a-4fd2-97ea-492df2ef1eb3'
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
run_tm(){ timeout --signal=TERM --kill-after=5s 60s npx -y @lucid-agents/taskmarket "$@"; }
run_tm task get "$TASK" >"$TMP/task.json" 2>"$TMP/task.err"
run_tm task submissions "$TASK" >"$TMP/submissions.json" 2>"$TMP/submissions.err"
run_tm wallet balance >"$TMP/balance.json" 2>"$TMP/balance.err"
python3 - "$TMP/task.json" "$TMP/submissions.json" "$TMP/balance.json" "$TASK" "$SUBMISSION" <<'PY'
import json,sys,datetime
pt,ps,pb,task_id,submission_id=sys.argv[1:]
def load(p):
    d=json.load(open(p)); return d.get('data',d) if isinstance(d,dict) else d
t=load(pt); s=load(ps); b=load(pb)
if isinstance(s,dict): items=s.get('submissions') or s.get('items') or s.get('results') or []
elif isinstance(s,list): items=s
else: items=[]
wallet=str(b.get('address') or '') if isinstance(b,dict) else ''
own=None
for x in items:
    if not isinstance(x,dict): continue
    if str(x.get('id') or '')==submission_id or (wallet and str(x.get('workerAddress') or x.get('worker_address') or '').lower()==wallet.lower()):
        own=x; break
reward=t.get('reward') or t.get('rewardUsdc') or t.get('reward_usdc') if isinstance(t,dict) else None
try:
    rv=float(reward); reward_usdc=rv/1_000_000 if rv>1000 else rv
except: reward_usdc=None
status=str(t.get('status') or '').lower() if isinstance(t,dict) else 'unknown'
winner=None
if isinstance(t,dict):
    for k in ('winner','winnerAddress','winner_address','acceptedWorker','accepted_worker','selectedWorker','selected_worker'):
        if t.get(k): winner=str(t.get(k)); break
own_status=(own.get('status') if isinstance(own,dict) else None)
rejected=(own.get('rejectedAt') or own.get('rejected_at') if isinstance(own,dict) else None)
try: balance=float(b.get('balanceUsdc') or 0) if isinstance(b,dict) else 0.0
except: balance=0.0
selection_signal=(winner and wallet and winner.lower()==wallet.lower()) or str(own_status or '').lower() in {'accepted','winner','won','completed','paid'}
payout_candidate=bool(balance>0 and (selection_signal or status in {'completed','settled','paid'}))
out={
 'platform':'taskmarket','task_id':task_id,'submission_id':submission_id,'worker_wallet':wallet,
 'task_status':status,'task_reward_usdc':reward_usdc,
 'task_expiry':(t.get('expiryTime') or t.get('expiry_time') or t.get('expiry') if isinstance(t,dict) else None),
 'own_submission_found':bool(own),'own_submission_status':own_status,'own_submission_rejected_at':rejected,
 'task_winner':winner,'wallet_balance_usdc':balance,'payout_evidence_candidate':payout_candidate,
 'checked_at':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
 'monitoring_mode':'read_only','revenue_policy':'Do not attribute revenue until selection/payout is independently verified.'
}
print(json.dumps(out,ensure_ascii=False,indent=2))
PY
