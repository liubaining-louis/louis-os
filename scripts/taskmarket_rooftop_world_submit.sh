#!/usr/bin/env bash
set -euo pipefail

ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
OUT='/var/lib/louis-os/results/taskmarket-rooftop-world-submit'
TASK='0xb4e0e2150a5b69a781769fe71f9092de3cffe978a03fd7286ebd408b99b152e3'
FILE='/tmp/world-of-base-rooftop-2030.mp4'
mkdir -p "$OUT"
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'

run_tm(){ timeout --signal=TERM --kill-after=5s 90s npx -y @lucid-agents/taskmarket "$@"; }

[[ -s "$FILE" ]] || { echo 'DELIVERABLE_MISSING'; exit 70; }
bytes=$(wc -c < "$FILE")
echo "DELIVERABLE_BYTES=$bytes"
[[ "$bytes" -le 60000000 ]] || { echo 'DELIVERABLE_TOO_LARGE'; exit 71; }

# Media hard gates immediately before the external action.
ffprobe -v error -show_entries format=duration:stream=codec_type,width,height -of json "$FILE" > "$OUT/media.json"
python3 - "$OUT/media.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); streams=d.get('streams') or []
dur=float((d.get('format') or {}).get('duration') or 0)
vid=[s for s in streams if s.get('codec_type')=='video']; aud=[s for s in streams if s.get('codec_type')=='audio']
print(f'MEDIA_DURATION={dur:.3f}'); print('MEDIA_VIDEO_STREAMS='+str(len(vid))); print('MEDIA_AUDIO_STREAMS='+str(len(aud)))
if not 5 <= dur <= 10: raise SystemExit('MEDIA_DURATION_FAIL')
if len(vid)!=1 or not aud: raise SystemExit('MEDIA_STREAM_FAIL')
if int(vid[0].get('width') or 0)<1080 or int(vid[0].get('height') or 0)<1080: raise SystemExit('MEDIA_RESOLUTION_FAIL')
print('MEDIA_GATE=PASS')
PY

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
expiry=d.get('expiryTime') or d.get('expiry_time') or d.get('expiry') or d.get('expiresAt') or d.get('expires_at')
actions=d.get('pendingActions') or d.get('pending_actions') or []
worker_submit=[a for a in actions if isinstance(a,dict) and a.get('role')=='worker' and a.get('action')=='submit']
print('TASK_STATUS='+status); print('TASK_MODE='+mode); print('TASK_REWARD_BASE='+str(reward)); print('TASK_EXPIRY='+str(expiry)); print('WORKER_SUBMIT_ACTIONS='+str(len(worker_submit)))
if status!='open' or mode!='bounty': raise SystemExit('TASK_NOT_OPEN_BOUNTY')
try:
    amount=float(reward or 0); amount=amount/1_000_000 if amount>1000 else amount
except Exception: amount=0
print('TASK_REWARD_USDC='+str(amount))
if abs(amount-64.0)>0.0001: raise SystemExit('TASK_REWARD_CHANGED')
if not worker_submit: raise SystemExit('NO_WORKER_SUBMIT_ACTION')
if any(bool(a.get('requiresPayment')) for a in worker_submit): raise SystemExit('WORKER_SUBMISSION_REQUIRES_PAYMENT')
if expiry:
    x=str(expiry).replace('Z','+00:00')
    if datetime.datetime.fromisoformat(x) <= datetime.datetime.now(datetime.timezone.utc): raise SystemExit('TASK_EXPIRED')
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

# Free worker action only: no stake, payment, task funding, acceptance, or transfer.
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
echo "DELIVERABLE_SHA256=$(sha256sum "$FILE" | awk '{print $1}')"
