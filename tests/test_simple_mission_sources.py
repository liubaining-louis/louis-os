from __future__ import annotations

import unittest

from atlas.simple_mission_sources import (
    FreelancerPublicJobsSource,
    estimate_simple_effort,
    infer_simple_capability,
)


class SimpleMissionSourceTests(unittest.TestCase):
    def test_accepts_remote_explicit_budget_low_bid_research_mission(self) -> None:
        html = b'''<html><body>
        <a href="/projects/web-search/verified-school-contact-research">Verified School Contact Research</a>
        <span>4 days left</span>
        <p>Research 50 official school contacts and deliver a clean spreadsheet with source URLs.</p>
        <span>Web Search</span><span>Lead Generation</span>
        <strong>$40 - $80</strong>
        <span>3 bids</span>
        <a href="/projects/web-search/verified-school-contact-research">Bid now</a>
        </body></html>'''
        source = FreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/web-search/",),
            fetcher=lambda _: html,
        )
        opportunities, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 40.0)
        self.assertEqual(item.currency, "USD")
        self.assertEqual(item.required_capabilities, ("evidence_research_dossier",))
        self.assertEqual(item.metadata["active_bids"], 3)
        self.assertTrue(item.reward_verified)
        self.assertTrue(item.account_required)
        self.assertTrue(item.terms_required)
        self.assertFalse(item.metadata["submission_dossier_prepared"])

    def test_rejects_average_bid_without_explicit_payer_budget(self) -> None:
        html = b'''<a href="/projects/data-entry/simple-task">Simple task</a>
        <span>6 days left</span><p>Copy data into a sheet.</p>
        <span>$55 Average bid</span><span>2 bids</span>'''
        source = FreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/data-entry/",),
            fetcher=lambda _: html,
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_rejects_physical_manual_and_crowded_work(self) -> None:
        html = b'''<html><body>
        <a href="/projects/data-entry/local-check">On-site document verification</a>
        <span>5 days left</span><p>Visit an address and take geotagged photos.</p><span>$20 - $30</span><span>0 bids</span>
        <a href="/projects/data-entry/manual-copy">Manual-only copy typing</a>
        <span>5 days left</span><p>No automated tools. Manual only.</p><span>$30 - $50</span><span>0 bids</span>
        <a href="/projects/web-search/crowded">Simple web research</a>
        <span>5 days left</span><p>Collect public sources.</p><span>$50 - $70</span><span>30 bids</span>
        </body></html>'''
        source = FreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/data-entry/",),
            fetcher=lambda _: html,
            maximum_bids=10,
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_source_failure_is_isolated(self) -> None:
        source = FreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/data-entry/",),
            fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("x")),
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("TimeoutError", state.reason)

    def test_capability_and_effort_are_bounded(self) -> None:
        self.assertEqual(
            infer_simple_capability("Build a verified contact list", "Web search and lead generation"),
            "evidence_research_dossier",
        )
        self.assertEqual(infer_simple_capability("Translate French document"), "translation_delivery")
        self.assertEqual(infer_simple_capability("Excel formula cleanup"), "python_data_analysis")
        self.assertLessEqual(estimate_simple_effort("Lead generation web search"), 16.0)


if __name__ == "__main__":
    unittest.main()
