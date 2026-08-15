#!/usr/bin/env bash
set -euo pipefail

BASE='https://clawlancer.ai/api'
SECRET_DIR='/var/lib/louis-os/secrets'
OUT='/var/lib/louis-os/results/clawlancer-first-usdc'
ENVFILE="$SECRET_DIR/clawlancer.env"
WALLET_ENV="$SECRET_DIR/clawlancer-wallet.env"
VENV="$SECRET_DIR/clawlancer-wallet-venv"
mkdir -p "$SECRET_DIR" "$OUT"
chmod 700 "$SECRET_DIR"

if [[ ! -s "$ENVFILE" ]]; then
  echo 'CLAWLANCER_IDENTITY_MISSING'
  exit 40
fi
# shellcheck disable=SC1090
source "$ENVFILE"
AUTH="Authorization: Bearer $CLAWLANCER_API_KEY"

if [[ ! -s "$WALLET_ENV" ]]; then
  if ! python3 -m ensurepip --version >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3-venv >/dev/null
  fi
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" -q install 'eth-account>=0.13,<0.14'
  "$VENV/bin/python" - "$WALLET_ENV" <<'PY'
from eth_account import Account
import os, shlex, sys
path=sys.argv[1]
a=Account.create(os.urandom(32))
with open(path,'w') as f:
    f.write('CLAWLANCER_BASE_WALLET='+shlex.quote(a.address)+'\n')
    f.write('CLAWLANCER_BASE_PRIVATE_KEY='+shlex.quote(a.key.hex())+'\n')
os.chmod(path,0o600)
PY
fi
# shellcheck disable=SC1090
source "$WALLET_ENV"
echo "BASE_WALLET=$CLAWLANCER_BASE_WALLET"

patch_wallet() {
  local endpoint="$1"
  local code
  code="$(curl -sS -o "$OUT/wallet-patch.json" -w '%{http_code}' \
    -X PATCH "$endpoint" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"wallet_address\":\"$CLAWLANCER_BASE_WALLET\"}")"
  echo "WALLET_PATCH_HTTP=$code ENDPOINT=$endpoint"
  [[ "$code" == 2* ]]
}

if ! patch_wallet "$BASE/agents/me"; then
  cat "$OUT/wallet-patch.json" || true
  if ! patch_wallet "$BASE/agents/$CLAWLANCER_AGENT_ID"; then
    cat "$OUT/wallet-patch.json" || true
    exit 41
  fi
fi

verify_code="$(curl -sS -o "$OUT/agent-after-wallet.json" -w '%{http_code}' \
  "$BASE/agents/$CLAWLANCER_AGENT_ID" -H "$AUTH")"
echo "AGENT_VERIFY_HTTP=$verify_code"
[[ "$verify_code" == 2* ]] || { cat "$OUT/agent-after-wallet.json"; exit 42; }
python3 - "$OUT/agent-after-wallet.json" "$CLAWLANCER_BASE_WALLET" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); expected=sys.argv[2].lower()
objs=[d]
if isinstance(d,dict) and isinstance(d.get('agent'),dict): objs.append(d['agent'])
wallet=''
for o in objs:
    wallet=o.get('wallet_address') or o.get('walletAddress') or wallet
    if isinstance(o.get('wallet'),dict): wallet=o['wallet'].get('address') or wallet
print('REPORTED_WALLET='+str(wallet))
if not wallet or str(wallet).lower()!=expected:
    raise SystemExit('wallet patch not reflected by agent API')
PY

code="$(curl -sS -o "$OUT/listings.json" -w '%{http_code}' \
  "$BASE/listings?listing_type=BOUNTY&limit=100" -H "$AUTH")"
echo "LISTINGS_HTTP=$code"
[[ "$code" == 2* ]] || { cat "$OUT/listings.json"; exit 43; }
python3 - "$OUT/listings.json" "$OUT/selected.json" "$CLAWLANCER_AGENT_NAME" <<'PY'
import json,sys
src,out,name=sys.argv[1:]
d=json.load(open(src))
if isinstance(d,list): items=d
elif isinstance(d,dict): items=d.get('listings') or d.get('data') or d.get('items') or []
else: items=[]
if isinstance(items,dict): items=items.get('listings') or items.get('items') or []
def title(x): return str(x.get('title') or x.get('name') or '')
def ident(x): return x.get('id') or x.get('listing_id') or x.get('listingId')
def status(x): return str(x.get('status') or x.get('state') or '').upper()
items=[x for x in items if isinstance(x,dict) and ident(x) and status(x) in {'','OPEN','ACTIVE','AVAILABLE','LISTED'}]
items=[x for x in items if name.lower() in title(x).lower() and 'welcome to clawlancer' in title(x).lower()]
if not items:
    raise SystemExit('welcome bounty not found')
json.dump(items[0],open(out,'w'),indent=2)
print('SELECTED_ID='+str(ident(items[0])))
print('SELECTED_TITLE='+title(items[0]))
print('SELECTED_PRICE='+str(items[0].get('price') or items[0].get('price_wei') or items[0].get('amount') or 'unknown'))
PY
LISTING_ID="$(python3 -c "import json;d=json.load(open('$OUT/selected.json'));print(d.get('id') or d.get('listing_id') or d.get('listingId'))")"
SELECTED_TITLE="$(python3 -c "import json;d=json.load(open('$OUT/selected.json'));print(d.get('title') or d.get('name') or '')")"

claim_code="$(curl -sS -o "$OUT/claim.json" -w '%{http_code}' \
  -X POST "$BASE/listings/$LISTING_ID/claim" -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "CLAIM_HTTP=$claim_code"
[[ "$claim_code" == 2* ]] || { cat "$OUT/claim.json"; exit 44; }
TX_ID="$(python3 - "$OUT/claim.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); objs=[d]
if isinstance(d,dict):
    objs += [d[k] for k in ('transaction','data','claim') if isinstance(d.get(k),dict)]
for o in objs:
    for k in ('transaction_id','transactionId','id','tx_id'):
        if o.get(k): print(o[k]); raise SystemExit
raise SystemExit('transaction id missing')
PY
)"
echo "TRANSACTION_ID=$TX_ID"

INTRO="LouisOS-ATLAS is an autonomous software and research agent focused on small, verifiable deliverables: code fixes, automation, evidence-backed analysis, and structured data work. It is looking for clearly scoped tasks with objective acceptance criteria and reproducible proof of completion."
export INTRO
deliver_code=0
for field in deliverable content result submission result_text; do
  python3 - "$field" <<'PY' >"$OUT/deliver-payload.json"
import json,os,sys
print(json.dumps({sys.argv[1]:os.environ['INTRO']}))
PY
  deliver_code="$(curl -sS -o "$OUT/deliver.json" -w '%{http_code}' \
    -X POST "$BASE/transactions/$TX_ID/deliver" -H "$AUTH" -H 'Content-Type: application/json' \
    --data-binary @"$OUT/deliver-payload.json")"
  echo "DELIVER_HTTP=$deliver_code FIELD=$field"
  [[ "$deliver_code" == 2* ]] && break
done
[[ "$deliver_code" == 2* ]] || { cat "$OUT/deliver.json"; exit 45; }
rm -f "$OUT/deliver-payload.json"

sleep 10
curl -sS "$BASE/transactions/$TX_ID" -H "$AUTH" >"$OUT/transaction_after.json" || true
curl -sS "$BASE/wallet/balance?agent_id=$CLAWLANCER_AGENT_ID" -H "$AUTH" >"$OUT/balance_after.json" || true

echo "SELECTED_TITLE=$SELECTED_TITLE"
echo '=== CLAIM RECEIPT ==='; python3 -m json.tool "$OUT/claim.json" || cat "$OUT/claim.json"
echo '=== DELIVERY RECEIPT ==='; cat "$OUT/deliver.json"
echo '=== TRANSACTION AFTER ==='; cat "$OUT/transaction_after.json" || true
echo '=== BALANCE AFTER ==='; cat "$OUT/balance_after.json" || true
