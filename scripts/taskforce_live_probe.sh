#!/usr/bin/env bash
set -euo pipefail

BASE='https://task-force.app'
SECRET_DIR='/var/lib/louis-os/secrets'
SECRET_FILE="$SECRET_DIR/taskforce.env"
OUT='/var/lib/louis-os/results/taskforce'
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

register_if_needed() {
  if [[ -s "$SECRET_FILE" ]]; then
    echo 'REGISTRATION=reused_existing_vm_secret'
    return 0
  fi

  tmp="$(mktemp)"
  code="$(curl -sS -o "$tmp" -w '%{http_code}' \
    -X POST "$BASE/api/agent/register" \
    -H 'Content-Type: application/json' \
    --data '{"name":"Louis OS","capabilities":["python","coding","research","data","automation","api","browser","writing"]}')"
  echo "REGISTER_HTTP=$code"
  if [[ "$code" != '200' && "$code" != '201' ]]; then
    echo 'REGISTRATION=failed'
    python3 - "$tmp" <<'PY'
import sys
print(open(sys.argv[1]).read()[:1500])
PY
    rm -f "$tmp"
    return 1
  fi

  python3 - "$tmp" "$SECRET_FILE" <<'PY'
import json, pathlib, shlex, sys
src, dst = sys.argv[1:]
d = json.load(open(src))
key = d.get('apiKey') or d.get('api_key')
a = d.get('agent') or {}
agent_id = a.get('id') or d.get('agentId') or d.get('agent_id')
wallet = a.get('walletAddress') or d.get('walletAddress') or d.get('wallet_address') or ''
if not key or not agent_id:
    raise SystemExit('registration response missing apiKey/agent id')
p = pathlib.Path(dst)
p.write_text(
    'TASKFORCE_API_KEY=' + shlex.quote(str(key)) + '\n' +
    'TASKFORCE_AGENT_ID=' + shlex.quote(str(agent_id)) + '\n' +
    'TASKFORCE_WALLET=' + shlex.quote(str(wallet)) + '\n'
)
p.chmod(0o600)
print('REGISTRATION=created')
print('AGENT_ID=' + str(agent_id))
print('WALLET_PRESENT=' + ('true' if wallet else 'false'))
PY
  rm -f "$tmp"
}

register_if_needed
# shellcheck disable=SC1090
source "$SECRET_FILE"

# Never print the API key. Only bounded, non-secret identity metadata.
echo "AGENT_ID=$TASKFORCE_AGENT_ID"
echo "WALLET_PRESENT=$([[ -n "${TASKFORCE_WALLET:-}" ]] && echo true || echo false)"

# Probe the verification challenge without attempting to fabricate an answer.
# The prompt is saved VM-locally and only safe metadata is emitted.
challenge_code="$(curl -sS -o "$OUT/challenge.json" -w '%{http_code}' \
  -X POST "$BASE/api/agent/verify/challenge" \
  -H "Authorization: Bearer $TASKFORCE_API_KEY" \
  -H 'Content-Type: application/json' -d '{}')"
echo "CHALLENGE_HTTP=$challenge_code"
python3 - "$OUT/challenge.json" <<'PY'
import json, sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print('CHALLENGE_PARSE=false')
    raise SystemExit
print('CHALLENGE_PARSE=true')
print('CHALLENGE_ID_PRESENT=' + ('true' if d.get('challengeId') else 'false'))
print('CHALLENGE_PROMPT_PRESENT=' + ('true' if d.get('prompt') else 'false'))
print('CHALLENGE_EXPIRES_AT=' + str(d.get('expiresAt') or ''))
PY

# Authoritative live inventory probe.
tasks_code="$(curl -sS -o "$OUT/tasks.json" -w '%{http_code}' \
  "$BASE/api/agent/tasks?status=ACTIVE&limit=100" \
  -H "X-API-Key: $TASKFORCE_API_KEY")"
echo "TASKS_HTTP=$tasks_code"
python3 - "$OUT/tasks.json" <<'PY'
import datetime as dt, json, sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print('TASKS_PARSE=false')
    print(open(sys.argv[1]).read()[:1500])
    raise SystemExit
items = d.get('tasks', d.get('data', d if isinstance(d,list) else [])) if isinstance(d,(dict,list)) else []
if not isinstance(items,list): items=[]
now=dt.datetime.now(dt.timezone.utc)
print('TASKS_PARSE=true')
print('TASKS_SEEN='+str(len(items)))
qualified=[]
for j in items:
    if not isinstance(j,dict): continue
    status=str(j.get('status','')).upper()
    budget=j.get('totalBudget', j.get('budgetUsdc', j.get('budget',0)))
    try: budget=float(budget or 0)
    except Exception: budget=0.0
    deadline=j.get('deadline') or j.get('deadlineAt') or ''
    fresh=True
    if deadline:
        try:
            x=dt.datetime.fromisoformat(str(deadline).replace('Z','+00:00'))
            if x.tzinfo is None: x=x.replace(tzinfo=dt.timezone.utc)
            fresh=x>=now
        except Exception: pass
    if status in ('ACTIVE','OPEN','') and fresh and 1 <= budget <= 100:
        qualified.append(j)
print('QUALIFIED_1_100_USDC='+str(len(qualified)))
for j in qualified[:15]:
    safe={k:j.get(k) for k in ('id','title','status','category','totalBudget','budgetUsdc','deadline','deadlineAt','skillsRequired','paymentType')}
    print('CANDIDATE='+json.dumps(safe,separators=(',',':'),ensure_ascii=False)[:2500])
PY

# Portfolio and earnings endpoints prove authenticated operational access.
for spec in \
  "NOTIFICATIONS|$BASE/api/agent/notifications?unreadOnly=true&limit=5" \
  "EARNINGS|$BASE/api/agent/earnings"; do
  name="${spec%%|*}"
  url="${spec#*|}"
  code="$(curl -sS -o "$OUT/${name,,}.json" -w '%{http_code}' "$url" -H "X-API-Key: $TASKFORCE_API_KEY")"
  echo "${name}_HTTP=$code"
done
