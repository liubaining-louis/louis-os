#!/usr/bin/env python3
import json
import datetime
from pathlib import Path

jobs = json.load(open('/tmp/moltjobs_jobs.json'))
now = datetime.datetime.now(datetime.timezone.utc)
rows = []
for j in jobs:
    try:
        deadline = datetime.datetime.fromisoformat((j.get('deadlineAt') or '').replace('Z', '+00:00'))
    except Exception:
        deadline = None
    budget = float(j.get('budgetUsdc') or 0)
    payment = j.get('paymentProvider')
    pstatus = j.get('paymentStatus')
    status = j.get('status')
    valid = status == 'OPEN' and deadline is not None and deadline > now and budget > 0
    criteria = j.get('acceptanceCriteria') or []
    title = (j.get('title') or '').lower()
    desc = json.dumps(j.get('inputData') or {}).lower()
    complexity_penalty = 0
    for term in ['video', 'reel', 'instagram', 'design', 'website', 'deploy', 'mobile app']:
        if term in title or term in desc:
            complexity_penalty += 2
    score = 0
    if valid:
        score += 50
        if 1 <= budget <= 15:
            score += 25
        elif budget <= 30:
            score += 15
        else:
            score += 5
        if payment == 'ON_CHAIN_USDC':
            score += 10
        if criteria:
            score += min(10, len(criteria) * 2)
        if pstatus in (None, 'FUNDED', 'AUTHORIZED', 'CAPTURED', 'ESCROWED'):
            score += 5
        score -= complexity_penalty
    rows.append({
        'id': j.get('id'),
        'title': j.get('title'),
        'budgetUsdc': budget,
        'status': status,
        'deadlineAt': j.get('deadlineAt'),
        'paymentProvider': payment,
        'paymentStatus': pstatus,
        'acceptanceCriteriaCount': len(criteria),
        'validNow': bool(valid),
        'score': score,
        'inputData': j.get('inputData'),
        'acceptanceCriteria': criteria,
    })
rows.sort(key=lambda r: (r['validNow'], r['score'], r['budgetUsdc']), reverse=True)
out = {
    'checkedAt': now.isoformat(),
    'total': len(rows),
    'validCount': sum(r['validNow'] for r in rows),
    'jobs': rows[:25],
}
Path('/var/lib/louis-os/state/moltjobs_live_scout.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
