#!/usr/bin/env bash
set -euo pipefail

ROOT='/var/lib/louis-os/taskmarket-home'
NODE_ROOT='/var/lib/louis-os/tools/node22'
OUT_JSON='/tmp/taskmarket-claims-followup.json'
export HOME="$ROOT"
export PATH="$NODE_ROOT/bin:$PATH"
export TASKMARKET_API_URL='https://api.taskmarket.dev'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

TASKS=(
  '0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
  '0xb4e0e2150a5b69a781769fe71f9092de3cffe978a03fd7286ebd408b99b152e3'
)
SUBMISSIONS=(
  '99cba5cc-7c8a-4fd2-97ea-492df2ef1eb3'
  '3761b8e9-22ed-4d4c-ada8-b3a9c687e6a5'
)
LABELS=(
  'blue_square_arcade'
  'rooftop_world_2030'
)

TM_CACHED="$(find "$ROOT/.npm/_npx" -type f -path '*/node_modules/.bin/taskmarket' -perm -u+x -print -quit 2>/dev/null || true)"
run_tm(){
  if [[ -n "$TM_CACHED" && -x "$TM_CACHED" ]]; then
    timeout --signal=TERM --kill-after=3s 30s "$TM_CACHED" "$@"
  else
    timeout --signal=TERM --kill-after=3s 35s npx -y @lucid-agents/taskmarket "$@"
  fi
}

capture_json(){
  local out="$1"; shift
  local attempt rc
  : >"$TMP/$out.err"
  for attempt in 1 2 3; do
    set +e
    run_tm "$@" >"$TMP/$out.json" 2>"$TMP/$out.err.attempt"
    rc=$?
    set -e
    cat "$TMP/$out.err.attempt" >>"$TMP/$out.err" || true
    if [[ "$rc" -eq 0 ]] && python3 -m json.tool "$TMP/$out.json" >/dev/null 2>&1; then
      echo "${out^^}_READ_OK=true attempt=$attempt" >&2
      return 0
    fi
    echo "${out^^}_READ_RETRY=$attempt rc=$rc" >&2
    sleep $((attempt*2))
  done
  echo '{}' >"$TMP/$out.json"
  echo "${out^^}_READ_OK=false" >&2
  return 1
}

errors=()
if ! capture_json balance wallet balance; then errors+=("balance_read_failed"); fi
for i in 0 1; do
  if ! capture_json "task_$i" task get "${TASKS[$i]}"; then errors+=("task_${i}_read_failed"); fi
  if ! capture_json "subs_$i" task submissions "${TASKS[$i]}"; then errors+=("subs_${i}_read_failed"); fi
done

ERRORS_JSON="$(printf '%s\n' "${errors[@]:-}" | python3 -c 'import json,sys; print(json.dumps([x.strip() for x in sys.stdin if x.strip()]))')"
export ERRORS_JSON

python3 - "$TMP" "$OUT_JSON" "${TASKS[0]}" "${SUBMISSIONS[0]}" "${LABELS[0]}" "${TASKS[1]}" "${SUBMISSIONS[1]}" "${LABELS[1]}" <<'PY'
import datetime,json,os,sys
root,out_path,*flat=sys.argv[1:]
pairs=[flat[i:i+3] for i in range(0,len(flat),3)]
errors=json.loads(os.environ.get('ERRORS_JSON','[]'))

def load(path):
    try: d=json.load(open(path))
    except Exception: return {}
    return d.get('data',d) if isinstance(d,dict) else d

balance_obj=load(f'{root}/balance.json')
wallet=str(balance_obj.get('address') or '') if isinstance(balance_obj,dict) else ''
try: balance=float(balance_obj.get('balanceUsdc') or 0) if isinstance(balance_obj,dict) else 0.0
except Exception: balance=0.0

claims=[]
for idx,(task_id,submission_id,label) in enumerate(pairs):
    t=load(f'{root}/task_{idx}.json'); s=load(f'{root}/subs_{idx}.json')
    if isinstance(s,dict): items=s.get('submissions') or s.get('items') or s.get('results') or []
    elif isinstance(s,list): items=s
    else: items=[]
    own=None
    for x in items:
        if not isinstance(x,dict): continue
        if str(x.get('id') or '')==submission_id:
            own=x; break
    if own is None and wallet:
        for x in items:
            if isinstance(x,dict) and str(x.get('workerAddress') or x.get('worker_address') or '').lower()==wallet.lower():
                own=x; break
    reward=(t.get('reward') or t.get('rewardUsdc') or t.get('reward_usdc') or t.get('rewardAmount')) if isinstance(t,dict) else None
    try:
        rv=float(reward or 0); reward_usdc=rv/1_000_000 if rv>1000 else rv
    except Exception: reward_usdc=None
    status=str(t.get('status') or 'unknown').lower() if isinstance(t,dict) else 'unknown'
    winner=None
    if isinstance(t,dict):
        for k in ('winner','winnerAddress','winner_address','acceptedWorker','accepted_worker','selectedWorker','selected_worker'):
            if t.get(k): winner=str(t.get(k)); break
    own_status=own.get('status') if isinstance(own,dict) else None
    rejected=(own.get('rejectedAt') or own.get('rejected_at')) if isinstance(own,dict) else None
    selection=bool((winner and wallet and winner.lower()==wallet.lower()) or str(own_status or '').lower() in {'accepted','winner','won','completed','paid'})
    claims.append({
      'label':label,'task_id':task_id,'submission_id':submission_id,
      'task_status':status,'task_reward_usdc':reward_usdc,
      'task_expiry':(t.get('expiryTime') or t.get('expiry_time') or t.get('expiry') or t.get('expiresAt') or t.get('expires_at')) if isinstance(t,dict) else None,
      'own_submission_found':bool(own),'own_submission_status':own_status,
      'own_submission_rejected_at':rejected,'task_winner':winner,'selection_signal':selection,
    })

selected_any=any(c['selection_signal'] for c in claims)
settled_any=any(c['task_status'] in {'completed','settled','paid'} for c in claims)
payout_candidate=bool(balance>0 and (selected_any or settled_any))
now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
out={
 'platform':'taskmarket','worker_wallet':wallet,'wallet_balance_usdc':balance,
 'claims':claims,'claim_count':len(claims),'selection_signal_any':selected_any,
 'payout_evidence_candidate':payout_candidate,'errors':errors,'monitor_healthy':not errors,
 'checked_at':now,'monitoring_mode':'read_only',
 'revenue_policy':'Do not attribute revenue until selection and payout are independently verified.'
}
with open(out_path,'w',encoding='utf-8') as f: json.dump(out,f,indent=2,ensure_ascii=False); f.write('\n')
os.chmod(out_path,0o644)
print('CLAIMS_FOLLOWUP_SNAPSHOT_WRITTEN='+out_path,file=sys.stderr)
PY

python3 -m json.tool "$OUT_JSON" >/dev/null
for f in "$TMP"/*.err; do
  [[ -s "$f" ]] || continue
  echo "--- $(basename "$f") ---" >&2
  tail -n 20 "$f" >&2 || true
done
