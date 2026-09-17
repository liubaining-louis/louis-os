"""Regression: a reopened job must not erase prior attempts or ask again."""
import json
from pathlib import Path
import unittest

from atlas.automation_compatibility import reject_incompatible_delivery_methods
from atlas.cash_first_market import build_cash_first_portfolio, human_action_payload
from scripts.cash_first_market_postprocess import attach_prepared_artifacts
from scripts.internet_opportunity_router_cycle import build_cycle

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.bountybook.ai/job/19a16071-2be4-4fce-ae05-217b4e7098a8'


class BountyBookRecoveryTests(unittest.TestCase):
    def listing(self, identifier='market-3ed6e5a2ef3a1df6'):
        return {
            'opportunity_id': identifier, 'source_url': URL,
            'title': 'Build a minimal HTTP/1.1 server in Python using raw sockets',
            'description': 'Implement and test HTTPServer using raw Python sockets.',
            'reward_amount': 8, 'reward_verified': True, 'reward_currency': 'USDC',
            'estimated_effort_hours': 2, 'effort_hours': 2, 'time_to_cash_days': 10,
            'cost': 0, 'competition': 0.1, 'accessibility': 0.9, 'risk': 0.22,
            'capability_fit': 1, 'fresh_open_verified': True,
            'payment_path': 'USDC platform payout', 'payment_confidence': 0.9,
            'acceptance_criteria': ['GET POST 404'], 'legal_policy_pass': True,
            'human_actions_required': 1,
            'decision': {'status': 'prepare_then_gate', 'missing_capabilities': []},
            'metadata': {'submission_dossier_required': True,
                         'submission_dossier_prepared': True,
                         'prepared_artifact_registry_verified': True,
                         'human_action_instructions': ['Authorize this job again.']},
        }

    def test_reopened_job_cannot_request_authorization_again(self):
        registry = json.loads((ROOT / 'config/persistent_opportunity_rejections.json').read_text())
        prepared = json.loads((ROOT / 'config/prepared_opportunity_artifacts.json').read_text())
        rows, count = reject_incompatible_delivery_methods([self.listing()], persistent_rejections=registry)
        rows = attach_prepared_artifacts(rows, prepared)
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]['decision']['status'], 'rejected')
        self.assertEqual(rows[0]['metadata']['human_action_instructions'], [])
        human = human_action_payload(build_cash_first_portfolio({'opportunities': rows}))
        self.assertEqual(human['items'], [])

    def test_router_rejects_stale_raw_listing_even_under_different_id(self):
        for identifier in ['market-3ed6e5a2ef3a1df6', 'raw-source-copy']:
            with self.subTest(identifier=identifier):
                out = build_cycle([('raw_source.json', {'opportunities': [self.listing(identifier)]})])
                self.assertIsNone(out['selected'])
                self.assertEqual(out['decision_counts']['reject'], 1)
                self.assertEqual(out['top_ranked'][0]['persistent_rejection_reason'],
                                 'provider_verification_failure_retry_paused')

    def test_unrelated_eligible_work_remains_routable(self):
        other = self.listing('other-job')
        other['source_url'] = 'https://example.test/other-job'
        out = build_cycle([('raw_source.json', {'opportunities': [self.listing(), other]})])
        self.assertEqual(out['selected']['opportunity_id'], 'other-job')


if __name__ == '__main__':
    unittest.main()
