#!/usr/bin/env bash
set -euo pipefail

ROOT='/var/lib/louis-os/taskmarket-home'
OUT='/var/lib/louis-os/results/taskmarket-bootstrap'
mkdir -p "$ROOT" "$OUT"
chmod 700 "$ROOT"
export HOME="$ROOT"
export TASKMARKET_API_URL='https://api.taskmarket.dev'

if ! command -v node >/dev/null 2>&1 || [[ "$(node -p 'Number(process.versions.node.split(`.`)[0])' 2>/dev/null || echo 0)" -lt 18 ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq nodejs npm >/dev/null
fi

echo "NODE=$(node --version 2>/dev/null || true)"
echo "NPM=$(npm --version 2>/dev/null || true)"

run_tm() {
  timeout --signal=TERM --kill-after=5s 90s npx -y @lucid-agents/taskmarket "$@"
}

# Platform-sponsored initial wallet/device/agent registration. Re-running is
# documented as idempotent when the keystore already exists.
set +e
run_tm init >"$OUT/init.json" 2>"$OUT/init.err"
init_rc=$?
set -e
echo "INIT_RC=$init_rc"
if [[ "$init_rc" -ne 0 ]]; then
  echo 'INIT_STDERR:'
  sed -E 's/(0x[0-9a-fA-F]{64})/[REDACTED_PRIVATE_MATERIAL]/g' "$OUT/init.err" | tail -n 80
  exit "$init_rc"
fi

# Report only public wallet/agent metadata; encrypted keystore stays on VM.
python3 - "$OUT/init.json" <<'PY'
import json,re,sys
text=open(sys.argv[1],encoding='utf-8',errors='replace').read()
try:
    d=json.loads(text)
except Exception:
    d=None
print('INIT_JSON_PARSEABLE='+str(isinstance(d,(dict,list))).lower())
if isinstance(d,dict):
    data=d.get('data',d)
    if isinstance(data,dict):
        print('WALLET_ADDRESS='+str(data.get('address') or data.get('walletAddress') or data.get('wallet_address') or 'unknown'))
        print('AGENT_ID='+str(data.get('agentId') or data.get('agent_id') or 'unknown'))
else:
    safe=re.sub(r'0x[0-9a-fA-F]{64}','[REDACTED_PRIVATE_MATERIAL]',text)
    print('INIT_OUTPUT='+safe[:3000].replace('\n','\\n'))
PY

set +e
run_tm identity status >"$OUT/identity.json" 2>"$OUT/identity.err"
id_rc=$?
run_tm wallet balance >"$OUT/balance.json" 2>"$OUT/balance.err"
bal_rc=$?
run_tm task list --status open >"$OUT/tasks.json" 2>"$OUT/tasks.err"
tasks_rc=$?
set -e

echo "IDENTITY_RC=$id_rc"
echo "BALANCE_RC=$bal_rc"
echo "TASKS_RC=$tasks_rc"

python3 - "$OUT/identity.json" "$OUT/balance.json" "$OUT/tasks.json" <<'PY'
import json,sys
identity_path,balance_path,tasks_path=sys.argv[1:]

def load(path):
    try: return json.load(open(path))
    except Exception: return None

def data(x):
    return x.get('data',x) if isinstance(x,dict) else x

i=load(identity_path); b=load(balance_path); t=load(tasks_path)
print('IDENTITY='+json.dumps(data(i),ensure_ascii=False)[:2500] if i is not None else 'IDENTITY=unparseable')
print('BALANCE='+json.dumps(data(b),ensure_ascii=False)[:2500] if b is not None else 'BALANCE=unparseable')

obj=data(t)
if isinstance(obj,dict):
    items=obj.get('tasks') or obj.get('items') or obj.get('results') or []
elif isinstance(obj,list):
    items=obj
else:
    items=[]

print('LIVE_TASK_COUNT='+str(len(items)))
rows=[]
for x in items:
    if not isinstance(x,dict): continue
    tid=x.get('taskId') or x.get('task_id') or x.get('id')
    desc=str(x.get('description') or x.get('title') or '')
    reward=x.get('rewardUsdc') or x.get('reward_usdc') or x.get('reward') or x.get('rewardAmount')
    mode=str(x.get('mode') or x.get('taskMode') or x.get('task_mode') or 'unknown').lower()
    status=str(x.get('status') or '').lower()
    stake=x.get('stakeRequired') or x.get('stake_required') or x.get('stake') or 0
    expiry=x.get('expiry') or x.get('expiresAt') or x.get('expires_at')
    tags=x.get('tags') or []
    rows.append({'id':tid,'reward':reward,'mode':mode,'status':status,'stake':stake,'expiry':expiry,'tags':tags,'description':desc[:500]})

def reward_num(v):
    try:
        n=float(v)
        # API may expose base units; keep ordering useful without changing display.
        return n
    except Exception:
        return 0
rows.sort(key=lambda x:(x['mode']=='bounty', not bool(x['stake']), reward_num(x['reward'])),reverse=True)
for row in rows[:40]:
    print('TASK='+json.dumps(row,ensure_ascii=False))
PY

# Verify keystore exists and has private permissions, without printing contents.
KS="$HOME/.taskmarket/keystore.json"
if [[ -f "$KS" ]]; then
  echo "KEYSTORE_PRESENT=true"
  stat -c 'KEYSTORE_MODE=%a KEYSTORE_BYTES=%s' "$KS"
else
  echo "KEYSTORE_PRESENT=false"
fi
