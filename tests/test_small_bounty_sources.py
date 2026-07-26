from __future__ import annotations

import unittest

from atlas.small_bounty_sources import (
    AlgoraPublicSource,
    OpirePublicSource,
    infer_bounded_capability,
)


class SmallBountySourceTests(unittest.TestCase):
    def test_opire_accepts_only_open_available_bounded_reward(self) -> None:
        home = b'''<html><body>
        <a href="/issues/valid">Valid</a>
        <a href="/issues/closed">Closed</a>
        <a href="/issues/crowded">Crowded</a>
        </body></html>'''
        valid = b'''<html><body>
        <h1>$40.00 bounty for [Bounty] Add French documentation</h1>
        <p>Earn up to $40.00 by solving this issue.</p>
        <p>Issue URL: https://github.com/example/docs/issues/12</p>
        <p>Status: Open.</p>
        <p>1 available rewards and 0 paid rewards.</p>
        <p>2 solvers are trying this issue and 1 solvers have claimed it.</p>
        <h2>Rewards</h2><p>$40.00 reward, status Available</p>
        </body></html>'''
        closed = b'''<html><body>
        <h1>$50.00 bounty for Fix a typo</h1><p>Earn up to $50.00 now.</p>
        <p>Issue URL: https://github.com/example/docs/issues/13</p>
        <p>Status: Closed.</p><p>1 available rewards and 0 paid rewards.</p>
        <p>$50.00 reward, status Available</p></body></html>'''
        crowded = b'''<html><body>
        <h1>$30.00 bounty for Fix README wording</h1><p>Earn up to $30.00 now.</p>
        <p>Issue URL: https://github.com/example/docs/issues/14</p>
        <p>Status: Open.</p><p>1 available rewards and 0 paid rewards.</p>
        <p>9 solvers are trying this issue and 8 solvers have claimed it.</p>
        <p>$30.00 reward, status Available</p></body></html>'''
        pages = {
            "https://app.opire.dev/home": home,
            "https://app.opire.dev/issues/valid": valid,
            "https://app.opire.dev/issues/closed": closed,
            "https://app.opire.dev/issues/crowded": crowded,
        }
        source = OpirePublicSource(fetcher=pages.__getitem__, maximum_solvers=5)
        opportunities, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(state.observed_count, 1)
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 40.0)
        self.assertEqual(item.required_capabilities, ("deterministic_text_replacement",))
        self.assertTrue(item.reward_verified)
        self.assertTrue(item.metadata["payout_setup_required"])
        self.assertEqual(item.metadata["payment_methods"], ["Stripe payout via Opire"])

    def test_opire_rejects_title_amount_without_available_platform_reward(self) -> None:
        home = b'<a href="/issues/fake">Fake</a>'
        fake = b'''<h1>$1,650 bounty for Bug Reward 1650 USD</h1>
        <p>Earn up to $0.00 by solving it.</p>
        <p>Issue URL: https://github.com/example/fork/issues/1</p>
        <p>Status: Open.</p><p>0 available rewards and 0 paid rewards.</p>'''
        pages = {
            "https://app.opire.dev/home": home,
            "https://app.opire.dev/issues/fake": fake,
        }
        opportunities, state = OpirePublicSource(fetcher=pages.__getitem__).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_algora_filters_crowding_and_preserves_platform_evidence(self) -> None:
        board = b'''<html><body>
        <div><span>$50</span><a href="https://github.com/example/docs/issues/21">docs#21 Fix typo in README</a><span>1 claim</span></div>
        </body></html>'''
        source = AlgoraPublicSource(handles=("example",), fetcher=lambda _: board)
        opportunities, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 50.0)
        self.assertEqual(item.required_capabilities, ("deterministic_text_replacement",))
        self.assertIn("https://algora.io/example/bounties?status=open", item.payment_evidence)
        self.assertEqual(item.metadata["payment_methods"], ["Algora platform payout"])

    def test_source_failure_is_contained(self) -> None:
        source = AlgoraPublicSource(handles=("one", "two"), fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("x")))
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("TimeoutError", state.reason)

    def test_capability_inference_fails_to_bounded_proposal(self) -> None:
        self.assertEqual(infer_bounded_capability("Fix broken link"), "broken_link_replacement")
        self.assertEqual(infer_bounded_capability("Implement a new database engine"), "technical_proposal")


if __name__ == "__main__":
    unittest.main()
