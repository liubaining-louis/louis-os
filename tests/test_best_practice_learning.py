from __future__ import annotations

import unittest

from atlas.best_practice_learning import SuccessEvidence, build_playbook, evidence_score, learning_manifest


class BestPracticeLearningTests(unittest.TestCase):
    def evidence(self, group: str, evidence_type: str = "documented_case_study") -> SuccessEvidence:
        return SuccessEvidence(
            source_url=f"https://example.com/{group}",
            source_domain="example.com",
            published_at="2026-01-01",
            evidence_type=evidence_type,
            actor=group,
            context="B2B services",
            mechanism="show a bounded proof before the proposal",
            outcome="higher qualified response rate",
            independent_group=group,
            has_concrete_metrics=True,
            has_failure_conditions=True,
        )

    def test_single_success_story_remains_hypothesis(self) -> None:
        playbook = build_playbook("show a bounded proof before the proposal", [self.evidence("one")])
        self.assertEqual(playbook.transfer_status, "hypothesis_only")
        self.assertEqual(playbook.survivorship_risk, "high")

    def test_independent_evidence_can_enable_bounded_experiment(self) -> None:
        rows = [
            self.evidence("one", "primary_research"),
            self.evidence("two", "documented_case_study"),
            self.evidence("three", "operator_account_with_receipts"),
        ]
        playbook = build_playbook("show a bounded proof before the proposal", rows)
        self.assertEqual(playbook.transfer_status, "bounded_experiment_ready")
        self.assertGreaterEqual(playbook.independent_groups, 2)

    def test_promotional_conflict_reduces_score(self) -> None:
        clean = self.evidence("one")
        promoted = SuccessEvidence(**{**clean.__dict__, "promotional_conflict": True})
        self.assertLess(evidence_score(promoted), evidence_score(clean))

    def test_manifest_never_counts_external_success_as_revenue(self) -> None:
        manifest = learning_manifest([build_playbook("show a bounded proof before the proposal", [self.evidence("one")])])
        self.assertTrue(manifest["truth"]["external_success_is_not_louis_os_revenue"])


if __name__ == "__main__":
    unittest.main()
