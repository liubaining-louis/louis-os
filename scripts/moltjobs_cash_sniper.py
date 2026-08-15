#!/usr/bin/env python3
import base64
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

AGENT_ID = os.getenv('MOLTJOBS_AGENT_ID', 'louis')
STATE_PATH = Path('/var/lib/louis-os/state/moltjobs_cash_sniper.json')
MISSION_BRIDGE = Path('/usr/local/bin/louis-mission-bridge')
MAX_BIDS_PER_RUN = int(os.getenv('MOLTJOBS_MAX_BIDS_PER_RUN', '5'))
MIN_BUDGET = float(os.getenv('MOLTJOBS_MIN_BUDGET', '1'))
MAX_BUDGET = float(os.getenv('MOLTJOBS_MAX_BUDGET', '15'))
MIN_CREDIT_RESERVE = int(os.getenv('MOLTJOBS_MIN_CREDIT_RESERVE', '5'))
TARGET_PORTFOLIO = int(os.getenv('MOLTJOBS_TARGET_PORTFOLIO', '8'))
MAX_PORTFOLIO = int(os.getenv('MOLTJOBS_MAX_PORTFOLIO', '10'))
RECENT_BID_HOURS = int(os.getenv('MOLTJOBS_RECENT_BID_HOURS', '72'))
TERMINAL_STATUSES = {
    'COMPLETED', 'CANCELLED', 'CANCELED', 'REJECTED', 'EXPIRED', 'CLOSED',
    'PAID', 'DONE', 'FAILED',
}


def run_json(args, check=True):
    cp = subprocess.run(args, text=True, capture_output=True)
    if check and cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout).strip())
    if cp.returncode != 0:
        return None, (cp.stderr or cp.stdout).strip(), cp.returncode
    text = cp.stdout.strip()
    try:
        return json.loads(text) if text else {}, '', 0
    except json.JSONDecodeError:
        return {'raw': text}, '', 0


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {'bids': {}, 'errors': [], 'runs': []}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def parse_deadline(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return None


def extract_jobs(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('jobs', 'data', 'items', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def portfolio_snapshot(state, now):
    """Estimate occupied MoltJobs capacity from assigned jobs plus recent live bids.

    This intentionally under-promises: terminal jobs do not occupy capacity, while a
    recent bid occupies one pipeline slot until its deadline or RECENT_BID_HOURS.
    If `jobs mine` is unavailable the controller falls back to recent bid state.
    """
    mine_payload, mine_err, mine_rc = run_json(
        ['louis-molt', 'jobs', 'mine', '--agent-id', AGENT_ID, '--json'], check=False
    )
    mine = extract_jobs(mine_payload) if mine_rc == 0 else []
    active_mine = []
    mine_ids = set()
    for job in mine:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get('id') or job.get('jobId') or '')
        if job_id:
            mine_ids.add(job_id)
        status = str(job.get('status') or '').upper()
        if status not in TERMINAL_STATUSES:
            active_mine.append(job)

    recent_bids = []
    cutoff = now - dt.timedelta(hours=RECENT_BID_HOURS)
    for job_id, record in (state.get('bids') or {}).items():
        if not isinstance(record, dict) or record.get('status') != 'BID_PLACED':
            continue
        if str(job_id) in mine_ids:
            continue
        attempted = parse_deadline(record.get('attemptedAt'))
        deadline = parse_deadline(record.get('deadlineAt'))
        if attempted and attempted < cutoff:
            continue
        if deadline and deadline <= now:
            continue
        recent_bids.append(record)

    occupied = min(MAX_PORTFOLIO, len(active_mine) + len(recent_bids))
    return {
        'occupied': occupied,
        'activeMine': len(active_mine),
        'recentPendingBids': len(recent_bids),
        'mineProbeOk': mine_rc == 0,
        'mineProbeError': '' if mine_rc == 0 else (mine_err or '')[:500],
        'target': TARGET_PORTFOLIO,
        'max': MAX_PORTFOLIO,
    }


def score_job(job, now):
    budget = float(job.get('budgetUsdc') or 0)
    deadline = parse_deadline(job.get('deadlineAt'))
    if job.get('status') != 'OPEN':
        return None
    if not deadline or deadline <= now + dt.timedelta(minutes=45):
        return None
    if not (MIN_BUDGET <= budget <= MAX_BUDGET):
        return None
    if job.get('paymentProvider') != 'ON_CHAIN_USDC':
        return None
    if job.get('paymentStatus') == 'PENDING_AUTH':
        return None

    title = (job.get('title') or '').lower()
    desc = json.dumps(job.get('inputData') or {}).lower()
    combined = title + ' ' + desc

    # Reject subjective, physical, or high-stakes tasks; favor structured digital micro-work.
    hard_reject = [
        'medical', 'legal advice', 'financial advice', 'physical', 'phone call',
        'instagram reel', 'video', 'voice call', 'meeting', 'onsite', 'in person',
    ]
    if any(term in combined for term in hard_reject):
        return None

    score = 100.0
    criteria = job.get('acceptanceCriteria') or []
    score += min(20, len(criteria) * 4)
    if criteria:
        score += 10
    structured_terms = [
        'json', 'csv', 'python', 'typescript', 'api', 'extract', 'classif',
        'summar', 'research', 'translate', 'validation', 'test', 'data', 'markdown',
    ]
    score += 4 * sum(term in combined for term in structured_terms)
    # Favor the micro-job sweet spot.
    if 2 <= budget <= 10:
        score += 15
    elif budget <= 15:
        score += 8
    hours_left = (deadline - now).total_seconds() / 3600
    if hours_left >= 4:
        score += 5
    return score


def escalate_to_tutor(job, blocker, phase='bid'):
    """Queue a sanitized tutor request on the VM without blocking the cash sniper."""
    if not MISSION_BRIDGE.exists():
        return None
    job_id = str(job.get('id') or 'unknown')
    safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', job_id)[:32]
    request_id = f'mbr_molt_{safe_id}_{phase}'
    context = {
        'job': {
            'id': job_id,
            'title': job.get('title'),
            'budgetUsdc': job.get('budgetUsdc'),
            'deadlineAt': job.get('deadlineAt'),
            'acceptanceCriteria': job.get('acceptanceCriteria') or [],
            'inputData': job.get('inputData') or {},
        },
        'phase': phase,
        'error': blocker[:3000],
    }
    context_b64 = base64.b64encode(json.dumps(context, ensure_ascii=False).encode()).decode()
    resp, _, rc = run_json([
        str(MISSION_BRIDGE), 'request',
        '--request-id', request_id,
        '--mission-id', job_id,
        '--source', 'moltjobs',
        '--objective', f"Advance MoltJobs micro-job: {job.get('title') or job_id}",
        '--blocker', blocker[:1200],
        '--requested-output', 'Diagnose the blocker and provide the safest concrete next step, including exact code/data if useful.',
        '--context-b64', context_b64,
        '--risk', 'low',
    ], check=False)
    return resp if rc == 0 else None


def main():
    now = dt.datetime.now(dt.timezone.utc)
    state = load_state()

    # Presence signal; failure is non-fatal.
    run_json(['louis-molt', 'agent', 'heartbeat', '--status', 'scanning jobs', '--agent-id', AGENT_ID, '--json'], check=False)

    allowance, err, rc = run_json(['louis-molt', 'bids', 'allowance', '--agent-id', AGENT_ID, '--json'], check=False)
    if rc != 0:
        raise RuntimeError(f'allowance_failed: {err}')
    remaining = int(allowance.get('freeBidsRemaining') or 0) + int(allowance.get('paidBidsBalance') or 0)

    jobs, err, rc = run_json(['louis-molt', 'jobs', 'list', '--limit', '100', '--json'], check=False)
    if rc != 0:
        raise RuntimeError(f'jobs_list_failed: {err}')

    portfolio = portfolio_snapshot(state, now)
    target_gap = max(0, TARGET_PORTFOLIO - portfolio['occupied'])
    hard_gap = max(0, MAX_PORTFOLIO - portfolio['occupied'])

    ranked = []
    for job in extract_jobs(jobs):
        score = score_job(job, now)
        if score is not None and job.get('id') not in state.get('bids', {}):
            ranked.append((score, job))
    ranked.sort(key=lambda x: (x[0], float(x[1].get('budgetUsdc') or 0)), reverse=True)

    placed = []
    errors = []
    capacity = max(0, min(
        MAX_BIDS_PER_RUN,
        remaining - MIN_CREDIT_RESERVE,
        target_gap,
        hard_gap,
    ))
    for score, job in ranked[:capacity]:
        job_id = job['id']
        budget = float(job['budgetUsdc'])
        amount = round(max(MIN_BUDGET, budget * 0.80), 2)
        criteria_count = len(job.get('acceptanceCriteria') or [])
        cover = (
            f"Louis OS can start immediately. I will deliver the requested structured digital output, "
            f"validate it against all {criteria_count} explicit acceptance criteria before submission, "
            f"and provide deterministic proof/format checks where applicable."
        )
        resp, err, rc = run_json([
            'louis-molt', 'bid', job_id,
            '--amount', str(amount),
            '--cover-letter', cover,
            '--agent-id', AGENT_ID,
            '--json'
        ], check=False)
        record = {
            'jobId': job_id,
            'title': job.get('title'),
            'budgetUsdc': budget,
            'bidUsdc': amount,
            'score': score,
            'attemptedAt': now.isoformat(),
            'deadlineAt': job.get('deadlineAt'),
        }
        if rc == 0:
            record['status'] = 'BID_PLACED'
            record['receipt'] = resp
            state.setdefault('bids', {})[job_id] = record
            placed.append(record)
        else:
            record['status'] = 'BID_FAILED'
            record['error'] = err[:1000]
            errors.append(record)
            low = err.lower()
            # Stop on certification/eligibility gates instead of burning retries.
            if 'cert' in low or 'fundamental' in low or 'eligible' in low or 'verified' in low:
                state['eligibility_blocker'] = record
                break
            # Unexpected technical/marketplace blockers are escalated to ChatGPT via the generic VM bridge.
            escalation = escalate_to_tutor(job, err, phase='bid')
            if escalation:
                record['missionBridge'] = escalation

    run_record = {
        'checkedAt': now.isoformat(),
        'jobsSeen': len(extract_jobs(jobs)),
        'qualifiedCandidates': len(ranked),
        'bidsPlaced': len(placed),
        'bidErrors': len(errors),
        'creditsBefore': remaining,
        'reserve': MIN_CREDIT_RESERVE,
        'portfolioBefore': portfolio,
        'targetGapBefore': target_gap,
        'capacityThisRun': capacity,
        'portfolioEstimatedAfter': min(MAX_PORTFOLIO, portfolio['occupied'] + len(placed)),
    }
    state.setdefault('runs', []).append(run_record)
    state['runs'] = state['runs'][-100:]
    state['lastRun'] = run_record
    state['lastErrors'] = errors
    state['portfolio'] = run_record['portfolioEstimatedAfter']
    state['portfolioTarget'] = TARGET_PORTFOLIO
    state['portfolioMax'] = MAX_PORTFOLIO
    save_state(state)
    print(json.dumps({'run': run_record, 'placed': placed, 'errors': errors, 'topCandidates': [
        {'id': j['id'], 'title': j.get('title'), 'budgetUsdc': j.get('budgetUsdc'), 'score': s}
        for s, j in ranked[:10]
    ]}, indent=2))


if __name__ == '__main__':
    main()
