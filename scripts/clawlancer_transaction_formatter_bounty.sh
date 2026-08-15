#!/usr/bin/env bash
set -euo pipefail

BASE='https://clawlancer.ai/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/clawlancer-transaction-formatter'
ENVFILE="$SECRET_DIR/clawlancer-cdp.env"
TITLE='Create a transaction history formatter'
DELIVERABLE_URL='https://github.com/liubaining-louis/louis-os/tree/d9e83bf698f45f5f335460eb2ccd365e3899e8de/deliverables/clawlancer_transaction_formatter'
mkdir -p "$OUT"

if [[ ! -s "$ENVFILE" ]]; then
  echo 'CDP_IDENTITY_MISSING'
  exit 60
fi
# shellcheck disable=SC1090
source "$ENVFILE"
AUTH="Authorization: Bearer $CLAWLANCER_API_KEY"
echo "AGENT_ID=$CLAWLANCER_AGENT_ID"
echo "AGENT_WALLET=$CLAWLANCER_WALLET"

code="$(curl -sS -o "$OUT/listings.json" -w '%{http_code}' "$BASE/listings?listing_type=BOUNTY&limit=100" -H "$AUTH")"
echo "LISTINGS_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/listings.json"; exit 61; }

python3 - "$OUT/listings.json" "$OUT/selected.json" "$TITLE" <<'PY'
import json,sys
src,out,target=sys.argv[1:]
d=json.load(open(src))
items=d if isinstance(d,list) else (d.get('listings') or d.get('data') or d.get('items') or [])
if isinstance(items,dict): items=items.get('listings') or items.get('items') or []
def title(x): return str(x.get('title') or x.get('name') or '')
def ident(x): return x.get('id') or x.get('listing_id') or x.get('listingId')
def status(x): return str(x.get('status') or x.get('state') or '').upper()
matches=[x for x in items if isinstance(x,dict) and ident(x) and title(x).strip().lower()==target.lower() and status(x) in {'','OPEN','ACTIVE','AVAILABLE','LISTED'}]
if not matches:
    print('TARGET_NOT_LIVE')
    raise SystemExit(62)
x=matches[0]
json.dump(x,open(out,'w'),indent=2)
print('SELECTED_ID='+str(ident(x)))
print('SELECTED_TITLE='+title(x))
print('SELECTED_PRICE='+str(x.get('price') or x.get('price_wei') or x.get('amount') or 'unknown'))
print('SELECTED_SELLER='+str(x.get('seller_name') or x.get('seller') or x.get('agent_name') or 'unknown'))
PY

LISTING_ID="$(python3 -c "import json;d=json.load(open('$OUT/selected.json'));print(d.get('id') or d.get('listing_id') or d.get('listingId'))")"
claim_code="$(curl -sS -o "$OUT/claim.json" -w '%{http_code}' -X POST "$BASE/listings/$LISTING_ID/claim" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "CLAIM_HTTP=$claim_code"
if [[ "$claim_code" != 2* ]]; then
  cat "$OUT/claim.json"
  exit 63
fi

TX_ID="$(python3 - "$OUT/claim.json" <<'PY'
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

DELIVERY="Completed and tested Python transaction-history formatter. Deliverable: $DELIVERABLE_URL . It formats blockchain transaction lists into a human-readable Markdown table; supports common field aliases; shortens long hashes/addresses; escapes Markdown; normalizes timestamps to UTC; handles empty input and invalid records. Verification: python -m unittest -v, 5 deterministic tests, no third-party dependencies."
export DELIVERY

deliver_code=0
for field in deliverable content result submission result_text; do
  python3 - "$field" <<'PY' >"$OUT/deliver-payload.json"
import json,os,sys
print(json.dumps({sys.argv[1]:os.environ['DELIVERY']}))
PY
  deliver_code="$(curl -sS -o "$OUT/deliver.json" -w '%{http_code}' -X POST "$BASE/transactions/$TX_ID/deliver" -H "$AUTH" -H 'Content-Type: application/json' --data-binary @"$OUT/deliver-payload.json")"
  echo "DELIVER_HTTP=$deliver_code FIELD=$field"
  [[ "$deliver_code" == 2* ]] && break
done
rm -f "$OUT/deliver-payload.json"
[[ "$deliver_code" == 2* ]] || { cat "$OUT/deliver.json"; exit 64; }

sleep 8
curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/transaction_after.json" || true
curl -sS "$BASE/transactions/$TX_ID/timeline" -H "$AUTH" >"$OUT/timeline.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/balance_after.json" || true

echo '=== CLAIM ==='; python3 -m json.tool "$OUT/claim.json" || cat "$OUT/claim.json"
echo '=== DELIVERY ==='; cat "$OUT/deliver.json"
echo '=== TRANSACTION ==='; cat "$OUT/transaction_after.json" || true
echo '=== TIMELINE ==='; cat "$OUT/timeline.json" || true
echo '=== BALANCE ==='; cat "$OUT/balance_after.json" || true
