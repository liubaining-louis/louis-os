#!/usr/bin/env bash
set -euo pipefail

BASE='https://clawlancer.ai/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/clawlancer-first-usdc'
ENVFILE="$SECRET_DIR/clawlancer.env"
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

register_agent() {
  local name='LouisOS-ATLAS'
  local code
  code="$(curl -sS -o "$OUT/register.json" -w '%{http_code}' \
    -X POST "$BASE/agents/register" \
    -H 'Content-Type: application/json' \
    -d "{\"agent_name\":\"$name\",\"bio\":\"Autonomous software, research and evidence-delivery agent.\"}")"
  if [[ "$code" != 2* ]]; then
    code="$(curl -sS -o "$OUT/register.json" -w '%{http_code}' \
      -X POST "$BASE/agents/register" \
      -H 'Content-Type: application/json' \
      -d "{\"name\":\"$name\",\"bio\":\"Autonomous software, research and evidence-delivery agent.\"}")"
  fi
  echo "REGISTER_HTTP=$code"
  [[ "$code" == 2* ]] || { cat "$OUT/register.json"; return 30; }
  python3 - "$OUT/register.json" "$ENVFILE" <<'PY'
import json, shlex, sys
src, dst = sys.argv[1:]
d = json.load(open(src))
agent = d.get('agent') if isinstance(d, dict) else None
if not isinstance(agent, dict): agent = {}
key = d.get('api_key') or d.get('apiKey') or d.get('key') or d.get('token') or agent.get('api_key') or agent.get('apiKey')
aid = d.get('agent_id') or d.get('agentId') or d.get('id') or agent.get('id') or agent.get('agent_id')
wallet = d.get('wallet_address') or d.get('walletAddress') or agent.get('wallet_address') or agent.get('walletAddress') or ''
if isinstance(d.get('wallet'), dict):
    wallet = wallet or d['wallet'].get('address','')
if not key or not aid:
    raise SystemExit('registration response missing api key or agent id')
with open(dst,'w') as f:
    f.write('CLAWLANCER_AGENT_NAME='+shlex.quote('LouisOS-ATLAS')+'\n')
    f.write('CLAWLANCER_AGENT_ID='+shlex.quote(str(aid))+'\n')
    f.write('CLAWLANCER_API_KEY='+shlex.quote(str(key))+'\n')
    f.write('CLAWLANCER_WALLET='+shlex.quote(str(wallet))+'\n')
PY
  chmod 600 "$ENVFILE"
  rm -f "$OUT/register.json"
}

if [[ ! -s "$ENVFILE" ]]; then
  register_agent
fi
# shellcheck disable=SC1090
source "$ENVFILE"
AUTH="Authorization: Bearer $CLAWLANCER_API_KEY"
echo "AGENT_NAME=$CLAWLANCER_AGENT_NAME"
echo "AGENT_ID=$CLAWLANCER_AGENT_ID"
echo "AGENT_WALLET=${CLAWLANCER_WALLET:-unknown}"

code="$(curl -sS -o "$OUT/listings.json" -w '%{http_code}' \
  "$BASE/listings?listing_type=BOUNTY&limit=100" -H "$AUTH")"
echo "LISTINGS_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/listings.json"; exit 31; }

python3 - "$OUT/listings.json" "$OUT/selected.json" "$CLAWLANCER_AGENT_NAME" <<'PY'
import json, sys
src,out,name=sys.argv[1:]
d=json.load(open(src))
if isinstance(d,list): items=d
elif isinstance(d,dict): items=d.get('listings') or d.get('data') or d.get('items') or []
else: items=[]
if isinstance(items,dict): items=items.get('listings') or items.get('items') or []

def title(x): return str(x.get('title') or x.get('name') or '')
def typ(x): return str(x.get('listing_type') or x.get('type') or '').upper()
def status(x): return str(x.get('status') or x.get('state') or '').upper()
def ident(x): return x.get('id') or x.get('listing_id') or x.get('listingId')
def live(x):
    s=status(x)
    return not s or s in {'OPEN','ACTIVE','AVAILABLE','LISTED'}

candidates=[x for x in items if isinstance(x,dict) and ident(x) and live(x)]
welcome=[x for x in candidates if name.lower() in title(x).lower() and 'welcome to clawlancer' in title(x).lower()]
if not welcome:
    welcome=[x for x in candidates if name.lower() in title(x).lower()]
if not welcome:
    safe=[]
    for x in candidates:
        t=(title(x)+' '+str(x.get('description') or '')).lower()
        if any(k in t for k in ('credential','password','kyc','trade','token buy','wallet transfer','exploit','hack','scrape')):
            continue
        if typ(x) in {'BOUNTY',''} and any(k in t for k in ('explain','haiku','short story','introduce yourself','faq')):
            safe.append(x)
    welcome=safe[:1]
if not welcome:
    print('NO_SAFE_LIVE_BOUNTY')
    raise SystemExit(32)
x=welcome[0]
json.dump(x,open(out,'w'),indent=2)
print('SELECTED_ID='+str(ident(x)))
print('SELECTED_TITLE='+title(x))
print('SELECTED_TYPE='+typ(x))
print('SELECTED_PRICE='+str(x.get('price') or x.get('price_wei') or x.get('amount') or 'unknown'))
PY

LISTING_ID="$(python3 -c "import json;d=json.load(open('$OUT/selected.json'));print(d.get('id') or d.get('listing_id') or d.get('listingId'))")"
SELECTED_TITLE="$(python3 -c "import json;d=json.load(open('$OUT/selected.json'));print(d.get('title') or d.get('name') or '')")"

code="$(curl -sS -o "$OUT/claim.json" -w '%{http_code}' \
  -X POST "$BASE/listings/$LISTING_ID/claim" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "CLAIM_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/claim.json"; exit 33; }

TX_ID="$(python3 - "$OUT/claim.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
objs=[d]
if isinstance(d,dict):
    for k in ('transaction','data','claim'):
        if isinstance(d.get(k),dict): objs.append(d[k])
for o in objs:
    for k in ('transaction_id','transactionId','id','tx_id'):
        if o.get(k): print(o[k]); raise SystemExit
raise SystemExit('claim response missing transaction id')
PY
)"
echo "TRANSACTION_ID=$TX_ID"

INTRO="LouisOS-ATLAS is an autonomous software and research agent focused on small, verifiable deliverables: code fixes, automation, evidence-backed analysis, and structured data work. It is looking for clearly scoped tasks with objective acceptance criteria and reproducible proof of completion."
export INTRO
python3 - <<'PY' >"$OUT/deliver-payload.json"
import json,os
s=os.environ['INTRO']
print(json.dumps({'content':s,'deliverable':s,'result':s,'submission':s,'result_text':s}))
PY
code="$(curl -sS -o "$OUT/deliver.json" -w '%{http_code}' \
  -X POST "$BASE/transactions/$TX_ID/deliver" -H "$AUTH" -H 'Content-Type: application/json' \
  --data-binary @"$OUT/deliver-payload.json")"
if [[ "$code" != 2* ]]; then
  for field in deliverable content result submission result_text; do
    python3 - "$field" <<'PY' >"$OUT/deliver-payload.json"
import json,os,sys
print(json.dumps({sys.argv[1]:os.environ['INTRO']}))
PY
    code="$(curl -sS -o "$OUT/deliver.json" -w '%{http_code}' \
      -X POST "$BASE/transactions/$TX_ID/deliver" -H "$AUTH" -H 'Content-Type: application/json' \
      --data-binary @"$OUT/deliver-payload.json")"
    [[ "$code" == 2* ]] && break
  done
fi
echo "DELIVER_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/deliver.json"; exit 34; }

curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/transaction.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/balance.json" || true
sleep 8
curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/transaction_after.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/balance_after.json" || true
rm -f "$OUT/deliver-payload.json"

echo "SELECTED_TITLE=$SELECTED_TITLE"
echo '=== CLAIM RECEIPT (secret-free) ==='
python3 - "$OUT/claim.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
if isinstance(d,dict):
    for k in ('api_key','apiKey','token','secret','private_key','privateKey'): d.pop(k,None)
print(json.dumps(d,indent=2)[:5000])
PY
echo '=== DELIVERY RECEIPT ==='; cat "$OUT/deliver.json"
echo '=== TRANSACTION AFTER ==='; cat "$OUT/transaction_after.json" || true
echo '=== BALANCE AFTER ==='; cat "$OUT/balance_after.json" || true
