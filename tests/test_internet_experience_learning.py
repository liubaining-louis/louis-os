from __future__ import annotations

from datetime import datetime, timezone
import unittest

from atlas.internet_experience_learning import InternetObservation, OutcomeFeedback, learning_directives, source_reliability, synthesize_claims


NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


class InternetExperienceLearningTests(unittest.TestCase):
    def test_primary_authoritative_source_scores_high(self) -> None:
        observation = InternetObservation(
            observation_id="1",
            claim_key="legal-rule",
            claim="Official rule",
            source_url="https://service-public.fr/example",
            observed_at="2026-07-28T00:00:00+00:00",
            primary_source=True,
            evidence_type="official_document",
        )
        self.assertGreaterEqual(source_reliability(observation), 0.9)

    def test_two_independent_sources_promote_supported(self) -> None:
        rows = [
            InternetObservation("1", "proposal-style", "Short proposals perform better", "https://example-a.com/a", "2026-07-28T00:00:00+00:00", independent_group="a"),
            InternetObservation("2", "proposal-style", "Short proposals perform better", "https://example-b.com/b", "2026-07-28T00:00:00+00:00", independent_group="b"),
        ]
        claims = synthesize_claims(rows, now=NOW)
        self.assertEqual(claims[0]["promotion_level"], "supported")

    def test_verified_success_promotes_validated(self) -> None:
        observation = InternetObservation("1", "fixed-price", "Fixed price improves conversion", "https://example.com/a", "2026-07-28T00:00:00+00:00")
        outcome = OutcomeFeedback("fixed-price", "client_replied", True, "2026-07-28T01:00:00+00:00", receipt="receipt://reply/1")
        claims = synthesize_claims([observation], [outcome], now=NOW)
        self.assertEqual(claims[0]["promotion_level"], "validated")
        self.assertEqual(learning_directives(claims)[0]["action"], "increase_strategy_weight_with_exploration_reserve")

    def test_learning_does_not_authorize_submission(self) -> None:
        observation = InternetObservation("1", "x", "Claim", "https://example.com", "2026-07-28T00:00:00+00:00")
        directives = learning_directives(synthesize_claims([observation], now=NOW))
        self.assertFalse(directives[0]["external_submission_authorized"])


if __name__ == "__main__":
    unittest.main()
