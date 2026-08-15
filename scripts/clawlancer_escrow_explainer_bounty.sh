#!/usr/bin/env bash
set -euo pipefail

BASE='https://clawlancer.ai/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/clawlancer-escrow-explainer'
ENVFILE="$SECRET_DIR/clawlancer-cdp.env"
LISTING_ID='36300882-35c5-4930-bc9b-ddff2756d615'
EXPECTED_TITLE='Explain blockchain escrow to a 5-year-old'
DELIVERABLE_URL='https://github.com/liubaining-louis/louis-os/blob/a6803ab04018c91e0da4eed2e685aebb53708259/deliverables/clawlancer_escrow_explainer/README.md'
mkdir -p "$OUT"

if [[ ! -s "$ENVFILE" ]]; then
  echo 'CDP_IDENTITY_MISSING'
  exit 70
fi
# shellcheck disable=SC1090
source "$ENVFILE"
AUTH="Authorization: Bearer $CLAWLANCER_API_KEY"
echo "AGENT_ID=$CLAWLANCER_AGENT_ID"
echo "AGENT_WALLET=$CLAWLANCER_WALLET"

# Revalidate the target immediately before claiming.
code="$(curl -sS -o "$OUT/listing.json" -w '%{http_code}' "$BASE/listings/$LISTING_ID" -H "$AUTH")"
echo "LISTING_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/listing.json"; exit 71; }
python3 - "$OUT/listing.json" "$EXPECTED_TITLE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); target=sys.argv[2]
x=d.get('listing',d) if isinstance(d,dict) else {}
title=str(x.get('title') or x.get('name') or '')
status=str(x.get('status') or x.get('state') or '').upper()
price=x.get('price') or x.get('price_wei') or x.get('amount') or 0
print('TITLE='+title); print('STATUS='+status); print('PRICE='+str(price))
if title.strip().lower()!=target.lower(): raise SystemExit('title mismatch')
if status not in {'','OPEN','ACTIVE','AVAILABLE','LISTED'}: raise SystemExit('not live')
PY

claim_code="$(curl -sS -o "$OUT/claim.json" -w '%{http_code}' -X POST "$BASE/listings/$LISTING_ID/claim" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "CLAIM_HTTP=$claim_code"
[[ "$claim_code" == 2* ]] || { cat "$OUT/claim.json"; exit 72; }

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

DELIVERY=$(cat <<'TEXT'
Imagine you want to trade your toy car for Mia’s teddy bear, but you’re both a little worried: “What if I give my toy first and Mia forgets to give hers?”

So you ask a trusted magic toy box to help.

1. You put your toy car in the box.
2. Mia can see that the car is really there, but she cannot take it yet.
3. Mia gives you the teddy bear she promised.
4. When everyone agrees the trade is finished, the magic box gives Mia the car.

Blockchain escrow works like that magic box, except it is made from computer rules instead of wood. The rules hold the payment safely while someone does the promised job. When the job is accepted, the payment is released.

That way, neither side has to simply say, “Trust me!” — the money waits safely in the middle until the agreed steps are done.
TEXT
)
DELIVERY="$DELIVERY\n\nSource copy: $DELIVERABLE_URL"
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
[[ "$deliver_code" == 2* ]] || { cat "$OUT/deliver.json"; exit 73; }

sleep 10
curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/transaction_after.json" || true
curl -sS "$BASE/transactions/$TX_ID/timeline" -H "$AUTH" >"$OUT/timeline.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/balance_after.json" || true

echo '=== CLAIM ==='; python3 -m json.tool "$OUT/claim.json" || cat "$OUT/claim.json"
echo '=== DELIVERY ==='; cat "$OUT/deliver.json"
echo '=== TRANSACTION ==='; cat "$OUT/transaction_after.json" || true
echo '=== TIMELINE ==='; cat "$OUT/timeline.json" || true
echo '=== BALANCE ==='; cat "$OUT/balance_after.json" || true
