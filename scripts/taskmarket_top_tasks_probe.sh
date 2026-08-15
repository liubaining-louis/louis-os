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

run_tm task list --status open >"$OUT/open-tasks.json" 2>"$OUT/open-tasks.err"

python3 - "$OUT/open-tasks.json" "$OUT/ranked-task-ids.txt" <<'PY'
import json,sys
src,out=sys.argv[1:]
raw=json.load(open(src))
obj=raw.get('data',raw) if isinstance(raw,dict) else raw
if isinstance(obj,dict):
    items=obj.get('tasks') or obj.get('items') or obj.get('results') or []
elif isinstance(obj,list):
    items=obj
else:
    items=[]

def amount(v):
    try:
        x=float(v or 0)
        return x/1_000_000 if x>1000 else x
    except Exception:
        return 0.0

def stake(v):
    try:
        x=float(v or 0)
        return x/1_000_000 if x>1000 else x
    except Exception:
        return 0.0

rows=[]
for x in items:
    if not isinstance(x,dict):
        continue
    tid=x.get('taskId') or x.get('task_id') or x.get('id')
    if not tid:
        continue
    reward=amount(x.get('rewardUsdc') or x.get('reward_usdc') or x.get('reward') or x.get('rewardAmount'))
    stk=stake(x.get('stakeRequired') or x.get('stake_required') or x.get('stake') or 0)
    mode=str(x.get('mode') or x.get('taskMode') or x.get('task_mode') or 'unknown').lower()
    desc=str(x.get('description') or x.get('title') or '')
    expiry=x.get('expiryTime') or x.get('expiry_time') or x.get('expiry') or x.get('expiresAt') or x.get('expires_at')
    rows.append({'id':str(tid),'reward_usdc':reward,'stake_usdc':stk,'mode':mode,'expiry':expiry,'description':desc[:800]})
rows.sort(key=lambda r:(r['stake_usdc']==0, r['mode']=='bounty', r['reward_usdc']), reverse=True)
print('LIVE_TASK_COUNT='+str(len(rows)))
for i,r in enumerate(rows[:20],1):
    print('RANKED_TASK_'+str(i)+'='+json.dumps(r,ensure_ascii=False))
open(out,'w').write('\n'.join(r['id'] for r in rows[:12])+'\n')
PY

mapfile -t TASKS < "$OUT/ranked-task-ids.txt"
for task in "${TASKS[@]}"; do
  [[ -n "$task" ]] || continue
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
    reward=d.get('reward') or d.get('rewardUsdc') or d.get('reward_usdc') or d.get('rewardAmount')
    stake=d.get('stakeRequired') or d.get('stake_required') or d.get('stake') or 0
    def norm(v):
        try:
            x=float(v or 0); return x/1_000_000 if x>1000 else x
        except:return None
    print('STATUS='+str(d.get('status')))
    print('MODE='+str(d.get('mode') or d.get('taskMode') or d.get('task_mode')))
    print('REWARD_USDC='+str(norm(reward)))
    print('STAKE_USDC='+str(norm(stake)))
    print('EXPIRY='+str(d.get('expiryTime') or d.get('expiry_time') or d.get('expiry') or d.get('expiresAt') or d.get('expires_at')))
    print('REQUESTER='+str(d.get('requester')))
    print('REQUESTER_AGENT_ID='+str(d.get('requesterAgentId') or d.get('requester_agent_id')))
    print('TAGS='+json.dumps(d.get('tags') or []))
    print('PENDING_ACTIONS='+json.dumps(d.get('pendingActions') or d.get('pending_actions') or [],ensure_ascii=False)[:4000])
    print('DESCRIPTION='+str(d.get('description') or d.get('title') or '')[:9000].replace('\n','\\n'))
else:
    print('DETAIL_UNPARSEABLE='+str(d)[:1500])
if isinstance(s,dict):
    items=s.get('submissions') or s.get('items') or s.get('results') or []
elif isinstance(s,list): items=s
else: items=[]
print('SUBMISSION_COUNT='+str(len(items)))
for item in items[:12]:
    if isinstance(item,dict):
        print('SUB='+json.dumps({k:item.get(k) for k in ('id','workerAddress','workerAgentId','createdAt','status','rejectedAt')},ensure_ascii=False))
PY
done
