#!/usr/bin/env bash
set -euo pipefail
source /var/lib/louis-os/secrets/agentpact.env
AUTH="x-api-key: $AGENTPACT_API_KEY"
echo "AUTH_AGENT_ID=$AGENTPACT_AGENT_ID"
for target in \
  "https://api.agentpact.xyz/api/agents/$AGENTPACT_AGENT_ID" \
  "https://api.agentpact.xyz/api/offers/99aef21d-05dc-4375-bea6-94dd0b46ac5f" \
  "https://api.agentpact.xyz/api/agents/0699af94-76a9-411f-bb20-40ed9e101b37"; do
  echo "=== $target ==="
  code=$(curl -sS -o /tmp/ap.json -w '%{http_code}' "$target" -H "$AUTH")
  echo "HTTP=$code"
  python3 -c 'import json; p="/tmp/ap.json"; d=json.load(open(p)); [d.pop(k,None) for k in ("apiKey","api_key","key","token","secret","privateKey","private_key")] if isinstance(d,dict) else None; print(json.dumps(d,indent=2,ensure_ascii=False)[:8000])' || cat /tmp/ap.json
 done
