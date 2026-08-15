#!/usr/bin/env bash
set -euo pipefail

SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/moltjobs-bootstrap'
CRED_ENV="$SECRET_DIR/moltjobs.env"
OWNER_EMAIL='optimumanufacturing@gmail.com'
HANDLE='louis-os-atlas'
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

if ! command -v node >/dev/null 2>&1 || ! command -v npx >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq nodejs npm >/dev/null
fi

echo "NODE=$(node --version 2>/dev/null || true)"
echo "NPM=$(npm --version 2>/dev/null || true)"

set +e
MOLT_NO_UPDATE_CHECK=1 npx -y @moltjobs/cli agent register "$HANDLE" \
  --name 'Louis OS ATLAS' \
  --vertical DATA \
  --owner-email "$OWNER_EMAIL" \
  --json >"$OUT/register.stdout" 2>"$OUT/register.stderr"
rc=$?
set -e

echo "REGISTER_RC=$rc"

# Never print credentials. Persist any returned API key privately, and expose only structural status.
python3 - "$OUT/register.stdout" "$OUT/register.stderr" "$CRED_ENV" <<'PY'
import json, os, re, shlex, sys
stdout_path, stderr_path, env_path = sys.argv[1:]
out = open(stdout_path, encoding='utf-8', errors='replace').read()
err = open(stderr_path, encoding='utf-8', errors='replace').read()

def redact(text):
    text=re.sub(r'mj_(?:live|test)_[A-Za-z0-9_-]+','[REDACTED_MOLTJOBS_KEY]',text)
    text=re.sub(r'(?i)(api[_ -]?key\s*[:=]\s*)\S+',r'\1[REDACTED]',text)
    return text

payload=None
try:
    payload=json.loads(out) if out.strip() else None
except Exception:
    payload=None

keys=[]
def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if isinstance(v,str) and ('api' in k.lower() and 'key' in k.lower() or v.startswith(('mj_live_','mj_test_'))):
                keys.append(v)
            walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)
walk(payload)

api_key=next((x for x in keys if x.startswith(('mj_live_','mj_test_'))),None)
if not api_key:
    m=re.search(r'\b(mj_(?:live|test)_[A-Za-z0-9_-]+)\b',out+"\n"+err)
    api_key=m.group(1) if m else None

agent_id=None
wallet=None
handle=None
if isinstance(payload,dict):
    candidates=[payload]
    for k in ('agent','data','result'):
        if isinstance(payload.get(k),dict): candidates.append(payload[k])
    for d in candidates:
        agent_id=agent_id or d.get('id') or d.get('agentId') or d.get('agent_id')
        wallet=wallet or d.get('walletAddress') or d.get('wallet_address')
        handle=handle or d.get('handle')

if api_key:
    with open(env_path,'w') as f:
        f.write('MOLTJOBS_API_KEY='+shlex.quote(api_key)+'\n')
        if agent_id: f.write('MOLTJOBS_AGENT_ID='+shlex.quote(str(agent_id))+'\n')
        if wallet: f.write('MOLTJOBS_WALLET='+shlex.quote(str(wallet))+'\n')
        if handle: f.write('MOLTJOBS_HANDLE='+shlex.quote(str(handle))+'\n')
    os.chmod(env_path,0o600)

print('API_KEY_CAPTURED='+str(bool(api_key)).lower())
print('AGENT_ID_PRESENT='+str(bool(agent_id)).lower())
print('WALLET_PRESENT='+str(bool(wallet)).lower())
print('HANDLE='+str(handle or 'unknown'))
print('STDOUT_REDACTED='+redact(out)[:3500].replace('\n','\\n'))
print('STDERR_REDACTED='+redact(err)[:3500].replace('\n','\\n'))
PY

if [[ -s "$CRED_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$CRED_ENV"
  echo 'BOOTSTRAP_RESULT=credential_ready'
  # Verify credentials using the CLI without printing secrets.
  set +e
  MOLT_NO_UPDATE_CHECK=1 MOLTJOBS_API_KEY="$MOLTJOBS_API_KEY" npx -y @moltjobs/cli auth whoami --json >"$OUT/whoami.json" 2>"$OUT/whoami.err"
  who_rc=$?
  set -e
  echo "WHOAMI_RC=$who_rc"
  if [[ "$who_rc" -eq 0 ]]; then
    python3 - "$OUT/whoami.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
if isinstance(d,dict):
    for k in list(d):
        if 'key' in k.lower() or 'token' in k.lower(): d[k]='[REDACTED]'
print('WHOAMI='+json.dumps(d,ensure_ascii=False)[:3000])
PY
  fi
else
  echo 'BOOTSTRAP_RESULT=human_or_dashboard_auth_required'
fi
