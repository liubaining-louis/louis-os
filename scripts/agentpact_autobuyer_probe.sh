#!/usr/bin/env bash
set -euo pipefail

BASE='https://api.agentpact.xyz/api'
OUT='/var/lib/louis-os/results/agentpact-json-csv'
source /var/lib/louis-os/secrets/agentpact.env
AUTH="x-api-key: $AGENTPACT_API_KEY"
AGENT_ID="$AGENTPACT_AGENT_ID"
mkdir -p "$OUT"

curl -fsSL "$BASE/matches/recommendations?agentId=$AGENT_ID" -H "$AUTH" >"$OUT/recommendations-live.json"

python3 - "$OUT/recommendations-live.json" <<'PY' >"$OUT/recommendation-ids.tsv"
import json,sys
d=json.load(open(sys.argv[1]))
items=d if isinstance(d,list) else (d.get('recommendations') or d.get('data') or [])
seen=set()
for x in items[:80]:
    if not isinstance(x,dict): continue
    need=str(x.get('need_id') or x.get('needId') or '')
    score=x.get('score') or 0
    if need and need not in seen:
        seen.add(need)
        print(f'{need}\t{score}')
PY

: >"$OUT/autobuyer-candidates.jsonl"
while IFS=$'\t' read -r need_id score; do
  [[ -n "$need_id" ]] || continue
  ncode=$(curl -sS -o /tmp/ap-need.json -w '%{http_code}' "$BASE/needs/$need_id" -H "$AUTH")
  [[ "$ncode" == 2* ]] || continue
  buyer=$(python3 - <<'PY'
import json
n=json.load(open('/tmp/ap-need.json')); n=n.get('need',n) if isinstance(n,dict) else {}
print(n.get('agent_id') or n.get('agentId') or n.get('buyerAgentId') or '')
PY
)
  [[ -n "$buyer" ]] || continue
  acode=$(curl -sS -o /tmp/ap-buyer.json -w '%{http_code}' "$BASE/agents/$buyer" -H "$AUTH")
  [[ "$acode" == 2* ]] || continue
  python3 - "$need_id" "$score" "$buyer" <<'PY' >>"$OUT/autobuyer-candidates.jsonl"
import json,sys
need_id,score,buyer=sys.argv[1:]
n=json.load(open('/tmp/ap-need.json')); n=n.get('need',n) if isinstance(n,dict) else {}
a=json.load(open('/tmp/ap-buyer.json')); a=a.get('agent',a) if isinstance(a,dict) else {}
obj={
 'need_id':need_id,
 'match_score':float(score or 0),
 'title':n.get('title'),
 'category':n.get('category'),
 'tags':n.get('tags') or n.get('tags_json'),
 'status':n.get('status') or n.get('state'),
 'budget_min':n.get('budget_min',n.get('budgetMin',n.get('min_price',n.get('minPrice')))),
 'budget_max':n.get('budget_max',n.get('budgetMax',n.get('max_price',n.get('maxPrice')))),
 'buyer_agent_id':buyer,
 'buyer_auto_buy':bool(a.get('auto_buy_enabled') or a.get('autoBuyEnabled')),
 'buyer_max_auto_deal_price':a.get('max_auto_deal_price',a.get('maxAutoDealPrice')),
 'buyer_auto_buy_categories':a.get('auto_buy_categories',a.get('autoBuyCategories')),
 'buyer_presence':a.get('presence_status',a.get('presenceStatus')),
 'buyer_last_seen':a.get('last_seen_at',a.get('lastSeenAt')),
 'buyer_reputation':a.get('reputation_score',a.get('reputationScore')),
}
print(json.dumps(obj,ensure_ascii=False))
PY
done <"$OUT/recommendation-ids.tsv"

python3 - "$OUT/autobuyer-candidates.jsonl" <<'PY'
import json,sys
rows=[]
for line in open(sys.argv[1]):
    try: rows.append(json.loads(line))
    except: pass

def price_ok(x):
    try:
        mx=float(x['budget_max']) if x.get('budget_max') is not None else 0
    except: mx=0
    return mx>=2

def active(x): return str(x.get('buyer_presence') or '').lower()=='online'
rows.sort(key=lambda x:(x['buyer_auto_buy'], active(x), price_ok(x), x['match_score']), reverse=True)
print('CANDIDATES='+str(len(rows)))
print('AUTO_BUYERS='+str(sum(1 for x in rows if x['buyer_auto_buy'])))
print('ONLINE_BUYERS='+str(sum(1 for x in rows if active(x))))
for x in rows[:25]:
    print(json.dumps(x,ensure_ascii=False))
PY
