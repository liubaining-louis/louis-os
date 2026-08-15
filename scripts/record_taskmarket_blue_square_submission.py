#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('.')
receipts_path = ROOT / 'results' / 'external_action_receipts.json'
mon_path = ROOT / 'results' / 'monetization.json'
evidence_path = ROOT / 'results' / 'evidence.jsonl'

timestamp = '2026-08-15T08:01:23.974Z'
task_id = '0x34a65b919752f9b4500aae1574f44865a92c1b625e77c9a72741370c0daadccc'
submission_id = '99cba5cc-7c8a-4fd2-97ea-492df2ef1eb3'
wallet = '0xCB5e092121C0dc63e62d215b8B8ceFf8a1a96c0C'
run_url = 'https://github.com/liubaining-louis/louis-os/actions/runs/31873391331'
evidence_comment = 'https://github.com/liubaining-louis/louis-os/issues/77#issuecomment-5301277050'
deliverable_url = 'https://github.com/liubaining-louis/louis-os/blob/main/deliverables/taskmarket_blue_square_arcade/index.html'
commit_url = 'https://github.com/liubaining-louis/louis-os/commit/88f312df5826eae8832b67d4cfc40a9c1f9d55ec'

receipt = {
    'timestamp': timestamp,
    'action_id': 'taskmarket-blue-square-arcade-20260815',
    'candidate_id': f'taskmarket-{task_id}',
    'action_type': 'marketplace_file_submission',
    'platform': 'taskmarket',
    'task_id': task_id,
    'target_url': f'https://taskmarket.dev/tasks/{task_id}',
    'submission_channel': 'taskmarket_cli_file_submission',
    'submission_id': submission_id,
    'delivery_status': 'submitted_and_verified',
    'receipt_url': evidence_comment,
    'authorization_mode': 'explicit_owner_authorization',
    'evidence': [run_url, evidence_comment, deliverable_url, commit_url],
    'payout_wallet': wallet,
    'payout_network': 'Base',
    'currency': 'USDC',
    'claimed_reward_usdc': 100.0,
    'reward_status': 'unconfirmed_competitive_bounty',
    'deliverable_hash': '0x7bdc7cf4538dc0222e2feb1c49b8dd9756454b3672d0c1ec82025b100c4606a3',
    'submit_tx_hash': '0x1a19163b42ed665fab7857694be332d164d007476d2dbf70f601a0a3e2af350b',
    'verified': True,
    'counterparty_review_status': 'pending',
    'wallet_balance_usdc_at_submission': 0.0,
    'revenue_confirmed_eur': 0.0,
    'private_keystore_exported': False,
}

receipts = json.loads(receipts_path.read_text())
items = receipts.setdefault('receipts', [])
if not any(x.get('action_id') == receipt['action_id'] for x in items):
    items.append(receipt)
receipts['updated_at'] = timestamp
receipts_path.write_text(json.dumps(receipts, indent=2, ensure_ascii=False) + '\n')

m = json.loads(mon_path.read_text())
m['external_actions_submitted'] = max(int(m.get('external_actions_submitted', 0)), 4)
m['internet_actions_submitted'] = max(int(m.get('internet_actions_submitted', 0)), 4)
m['execution_status'] = 'non_rustchain_usdc_external_submission_verified_pending_review'
m['last_external_action_receipt'] = evidence_comment
m['last_external_authorization_mode'] = 'explicit_owner_authorization'
m['last_external_submission_channel'] = 'taskmarket_cli_file_submission'
m['last_external_submission_target'] = f'https://taskmarket.dev/tasks/{task_id}'
m['last_external_submission_id'] = submission_id
m['last_external_submission_currency'] = 'USDC'
m['last_external_wallet_base'] = wallet
m['last_external_wallet_balance_usdc'] = 0.0
m['non_rustchain_external_actions_submitted'] = max(int(m.get('non_rustchain_external_actions_submitted', 0)), 1)
m['non_rustchain_usdc_submissions_verified'] = max(int(m.get('non_rustchain_usdc_submissions_verified', 0)), 1)
m['potential_taskmarket_reward_usdc_unconfirmed'] = 100.0
m['submission_blocked_stage'] = 'counterparty_review'
m['primary_blocker'] = 'Awaiting Taskmarket requester review/selection and independently verified USDC payout; the non-RustChain submission itself is complete.'
m['root_cause_code'] = 'first_non_rustchain_usdc_submission_achieved'
m['next_action'] = 'monitor_taskmarket_submission_and_wallet_for_selection_or_payout_then_execute_next_zero_stake_usdc_task'
m['note'] = ('Four verified external paid-mission submissions now exist: three RustChain submissions plus one independently verified '
             'Taskmarket USDC submission. Taskmarket submission 99cba5cc-7c8a-4fd2-97ea-492df2ef1eb3 targets a 100 USDC competitive bounty. '
             'No reward is counted as revenue until selection and payout evidence are independently verified.')
m['revenue_confirmed_eur'] = float(m.get('revenue_confirmed_eur', 0.0) or 0.0)
m['revenue_received'] = float(m.get('revenue_received', 0.0) or 0.0)
m['updated_at'] = datetime.now(timezone.utc).isoformat()
mon_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + '\n')

event = {
    'timestamp': timestamp,
    'event_type': 'external_submission_verified',
    'platform': 'taskmarket',
    'currency': 'USDC',
    'task_id': task_id,
    'submission_id': submission_id,
    'payout_wallet': wallet,
    'claimed_reward_usdc': 100.0,
    'reward_confirmed': False,
    'revenue_confirmed_eur': 0.0,
    'evidence': [run_url, evidence_comment],
}
existing = evidence_path.read_text(encoding='utf-8') if evidence_path.exists() else ''
marker = f'"submission_id": "{submission_id}"'
if marker not in existing:
    with evidence_path.open('a', encoding='utf-8') as f:
        if existing and not existing.endswith('\n'):
            f.write('\n')
        f.write(json.dumps(event, ensure_ascii=False) + '\n')

print('TASKMARKET_RECEIPT_RECORDED=true')
print('EXTERNAL_ACTIONS_SUBMITTED=4')
print('NON_RUSTCHAIN_USDC_SUBMISSIONS_VERIFIED=1')
print('REVENUE_CONFIRMED_EUR=0')
