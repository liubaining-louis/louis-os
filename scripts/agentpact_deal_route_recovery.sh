#!/usr/bin/env bash
set -euo pipefail
BASE='https://api.agentpact.xyz/api'
OUT='/var/lib/louis-os/results/agentpact-json-csv'
source /var/lib/louis-os/secrets/agentpact.env
AUTH="x-api-key: $AGENTPACT_API_KEY"
NEED_ID='e0750d6c-0e7b-48e1-9fdc-843c0b69ee41'
BUYER_AGENT_ID='0699af94-76a9-411f-bb20-40ed9e101b37'
SELLER_AGENT_ID="$AGENTPACT_AGENT_ID"
OFFER_ID='99aef21d-05dc-4375-bea6-94dd0b46ac5f'
IDEMP='louis-agentpact-jsoncsv-20260815-v1'
mkdir -p "$OUT"

# Revalidate need + offer ownership immediately before proposing.
curl -fsSL "$BASE/needs/$NEED_ID" >"$OUT/recovery-need.json"
curl -fsSL "$BASE/offers/$OFFER_ID" >"$OUT/recovery-offer.json"
python3 - "$OUT/recovery-need.json" "$OUT/recovery-offer.json" "$BUYER_AGENT_ID" "$SELLER_AGENT_ID" <<'PY'
import json,sys
need=json.load(open(sys.argv[1])); offer=json.load(open(sys.argv[2])); buyer=sys.argv[3]; seller=sys.argv[4]
n=need.get('need',need); o=offer.get('offer',offer)
na=str(n.get('agent_id') or n.get('agentId') or n.get('buyerAgentId') or '')
oa=str(o.get('agent_id') or o.get('agentId') or '')
status=str(n.get('status') or n.get('state') or 'open').lower()
print('NEED_OWNER='+na); print('OFFER_OWNER='+oa); print('NEED_STATUS='+status)
if na and na != buyer: raise SystemExit('buyer ownership changed')
if oa != seller: raise SystemExit('seller offer ownership mismatch')
if status in {'closed','archived','cancelled','completed','filled'}: raise SystemExit('need no longer open')
PY

python3 - "$NEED_ID" "$OFFER_ID" "$BUYER_AGENT_ID" "$SELLER_AGENT_ID" <<'PY' >"$OUT/recovery-deal-payload.json"
import json,sys
from datetime import datetime,timedelta,timezone
need,offer,buyer,seller=sys.argv[1:]
deadline=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
print(json.dumps({
  'needId': need,
  'offerId': offer,
  'buyerAgentId': buyer,
  'sellerAgentId': seller,
  'negotiatedTotal': 2.0,
  'maxPriceDeltaPct': 50,
  'milestones': [{
    'idx': 1,
    'title': 'Deliver tested JSON-to-CSV transform',
    'description': 'Provide the tested Python script, validation logic, usage instructions, and reproducible tests within the requested one-hour scope.',
    'amount': 2.0,
    'deadline': deadline,
    'acceptanceCriteria': [
      'Python converts JSON object(s) to CSV',
      'CSV output validates exact header and row count',
      'Seven deterministic unit tests pass',
      'Malformed/non-tabular JSON fails clearly'
    ]
  }]
}))
PY

code="$(curl -sS -o "$OUT/recovery-deal.json" -w '%{http_code}' \
  -X POST "$BASE/deals" \
  -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $IDEMP" \
  --data-binary @"$OUT/recovery-deal-payload.json")"
echo "DEALS_ROUTE_HTTP=$code"
cat "$OUT/recovery-deal.json"
[[ "$code" == 2* ]] || exit 91

python3 - "$OUT/recovery-deal.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); objs=[d]
if isinstance(d,dict): objs += [d[k] for k in ('deal','data') if isinstance(d.get(k),dict)]
for o in objs:
    if o.get('id') or o.get('dealId') or o.get('deal_id'):
        print('DEAL_ID='+str(o.get('id') or o.get('dealId') or o.get('deal_id')))
        print('DEAL_STATUS='+str(o.get('status') or o.get('state') or 'unknown'))
        raise SystemExit
raise SystemExit('deal id missing from success response')
PY
