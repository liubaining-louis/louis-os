#!/usr/bin/env bash
set -euo pipefail
ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
OUT='/var/lib/louis-os/results/taskmarket-top-probe'
mkdir -p "$OUT"
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'

run_tm() {
  timeout --signal=TERM --kill-after=5s 60s npx -y @lucid-agents/taskmarket "$@"
}

TASKS=(
  '0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
  '0x8e416ba0f3e473d2dddc7f7afc03ca35ab12b95972818808e9eff0d1e98e31fb'
  '0x21cc30011dddb8c7a5e91b4c70c140defab447507169513745d0389572255a42'
  '0xfb182f610d57a6c056a8cfd1c9b691a0869c1e0d67c041ac27ed9f42a9c732a1'
)

for task in "${TASKS[@]}"; do
  safe="${task:2:12}"
  echo "=== TASK $task ==="
  set +e
  run_tm task get "$task" >"$OUT/$safe-detail.json" 2>"$OUT/$safe-detail.err"
  get_rc=$?
  run_tm task submissions "$task" >"$OUT/$safe-subs.json" 2>"$OUT/$safe-subs.err"
  sub_rc=$?
  set -e
  echo "GET_RC=$get_rc SUBMISSIONS_RC=$sub_rc"
  python3 - "$OUT/$safe-detail.json" "$OUT/$safe-subs.json" <<'PY'
import json,sys
p1,p2=sys.argv[1:]
def load(path):
    try:return json.load(open(path))
    except:return None
def data(x): return x.get('data',x) if isinstance(x,dict) else x
d=data(load(p1)); s=data(load(p2))
if isinstance(d,dict):
    reward=d.get('reward') or d.get('rewardUsdc') or d.get('reward_usdc')
    try: reward_usdc=float(reward)/1_000_000 if float(reward)>1000 else float(reward)
    except: reward_usdc=None
    print('STATUS='+str(d.get('status')))
    print('MODE='+str(d.get('mode')))
    print('REWARD_USDC='+str(reward_usdc))
    print('EXPIRY='+str(d.get('expiryTime') or d.get('expiry_time') or d.get('expiry')))
    print('REQUESTER='+str(d.get('requester')))
    print('REQUESTER_AGENT_ID='+str(d.get('requesterAgentId') or d.get('requester_agent_id')))
    print('TAGS='+json.dumps(d.get('tags') or []))
    print('PENDING_ACTIONS='+json.dumps(d.get('pendingActions') or d.get('pending_actions') or [],ensure_ascii=False)[:4000])
    print('DESCRIPTION='+str(d.get('description') or '')[:9000].replace('\n','\\n'))
else:
    print('DETAIL_UNPARSEABLE='+str(d)[:1500])
if isinstance(s,dict):
    items=s.get('submissions') or s.get('items') or s.get('results') or []
elif isinstance(s,list): items=s
else: items=[]
print('SUBMISSION_COUNT='+str(len(items)))
for item in items[:8]:
    if isinstance(item,dict):
        print('SUB='+json.dumps({k:item.get(k) for k in ('id','workerAddress','workerAgentId','createdAt','status')},ensure_ascii=False))
PY
done
