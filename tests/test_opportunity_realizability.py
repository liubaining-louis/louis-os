import unittest

from atlas.opportunity_realizability import assess_opportunity_realizability


class OpportunityRealizabilityTests(unittest.TestCase):
    def test_taskmarket_zero_stake_can_execute(self):
        r = assess_opportunity_realizability(
            {"state":"open","comments":4,"external_submit_route_verified":True,"payout_method_verified":True,"currency_liquidity_verified":True},
            provider="taskmarket",
        )
        self.assertEqual(r.decision, "execute")
        self.assertGreaterEqual(r.cash_realizability_score, 65)

    def test_ai_prohibited_is_rejected(self):
        r = assess_opportunity_realizability({"state":"open","body":"Human contributors only."}, provider="agentshield")
        self.assertEqual(r.decision, "reject")
        self.assertIn("ai_or_automation_ineligible", r.hard_reasons)

    def test_assigned_bounty_is_rejected(self):
        r = assess_opportunity_realizability({"state":"open","assignee":{"login":"someone"}}, provider="tenstorrent")
        self.assertEqual(r.decision, "reject")
        self.assertIn("assigned_to_other_contributor", r.hard_reasons)

    def test_closed_official_source_beats_aggregator(self):
        r = assess_opportunity_realizability({"state":"closed","official_state_open":False}, provider="tenstorrent")
        self.assertEqual(r.decision, "reject")
        self.assertIn("official_source_closed_or_stale", r.hard_reasons)

    def test_openjobs_requires_human_gate(self):
        r = assess_opportunity_realizability({"state":"open"}, provider="openjobs")
        self.assertEqual(r.decision, "human_gate")
        self.assertIn("signed_registration_or_new_identity_required", r.human_gate_reasons)

    def test_terms_account_gate_blocks_execution(self):
        r = assess_opportunity_realizability(
            {"state":"open"}, provider="github_public_issue",
            readiness_prerequisites=("third_party_account_required","external_terms_or_contract_required"),
        )
        self.assertEqual(r.decision, "human_gate")

    def test_broken_withdrawal_is_rejected(self):
        r = assess_opportunity_realizability({"state":"open"}, provider="mergeos")
        self.assertEqual(r.decision, "reject")
        self.assertIn("payout_or_withdrawal_not_reliably_realizable", r.hard_reasons)

    def test_high_competition_downranks(self):
        r = assess_opportunity_realizability(
            {"state":"open","active_competitor_count":30,"external_submit_route_verified":True,"payout_method_verified":True,"currency_liquidity_verified":True},
            provider="bountic",
        )
        self.assertEqual(r.decision, "downrank")
        self.assertTrue(any(x.startswith("active_competition=") for x in r.soft_reasons))

    def test_passive_buyer_initiated_market(self):
        r = assess_opportunity_realizability({"state":"open"}, provider="agentpact")
        self.assertEqual(r.decision, "passive")


if __name__ == "__main__":
    unittest.main()
