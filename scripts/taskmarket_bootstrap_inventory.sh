#!/usr/bin/env bash
set -euo pipefail

ROOT='/var/lib/louis-os/taskmarket-home'
OUT='/var/lib/louis-os/results/taskmarket-bootstrap'
TOOLS='/var/lib/louis-os/tools'
NODE_ROOT="$TOOLS/node22"
mkdir -p "$ROOT" "$OUT" "$TOOLS"
chmod 700 "$ROOT"
export HOME="$ROOT"
export TASKMARKET_API_URL='https://api.taskmarket.dev'

ensure_node22() {
  if [[ -x "$NODE_ROOT/bin/node" ]]; then
    export PATH="$NODE_ROOT/bin:$PATH"
    return
  fi
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  sums="$(curl -fsSL --max-time 30 https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt)"
  archive="$(printf '%s\n' "$sums" | awk '$2 ~ /^node-v22.*-linux-x64\.tar\.gz$/ {print $2; exit}')"
  [[ -n "$archive" ]] || { echo 'NODE_ARCHIVE_NOT_FOUND'; return 20; }
  curl -fsSL --max-time 90 "https://nodejs.org/dist/latest-v22.x/$archive" -o "$tmp/node.tar.gz"
  expected="$(printf '%s\n' "$sums" | awk -v f="$archive" '$2==f {print $1}')"
  actual="$(sha256sum "$tmp/node.tar.gz" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || { echo 'NODE_SHA256_MISMATCH'; return 21; }
  mkdir -p "$NODE_ROOT.tmp"
  tar -xzf "$tmp/node.tar.gz" -C "$NODE_ROOT.tmp" --strip-components=1
  rm -rf "$NODE_ROOT"
  mv "$NODE_ROOT.tmp" "$NODE_ROOT"
  export PATH="$NODE_ROOT/bin:$PATH"
}

ensure_node22
echo "NODE=$(node --version)"
echo "NPM=$(npm --version)"

run_tm() {
  timeout --signal=TERM --kill-after=5s 90s npx -y @lucid-agents/taskmarket "$@"
}

# Platform-sponsored initial wallet/device/agent registration. Re-running is
# idempotent when the encrypted keystore already exists.
set +e
run_tm init </dev/null >"$OUT/init.json" 2>"$OUT/init.err"
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
run_tm identity status </dev/null >"$OUT/identity.json" 2>"$OUT/identity.err"
id_rc=$?
run_tm wallet balance </dev/null >"$OUT/balance.json" 2>"$OUT/balance.err"
bal_rc=$?
run_tm task list --status open </dev/null >"$OUT/tasks.json" 2>"$OUT/tasks.err"
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
    try: return float(v)
    except Exception: return 0
rows.sort(key=lambda x:(x['mode']=='bounty', not bool(x['stake']), reward_num(x['reward'])),reverse=True)
for row in rows[:40]:
    print('TASK='+json.dumps(row,ensure_ascii=False))
PY

KS="$HOME/.taskmarket/keystore.json"
if [[ -f "$KS" ]]; then
  echo "KEYSTORE_PRESENT=true"
  stat -c 'KEYSTORE_MODE=%a KEYSTORE_BYTES=%s' "$KS"
else
  echo "KEYSTORE_PRESENT=false"
fi
