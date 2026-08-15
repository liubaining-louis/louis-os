#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
receipts_path=ROOT/'results'/'external_action_receipts.json'
ledger_path=ROOT/'results'/'monetization.json'
now=datetime.now(timezone.utc).isoformat()

receipts=json.loads(receipts_path.read_text())
items=receipts.setdefault('receipts',[])
known={x.get('action_id') for x in items}
new=[
  {
    'timestamp':'2026-08-15T13:45:00+00:00',
    'action_id':'rustchain-12444-email-fallback-20260815',
    'candidate_id':'rustchain-bounty-12444',
    'action_type':'email_submission',
    'target_url':'https://github.com/Scottcjn/rustchain-bounties/issues/12444',
    'submission_channel':'documented_email_fallback',
    'recipient':'sophia.eagent@gmail.com',
    'gmail_message_id':'1a005aad18742d72',
    'delivery_status':'sent',
    'github_integration_result':'403_resource_not_accessible_by_integration',
    'authorization_mode':'owner_scope_low_income_missions',
    'payout_wallet':'RTC822282d5ce983c4084ad76c724b466c7d92dc1f9',
    'currency':'RTC','claimed_reward_rtc':3.0,
    'reward_status':'unconfirmed_pending_counterparty_review',
    'verified':True,'counterparty_review_status':'pending','revenue_confirmed_eur':0.0
  },
  {
    'timestamp':'2026-08-15T13:46:00+00:00',
    'action_id':'rustchain-12442-email-fallback-20260815',
    'candidate_id':'rustchain-bounty-12442',
    'action_type':'email_submission',
    'target_url':'https://github.com/Scottcjn/rustchain-bounties/issues/12442',
    'submission_channel':'documented_email_fallback',
    'recipient':'sophia.eagent@gmail.com',
    'gmail_message_id':'1a005ab73bf11c39',
    'delivery_status':'sent',
    'github_integration_result':'403_resource_not_accessible_by_integration',
    'authorization_mode':'owner_scope_low_income_missions',
    'payout_wallet':'RTC822282d5ce983c4084ad76c724b466c7d92dc1f9',
    'currency':'RTC','claimed_reward_rtc':3.0,
    'reward_status':'unconfirmed_pending_counterparty_review',
    'verified':True,'counterparty_review_status':'pending','revenue_confirmed_eur':0.0
  },
  {
    'timestamp':'2026-08-15T13:55:26+00:00',
    'action_id':'rustchain-rip302-banner-job-9ad634ec9a9f880a-20260815',
    'candidate_id':'rustchain-rip302-job_9ad634ec9a9f880a',
    'action_type':'marketplace_design_delivery',
    'platform':'rustchain_rip302',
    'job_id':'job_9ad634ec9a9f880a',
    'target_url':'https://explorer.rustchain.org/agent/jobs/job_9ad634ec9a9f880a',
    'submission_channel':'rustchain_rip302_api_claim_and_deliver',
    'delivery_status':'delivered_waiting_poster_acceptance',
    'deliverable_url':'https://raw.githubusercontent.com/liubaining-louis/louis-os/main/deliverables/rustchain_rip302_banner/rustchain_banner_1500x500.png',
    'authorization_mode':'owner_scope_low_income_missions',
    'evidence':[
      'https://github.com/liubaining-louis/louis-os/actions/runs/31888252209',
      'https://github.com/liubaining-louis/louis-os/actions/runs/31888470260',
      'https://github.com/liubaining-louis/louis-os/actions/runs/31888508081',
      'https://github.com/liubaining-louis/louis-os/commit/2d85ed9'
    ],
    'payout_wallet':'RTC822282d5ce983c4084ad76c724b466c7d92dc1f9',
    'currency':'RTC','claimed_reward_rtc':3.0,
    'reward_status':'escrowed_by_poster_pending_acceptance',
    'verified':True,'counterparty_review_status':'delivered_pending_acceptance',
    'revenue_confirmed_eur':0.0
  }
]
added=0
for item in new:
    if item['action_id'] not in known:
        items.append(item); known.add(item['action_id']); added+=1
receipts['updated_at']=now
receipts_path.write_text(json.dumps(receipts,indent=2,ensure_ascii=False)+'\n')

ledger=json.loads(ledger_path.read_text())
# Set from evidence-backed totals, not additive on repeated runs.
ledger['external_actions_submitted']=max(int(ledger.get('external_actions_submitted',0)),8)
ledger['internet_actions_submitted']=max(int(ledger.get('internet_actions_submitted',0)),8)
ledger['rustchain_external_actions_submitted']=6
ledger['low_income_external_actions_submitted']=3
ledger['potential_rustchain_reward_rtc_unconfirmed']=61.0
ledger['potential_rustchain_escrow_delivered_rtc_unconfirmed']=3.0
ledger['last_external_action_receipt']='https://explorer.rustchain.org/agent/jobs/job_9ad634ec9a9f880a'
ledger['last_external_authorization_mode']='owner_scope_low_income_missions'
ledger['last_external_submission_channel']='rustchain_rip302_api_claim_and_deliver'
ledger['last_external_submission_currency']='RTC'
ledger['last_external_submission_id']='job_9ad634ec9a9f880a'
ledger['last_external_submission_target']='https://explorer.rustchain.org/agent/jobs/job_9ad634ec9a9f880a'
ledger['execution_status']='rustchain_rip302_delivered_waiting_acceptance'
ledger['next_action']='Monitor RIP-302 poster acceptance and continue targeting funded low-friction micro-jobs without counting reward as revenue before payout evidence.'
ledger['note']='Eight verified external paid-mission actions exist. Three new low-income actions were executed on 2026-08-15: two 3 RTC RustChain bounty submissions via documented email fallback and one funded 3 RTC RIP-302 job claimed and delivered. All 9 RTC are unconfirmed; confirmed revenue remains zero until payout evidence.'
ledger['revenue_confirmed_eur']=0.0
ledger['revenue_received']=0.0
ledger['updated_at']=now
ledger_path.write_text(json.dumps(ledger,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'added_receipts':added,'external_actions_submitted':ledger['external_actions_submitted'],'potential_rustchain_reward_rtc_unconfirmed':ledger['potential_rustchain_reward_rtc_unconfirmed'],'confirmed_revenue_eur':ledger['revenue_confirmed_eur']},indent=2))
