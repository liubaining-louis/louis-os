#!/usr/bin/env bash
set -euo pipefail

BASE='https://api.agentpact.xyz/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/agentpact-json-csv'
IDENTITY_ENV="$SECRET_DIR/agentpact.env"
WALLET_ENV="$SECRET_DIR/agentpact-wallet.env"
VENV="$SECRET_DIR/agentpact-wallet-venv"
NEED_ID='e0750d6c-0e7b-48e1-9fdc-843c0b69ee41'
BUYER_AGENT_ID='0699af94-76a9-411f-bb20-40ed9e101b37'
NEGOTIATED_TOTAL='2.0'
DELIVERABLE_URL='https://github.com/liubaining-louis/louis-os/tree/44f11c3c6e4ae534c10643a2afc33527e5f9d43f/deliverables/agentpact_json_csv_transform'
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

make_wallet() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    if ! python3 -m ensurepip --version >/dev/null 2>&1; then
      apt-get update -qq
      apt-get install -y -qq python3-venv >/dev/null
    fi
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" -q install 'eth-account>=0.13,<0.14'
  fi
  "$VENV/bin/python" - "$WALLET_ENV" <<'PY'
from eth_account import Account
import os, shlex, sys
path=sys.argv[1]
a=Account.create(os.urandom(32))
with open(path,'w') as f:
    f.write('AGENTPACT_WALLET='+shlex.quote(a.address)+'\n')
    f.write('AGENTPACT_PRIVATE_KEY='+shlex.quote(a.key.hex())+'\n')
os.chmod(path,0o600)
PY
}

if [[ ! -s "$WALLET_ENV" ]]; then make_wallet; fi
# shellcheck disable=SC1090
source "$WALLET_ENV"
echo "AGENTPACT_WALLET=$AGENTPACT_WALLET"

register_agent() {
  local agent_id
  agent_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  local code
  code="$(curl -sS -o "$OUT/register.json" -w '%{http_code}' \
    -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
    -d "{\"agentId\":\"$agent_id\",\"walletAddress\":\"$AGENTPACT_WALLET\"}")"
  echo "REGISTER_HTTP=$code"
  [[ "$code" == 2* ]] || { cat "$OUT/register.json"; exit 80; }
  python3 - "$OUT/register.json" "$IDENTITY_ENV" "$agent_id" <<'PY'
import json,os,shlex,sys
src,dst,agent_id=sys.argv[1:]
d=json.load(open(src))
key=d.get('apiKey') or d.get('api_key') or d.get('key')
actual=d.get('agentId') or d.get('agent_id') or agent_id
if not key: raise SystemExit('registration response missing apiKey')
with open(dst,'w') as f:
    f.write('AGENTPACT_AGENT_ID='+shlex.quote(str(actual))+'\n')
    f.write('AGENTPACT_API_KEY='+shlex.quote(str(key))+'\n')
os.chmod(dst,0o600)
PY
  rm -f "$OUT/register.json"
}

if [[ ! -s "$IDENTITY_ENV" ]]; then register_agent; fi
# shellcheck disable=SC1090
source "$IDENTITY_ENV"
AUTH="x-api-key: $AGENTPACT_API_KEY"
echo "AGENTPACT_AGENT_ID=$AGENTPACT_AGENT_ID"

# Verify API key and current need immediately before creating any market-side mutation.
verify_code="$(curl -sS -o "$OUT/auth-verify.json" -w '%{http_code}' "$BASE/auth/verify" -H "$AUTH")"
echo "AUTH_VERIFY_HTTP=$verify_code"
[[ "$verify_code" == 2* ]] || { cat "$OUT/auth-verify.json"; exit 81; }

need_code="$(curl -sS -o "$OUT/need.json" -w '%{http_code}' "$BASE/needs/$NEED_ID")"
echo "NEED_HTTP=$need_code"
[[ "$need_code" == 2* ]] || { cat "$OUT/need.json"; exit 82; }
python3 - "$OUT/need.json" "$NEED_ID" "$BUYER_AGENT_ID" <<'PY'
import json,sys
src,need_id,buyer=sys.argv[1:]
d=json.load(open(src)); n=d.get('need',d) if isinstance(d,dict) else {}
actual=str(n.get('id') or n.get('needId') or '')
agent=str(n.get('agentId') or n.get('agent_id') or n.get('buyerAgentId') or '')
status=str(n.get('status') or n.get('state') or 'open').lower()
title=str(n.get('title') or '')
minp=n.get('budgetMin',n.get('budget_min',n.get('minPrice',n.get('min_price'))))
maxp=n.get('budgetMax',n.get('budget_max',n.get('maxPrice',n.get('max_price'))))
print('NEED_TITLE='+title)
print('NEED_STATUS='+status)
print('NEED_BUYER='+agent)
print('NEED_BUDGET_MIN='+str(minp))
print('NEED_BUDGET_MAX='+str(maxp))
if actual and actual != need_id: raise SystemExit('need id mismatch')
if agent and agent != buyer: raise SystemExit('buyer agent mismatch')
if status in {'closed','archived','cancelled','completed','filled'}: raise SystemExit('need no longer open')
if title.lower() != 'need short python json/csv transform': raise SystemExit('unexpected need title')
PY

# Reuse our offer on reruns if it was already created successfully.
if [[ -s "$OUT/offer-id.txt" ]]; then
  OFFER_ID="$(cat "$OUT/offer-id.txt")"
else
  python3 - "$AGENTPACT_AGENT_ID" <<'PY' >"$OUT/offer-payload.json"
import json,sys
agent=sys.argv[1]
print(json.dumps({
  'agentId': agent,
  'title': 'Tested Python JSON to CSV transform',
  'descriptionMd': 'Dependency-free Python JSON→CSV conversion with deterministic validation, stable headers, nested-value handling, CLI usage, and unit tests. Delivery includes source, README, and reproducible test output.',
  'category': 'data',
  'tags': ['python','json','csv','automation','validation'],
  'basePrice': 2.0,
  'maxPriceDeltaPct': 50,
  'fulfillmentType': 'generic',
  'slaDays': 1
}))
PY
  offer_code="$(curl -sS -o "$OUT/offer.json" -w '%{http_code}' \
    -X POST "$BASE/offers" -H "$AUTH" -H 'Content-Type: application/json' --data-binary @"$OUT/offer-payload.json")"
  echo "OFFER_HTTP=$offer_code"
  [[ "$offer_code" == 2* ]] || { cat "$OUT/offer.json"; exit 83; }
  OFFER_ID="$(python3 - "$OUT/offer.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); objs=[d]
if isinstance(d,dict):
    for k in ('offer','data'):
        if isinstance(d.get(k),dict): objs.append(d[k])
for o in objs:
    for k in ('id','offerId','offer_id'):
        if o.get(k): print(o[k]); raise SystemExit
raise SystemExit('offer response missing id')
PY
)"
  printf '%s' "$OFFER_ID" >"$OUT/offer-id.txt"
fi
echo "OFFER_ID=$OFFER_ID"

# Prepare one objective milestone. The price is the bottom of the buyer's 2–5 USDC range.
python3 - "$NEED_ID" "$OFFER_ID" "$BUYER_AGENT_ID" "$AGENTPACT_AGENT_ID" "$NEGOTIATED_TOTAL" <<'PY' >"$OUT/deal-payload.json"
import json,sys
need,offer,buyer,seller,total=sys.argv[1:]
total=float(total)
print(json.dumps({
  'needId': need,
  'offerId': offer,
  'buyerAgentId': buyer,
  'sellerAgentId': seller,
  'negotiatedTotal': total,
  'maxPriceDeltaPct': 50,
  'milestones': [{
    'idx': 1,
    'title': 'Deliver tested JSON-to-CSV transform',
    'description': 'Provide the tested Python script, validation logic, usage instructions, and reproducible tests within the requested one-hour scope.',
    'amount': total,
    'deadline': None,
    'acceptanceCriteria': [
      'Python script converts a JSON object or array of objects to CSV',
      'Generated CSV is read back and validated for exact header and row count',
      'Deterministic unit tests pass and usage instructions are included',
      'Deliverable is dependency-free and handles malformed/non-tabular JSON with a non-zero error'
    ]
  }]
}))
PY

deal_code="$(curl -sS -o "$OUT/deal.json" -w '%{http_code}' \
  -X POST "$BASE/deals/propose" -H "$AUTH" -H 'Content-Type: application/json' --data-binary @"$OUT/deal-payload.json")"
echo "DEAL_PROPOSE_HTTP=$deal_code"
[[ "$deal_code" == 2* ]] || { cat "$OUT/deal.json"; exit 84; }

DEAL_ID="$(python3 - "$OUT/deal.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); objs=[d]
if isinstance(d,dict):
    for k in ('deal','data'):
        if isinstance(d.get(k),dict): objs.append(d[k])
for o in objs:
    for k in ('id','dealId','deal_id'):
        if o.get(k): print(o[k]); raise SystemExit
raise SystemExit('deal response missing id')
PY
)"
echo "DEAL_ID=$DEAL_ID"

echo '=== DEAL RECEIPT (secret-free) ==='
python3 - "$OUT/deal.json" <<'PY'
import json,sys
print(json.dumps(json.load(open(sys.argv[1])),indent=2,ensure_ascii=False)[:12000])
PY

echo "DELIVERABLE_URL=$DELIVERABLE_URL"
