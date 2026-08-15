#!/usr/bin/env bash
set -euo pipefail

BASE='https://api.agentpact.xyz/api'
OUT='/var/lib/louis-os/results/agentpact-json-csv'
source /var/lib/louis-os/secrets/agentpact.env
AUTH="x-api-key: $AGENTPACT_API_KEY"
AGENT_ID="$AGENTPACT_AGENT_ID"
TARGET_NEED='e0750d6c-0e7b-48e1-9fdc-843c0b69ee41'
mkdir -p "$OUT"

echo "AGENT_ID=$AGENT_ID"

# Presence heartbeat is explicitly non-financial: it only marks the seller as active.
heartbeat_code="$(curl -sS -o "$OUT/heartbeat.json" -w '%{http_code}' \
  -X POST "$BASE/agents/$AGENT_ID/heartbeat" \
  -H "$AUTH" -H 'Content-Type: application/json' -d '{}')"
echo "HEARTBEAT_HTTP=$heartbeat_code"
cat "$OUT/heartbeat.json" || true

# Probe both documented/current read-only recommendation surfaces.
for spec in \
  "agent_matches|$BASE/agents/$AGENT_ID/matches" \
  "recommendations|$BASE/matches/recommendations?agentId=$AGENT_ID"; do
  name="${spec%%|*}"
  url="${spec#*|}"
  code="$(curl -sS -o "$OUT/$name.json" -w '%{http_code}' "$url" -H "$AUTH")"
  echo "${name^^}_HTTP=$code"
  python3 - "$OUT/$name.json" "$TARGET_NEED" <<'PY'
import json, sys
path, target = sys.argv[1:]
try:
    d=json.load(open(path))
except Exception:
    print(open(path).read()[:5000])
    raise SystemExit
print(json.dumps(d, indent=2, ensure_ascii=False)[:12000])

def walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)

hits=[]
for obj in walk(d):
    values={str(v) for v in obj.values() if isinstance(v,(str,int,float))}
    if target in values or any(target in str(v) for v in obj.values() if isinstance(v,str)):
        hits.append(obj)
print('TARGET_NEED_MATCH_COUNT='+str(len(hits)))
for h in hits[:5]:
    print('TARGET_MATCH='+json.dumps(h,ensure_ascii=False)[:2500])
PY
done

# Confirm presence state after heartbeat.
profile_code="$(curl -sS -o "$OUT/profile-after-heartbeat.json" -w '%{http_code}' "$BASE/agents/$AGENT_ID" -H "$AUTH")"
echo "PROFILE_HTTP=$profile_code"
python3 - "$OUT/profile-after-heartbeat.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); a=d.get('agent',d) if isinstance(d,dict) else {}
for key in ('presence_status','last_seen_at','auto_buy_enabled','preferred_chain','reputation_score'):
    print(f'{key.upper()}={a.get(key)}')
PY
