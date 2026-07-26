from __future__ import annotations

import unittest

from atlas.usagov_challenge_source import USAGovChallengeSource


LISTING = b"""
<html><body>
<a href="/challenges/software-prize">Software Prize</a>
<a href="https://www.usa.gov/challenges/hardware-prize">Hardware Prize</a>
<a href="https://untrusted.example/challenges/fake">Fake</a>
</body></html>
"""

SOFTWARE = b"""
<html><body>
<h1>Caregiver AI Prize Challenge</h1>
<p>Develop an artificial intelligence software and application development solution.</p>
<dl>
<dt>End date</dt><dd>02/06/2029 5:00 PM ET</dd>
<dt>Challenge type</dt><dd>Software and application development</dd>
<dt>Prizes</dt><dd>Total cash prizes: $2,500,000</dd>
</dl>
<p>Apply on the official hosting platform. Rules and eligibility apply.</p>
</body></html>
"""

HARDWARE = b"""
<html><body>
<h1>Worldwide Robotics Hardware Challenge</h1>
<p>Open to teams around the world. Build a robotics physical prototype demonstration.</p>
<p>Prizes Cash prize: $100,000</p>
</body></html>
"""


class USAGovChallengeSourceTests(unittest.TestCase):
    def getter(self, url: str) -> bytes:
        if url.endswith("find-active-challenge"):
            return LISTING
        if url.endswith("software-prize"):
            return SOFTWARE
        if url.endswith("hardware-prize"):
            return HARDWARE
        raise AssertionError(url)

    def test_collects_official_non_github_paid_opportunities(self) -> None:
        opportunities, state = USAGovChallengeSource(fetcher=self.getter).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(state.observed_count, 2)
        software = next(item for item in opportunities if "Caregiver" in item.title)
        self.assertTrue(software.reward_verified)
        self.assertEqual(software.reward_amount, 2_500_000)
        self.assertEqual(software.currency, "USD")
        self.assertIn("web_application_prototype", software.required_capabilities)
        self.assertIn("technical_proposal", software.required_capabilities)
        self.assertTrue(software.terms_required)
        self.assertTrue(software.identity_or_kyc_required)
        self.assertTrue(all("usa.gov" in value for value in software.payment_evidence[:1]))

    def test_hardware_challenge_becomes_a_capability_gap_candidate(self) -> None:
        opportunities, _ = USAGovChallengeSource(fetcher=self.getter).collect()
        hardware = next(item for item in opportunities if "Robotics" in item.title)
        self.assertIn("physical_hardware_prototype", hardware.required_capabilities)
        self.assertGreaterEqual(hardware.accessibility, 0.8)
        self.assertGreater(hardware.cost, 0.5)

    def test_listing_failure_is_isolated_as_source_state(self) -> None:
        def broken(_: str) -> bytes:
            raise TimeoutError("source timed out")

        opportunities, state = USAGovChallengeSource(fetcher=broken).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("TimeoutError", state.reason)


if __name__ == "__main__":
    unittest.main()
