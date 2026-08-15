#!/usr/bin/env bash
set -euo pipefail
ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
TASK='0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
SUBMISSION='99cba5cc-7c8a-4fd2-97ea-492df2ef1eb3'
OUT_JSON='/tmp/taskmarket-blue-square-followup.json'
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

TM_CACHED="$(find "$ROOT/.npm/_npx" -type f -path '*/node_modules/.bin/taskmarket' -perm -u+x -print -quit 2>/dev/null || true)"
run_tm(){
  if [[ -n "$TM_CACHED" && -x "$TM_CACHED" ]]; then
    timeout --signal=TERM --kill-after=3s 30s "$TM_CACHED" "$@"
  else
    timeout --signal=TERM --kill-after=3s 35s npx -y @lucid-agents/taskmarket "$@"
  fi
}

capture_json(){
  local name="$1"; shift
  local attempt rc
  : >"$TMP/$name.err"
  for attempt in 1 2 3; do
    set +e
    run_tm "$@" >"$TMP/$name.json" 2>"$TMP/$name.err.attempt"
    rc=$?
    set -e
    cat "$TMP/$name.err.attempt" >>"$TMP/$name.err" || true
    if [[ "$rc" -eq 0 ]] && python3 -m json.tool "$TMP/$name.json" >/dev/null 2>&1; then
      echo "${name^^}_READ_OK=true attempt=$attempt" >&2
      return 0
    fi
    echo "${name^^}_READ_RETRY=$attempt rc=$rc" >&2
    sleep $((attempt * 2))
  done
  echo '{}' >"$TMP/$name.json"
  echo "${name^^}_READ_OK=false" >&2
  return 1
}

errors=()
if ! capture_json task task get "$TASK"; then errors+=("task_read_failed"); fi
if ! capture_json submissions task submissions "$TASK"; then errors+=("submissions_read_failed"); fi
if ! capture_json balance wallet balance; then errors+=("balance_read_failed"); fi

ERRORS_JSON="$(printf '%s\n' "${errors[@]:-}" | python3 -c 'import json,sys; print(json.dumps([x.strip() for x in sys.stdin if x.strip()]))')"
export ERRORS_JSON

python3 - "$TMP/task.json" "$TMP/submissions.json" "$TMP/balance.json" "$TASK" "$SUBMISSION" "$OUT_JSON" <<'PY'
import json,sys,datetime,os
pt,ps,pb,task_id,submission_id,out_path=sys.argv[1:]

def load(p):
    try:
        d=json.load(open(p))
    except Exception:
        return {}
    return d.get('data',d) if isinstance(d,dict) else d

t=load(pt); s=load(ps); b=load(pb)
errors=json.loads(os.environ.get('ERRORS_JSON','[]'))
if isinstance(s,dict): items=s.get('submissions') or s.get('items') or s.get('results') or []
elif isinstance(s,list): items=s
else: items=[]
wallet=str(b.get('address') or '') if isinstance(b,dict) else ''
own=None
for x in items:
    if not isinstance(x,dict):
        continue
    if str(x.get('id') or '')==submission_id or (wallet and str(x.get('workerAddress') or x.get('worker_address') or '').lower()==wallet.lower()):
        own=x
        break
reward=(t.get('reward') or t.get('rewardUsdc') or t.get('reward_usdc')) if isinstance(t,dict) else None
try:
    rv=float(reward); reward_usdc=rv/1_000_000 if rv>1000 else rv
except Exception:
    reward_usdc=None
status=str(t.get('status') or 'unknown').lower() if isinstance(t,dict) else 'unknown'
winner=None
if isinstance(t,dict):
    for k in ('winner','winnerAddress','winner_address','acceptedWorker','accepted_worker','selectedWorker','selected_worker'):
        if t.get(k):
            winner=str(t.get(k)); break
own_status=(own.get('status') if isinstance(own,dict) else None)
rejected=(own.get('rejectedAt') or own.get('rejected_at')) if isinstance(own,dict) else None
try:
    balance=float(b.get('balanceUsdc') or 0) if isinstance(b,dict) else 0.0
except Exception:
    balance=0.0
selection_signal=bool((winner and wallet and winner.lower()==wallet.lower()) or str(own_status or '').lower() in {'accepted','winner','won','completed','paid'})
payout_candidate=bool(balance>0 and (selection_signal or status in {'completed','settled','paid'}))
out={
 'platform':'taskmarket','task_id':task_id,'submission_id':submission_id,'worker_wallet':wallet,
 'task_status':status,'task_reward_usdc':reward_usdc,
 'task_expiry':(t.get('expiryTime') or t.get('expiry_time') or t.get('expiry')) if isinstance(t,dict) else None,
 'own_submission_found':bool(own),'own_submission_status':own_status,'own_submission_rejected_at':rejected,
 'task_winner':winner,'wallet_balance_usdc':balance,'payout_evidence_candidate':payout_candidate,
 'selection_signal':selection_signal,'errors':errors,'monitor_healthy':not errors,
 'checked_at':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
 'monitoring_mode':'read_only','revenue_policy':'Do not attribute revenue until selection/payout is independently verified.'
}
text=json.dumps(out,ensure_ascii=False,indent=2)+'\n'
with open(out_path,'w',encoding='utf-8') as f:
    f.write(text)
os.chmod(out_path,0o644)
print('FOLLOWUP_SNAPSHOT_WRITTEN='+out_path, file=sys.stderr)
PY

python3 -m json.tool "$OUT_JSON" >/dev/null
for f in "$TMP"/*.err; do
  [[ -s "$f" ]] || continue
  echo "--- $(basename "$f") ---" >&2
  tail -n 30 "$f" >&2 || true
done
