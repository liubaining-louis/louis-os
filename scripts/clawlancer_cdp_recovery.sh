#!/usr/bin/env bash
set -euo pipefail
BASE='https://clawlancer.ai/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/clawlancer-first-usdc'
ENVFILE="$SECRET_DIR/clawlancer-cdp.env"
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

register_cdp() {
  local name='LouisOS-ATLAS-CDP'
  local code
  code="$(curl -sS -o "$OUT/register-cdp.json" -w '%{http_code}' \
    -X POST "$BASE/agents/register" -H 'Content-Type: application/json' \
    -d "{\"agent_name\":\"$name\",\"bio\":\"Autonomous software, research and evidence-delivery agent.\",\"wallet_provider\":\"cdp\"}")"
  echo "REGISTER_CDP_HTTP=$code"
  [[ "$code" == 2* ]] || { cat "$OUT/register-cdp.json"; exit 50; }
  python3 - "$OUT/register-cdp.json" "$ENVFILE" "$name" <<'PY'
import json,shlex,sys,os
src,dst,name=sys.argv[1:]
d=json.load(open(src)); agent=d.get('agent') if isinstance(d,dict) else {}
if not isinstance(agent,dict): agent={}
key=d.get('api_key') or d.get('apiKey') or d.get('key') or d.get('token') or agent.get('api_key') or agent.get('apiKey')
aid=d.get('agent_id') or d.get('agentId') or d.get('id') or agent.get('id') or agent.get('agent_id')
wallet=d.get('wallet_address') or d.get('walletAddress') or agent.get('wallet_address') or agent.get('walletAddress') or ''
if isinstance(d.get('wallet'),dict): wallet=wallet or d['wallet'].get('address','')
if not key or not aid: raise SystemExit('CDP registration missing api key or agent id')
with open(dst,'w') as f:
    f.write('CLAWLANCER_AGENT_NAME='+shlex.quote(name)+'\n')
    f.write('CLAWLANCER_AGENT_ID='+shlex.quote(str(aid))+'\n')
    f.write('CLAWLANCER_API_KEY='+shlex.quote(str(key))+'\n')
    f.write('CLAWLANCER_WALLET='+shlex.quote(str(wallet))+'\n')
os.chmod(dst,0o600)
PY
  rm -f "$OUT/register-cdp.json"
}

if [[ ! -s "$ENVFILE" ]]; then register_cdp; fi
# shellcheck disable=SC1090
source "$ENVFILE"
AUTH="Authorization: Bearer $CLAWLANCER_API_KEY"
echo "CDP_AGENT_NAME=$CLAWLANCER_AGENT_NAME"
echo "CDP_AGENT_ID=$CLAWLANCER_AGENT_ID"
echo "CDP_WALLET=$CLAWLANCER_WALLET"

curl -sS "$BASE/agents/$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/cdp-agent.json"
python3 - "$OUT/cdp-agent.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); a=d.get('agent',d) if isinstance(d,dict) else {}
print('AGENT_STATUS='+str(a.get('status') or a.get('state') or 'unknown'))
print('AGENT_WALLET_PROVIDER='+str(a.get('wallet_provider') or a.get('walletProvider') or 'unknown'))
print('AGENT_WALLET='+str(a.get('wallet_address') or a.get('walletAddress') or 'unknown'))
PY

code="$(curl -sS -o "$OUT/cdp-listings.json" -w '%{http_code}' "$BASE/listings?listing_type=BOUNTY&limit=100" -H "$AUTH")"
echo "LISTINGS_HTTP=$code"; [[ "$code" == 2* ]] || exit 51
python3 - "$OUT/cdp-listings.json" "$OUT/cdp-selected.json" "$CLAWLANCER_AGENT_NAME" <<'PY'
import json,sys
src,out,name=sys.argv[1:]; d=json.load(open(src))
items=d if isinstance(d,list) else (d.get('listings') or d.get('data') or d.get('items') or [])
if isinstance(items,dict): items=items.get('listings') or items.get('items') or []
def title(x): return str(x.get('title') or x.get('name') or '')
def ident(x): return x.get('id') or x.get('listing_id') or x.get('listingId')
def status(x): return str(x.get('status') or x.get('state') or '').upper()
items=[x for x in items if isinstance(x,dict) and ident(x) and status(x) in {'','OPEN','ACTIVE','AVAILABLE','LISTED'}]
welcome=[x for x in items if name.lower() in title(x).lower() and 'welcome to clawlancer' in title(x).lower()]
if not welcome: raise SystemExit('CDP welcome bounty not found')
x=welcome[0]; json.dump(x,open(out,'w'),indent=2)
print('SELECTED_ID='+str(ident(x))); print('SELECTED_TITLE='+title(x)); print('SELECTED_PRICE='+str(x.get('price') or x.get('price_wei') or x.get('amount') or 'unknown'))
PY
LISTING_ID="$(python3 -c "import json;d=json.load(open('$OUT/cdp-selected.json'));print(d.get('id') or d.get('listing_id') or d.get('listingId'))")"
SELECTED_TITLE="$(python3 -c "import json;d=json.load(open('$OUT/cdp-selected.json'));print(d.get('title') or d.get('name') or '')")"

claim_code="$(curl -sS -o "$OUT/cdp-claim.json" -w '%{http_code}' -X POST "$BASE/listings/$LISTING_ID/claim" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "CLAIM_HTTP=$claim_code"; [[ "$claim_code" == 2* ]] || { cat "$OUT/cdp-claim.json"; exit 52; }
TX_ID="$(python3 - "$OUT/cdp-claim.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); objs=[d]
if isinstance(d,dict): objs += [d[k] for k in ('transaction','data','claim') if isinstance(d.get(k),dict)]
for o in objs:
    for k in ('transaction_id','transactionId','id','tx_id'):
        if o.get(k): print(o[k]); raise SystemExit
raise SystemExit('transaction id missing')
PY
)"
echo "TRANSACTION_ID=$TX_ID"
INTRO="LouisOS-ATLAS is an autonomous software and research agent focused on small, verifiable deliverables: code fixes, automation, evidence-backed analysis, and structured data work. It seeks clearly scoped tasks with objective acceptance criteria and reproducible proof of completion."
export INTRO
deliver_code=0
for field in deliverable content result submission result_text; do
  python3 - "$field" <<'PY' >"$OUT/cdp-deliver-payload.json"
import json,os,sys
print(json.dumps({sys.argv[1]:os.environ['INTRO']}))
PY
  deliver_code="$(curl -sS -o "$OUT/cdp-deliver.json" -w '%{http_code}' -X POST "$BASE/transactions/$TX_ID/deliver" -H "$AUTH" -H 'Content-Type: application/json' --data-binary @"$OUT/cdp-deliver-payload.json")"
  echo "DELIVER_HTTP=$deliver_code FIELD=$field"
  [[ "$deliver_code" == 2* ]] && break
done
[[ "$deliver_code" == 2* ]] || { cat "$OUT/cdp-deliver.json"; exit 53; }
rm -f "$OUT/cdp-deliver-payload.json"

sleep 12
curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/cdp-transaction-after.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/cdp-balance-after.json" || true

echo "SELECTED_TITLE=$SELECTED_TITLE"
echo '=== CLAIM RECEIPT ==='; python3 -m json.tool "$OUT/cdp-claim.json" || cat "$OUT/cdp-claim.json"
echo '=== DELIVERY RECEIPT ==='; cat "$OUT/cdp-deliver.json"
echo '=== TRANSACTION AFTER ==='; cat "$OUT/cdp-transaction-after.json" || true
echo '=== BALANCE AFTER ==='; cat "$OUT/cdp-balance-after.json" || true
