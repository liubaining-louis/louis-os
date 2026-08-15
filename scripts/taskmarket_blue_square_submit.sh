#!/usr/bin/env bash
set -euo pipefail

ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
OUT='/var/lib/louis-os/results/taskmarket-blue-square-submit'
TASK='0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
FILE='/tmp/taskmarket-blue-square.html'
mkdir -p "$OUT"
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'

run_tm(){ timeout --signal=TERM --kill-after=5s 90s npx -y @lucid-agents/taskmarket "$@"; }

[[ -s "$FILE" ]] || { echo 'DELIVERABLE_MISSING'; exit 70; }
bytes=$(wc -c < "$FILE")
echo "DELIVERABLE_BYTES=$bytes"
[[ "$bytes" -le 1000000 ]] || { echo 'DELIVERABLE_TOO_LARGE'; exit 71; }

run_tm wallet balance >"$OUT/balance-before.json"
python3 - "$OUT/balance-before.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); d=d.get('data',d) if isinstance(d,dict) else d
print('WORKER_WALLET='+str(d.get('address') if isinstance(d,dict) else 'unknown'))
print('BALANCE_USDC_BEFORE='+str(d.get('balanceUsdc') if isinstance(d,dict) else 'unknown'))
PY
WALLET=$(python3 - "$OUT/balance-before.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); d=d.get('data',d) if isinstance(d,dict) else d
print((d.get('address') or '').lower())
PY
)
[[ -n "$WALLET" ]] || { echo 'WALLET_UNRESOLVED'; exit 72; }
last=${WALLET: -1}
lane=$(( 16#$last % 10 ))
echo "WALLET_LANE=$lane"
[[ "$lane" -eq 2 ]] || { echo 'LANE_MISMATCH'; exit 73; }

# Authoritative last-second task verification.
run_tm task get "$TASK" >"$OUT/task-before.json"
python3 - "$OUT/task-before.json" <<'PY'
import json,sys,datetime
p=sys.argv[1]; d=json.load(open(p)); d=d.get('data',d) if isinstance(d,dict) else d
if not isinstance(d,dict): raise SystemExit('TASK_UNPARSEABLE')
status=str(d.get('status') or '').lower(); mode=str(d.get('mode') or '').lower()
reward=d.get('reward') or d.get('rewardUsdc') or d.get('reward_usdc')
expiry=d.get('expiryTime') or d.get('expiry_time') or d.get('expiry')
actions=d.get('pendingActions') or d.get('pending_actions') or []
worker_submit=[a for a in actions if isinstance(a,dict) and a.get('role')=='worker' and a.get('action')=='submit']
print('TASK_STATUS='+status); print('TASK_MODE='+mode); print('TASK_REWARD_BASE='+str(reward)); print('TASK_EXPIRY='+str(expiry)); print('WORKER_SUBMIT_ACTIONS='+str(len(worker_submit)))
if status!='open' or mode!='bounty': raise SystemExit('TASK_NOT_OPEN_BOUNTY')
if not worker_submit: raise SystemExit('NO_WORKER_SUBMIT_ACTION')
if any(bool(a.get('requiresPayment')) for a in worker_submit): raise SystemExit('WORKER_SUBMISSION_REQUIRES_PAYMENT')
PY

# Idempotency: never create duplicate submissions for the same wallet.
run_tm task submissions "$TASK" >"$OUT/submissions-before.json"
python3 - "$OUT/submissions-before.json" "$WALLET" >"$OUT/existing.txt" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); target=sys.argv[2].lower(); d=d.get('data',d) if isinstance(d,dict) else d
if isinstance(d,dict): items=d.get('submissions') or d.get('items') or d.get('results') or []
elif isinstance(d,list): items=d
else: items=[]
m=[]
for x in items:
    if isinstance(x,dict) and str(x.get('workerAddress') or x.get('worker_address') or '').lower()==target:
        m.append(x)
print(len(m))
for x in m: print(json.dumps(x,ensure_ascii=False))
PY
existing=$(head -n1 "$OUT/existing.txt")
echo "EXISTING_OWN_SUBMISSIONS=$existing"
if [[ "$existing" -gt 0 ]]; then
  echo 'SUBMISSION_ALREADY_PRESENT=true'
  tail -n +2 "$OUT/existing.txt"
  exit 0
fi

# Free worker action: no payment, stake, acceptance, or fund transfer is performed.
set +e
run_tm task submit "$TASK" --file "$FILE" >"$OUT/submit.json" 2>"$OUT/submit.err"
rc=$?
set -e
echo "SUBMIT_RC=$rc"
if [[ "$rc" -ne 0 ]]; then
  echo 'SUBMIT_STDERR:'; tail -n 100 "$OUT/submit.err"
  exit "$rc"
fi
cat "$OUT/submit.json"

# Verify receipt independently from the task's submission list.
sleep 2
run_tm task submissions "$TASK" >"$OUT/submissions-after.json"
python3 - "$OUT/submissions-after.json" "$WALLET" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); target=sys.argv[2].lower(); d=d.get('data',d) if isinstance(d,dict) else d
if isinstance(d,dict): items=d.get('submissions') or d.get('items') or d.get('results') or []
elif isinstance(d,list): items=d
else: items=[]
m=[]
for x in items:
    if isinstance(x,dict) and str(x.get('workerAddress') or x.get('worker_address') or '').lower()==target: m.append(x)
print('OWN_SUBMISSION_COUNT_AFTER='+str(len(m)))
for x in m: print('VERIFIED_SUBMISSION='+json.dumps(x,ensure_ascii=False))
if not m: raise SystemExit('SUBMISSION_NOT_FOUND_AFTER_WRITE')
PY

echo 'TASKMARKET_EXTERNAL_SUBMISSION_VERIFIED=true'
echo "TASK_ID=$TASK"
