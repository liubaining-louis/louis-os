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

    def test_verifies_low_bid_average_card_on_official_open_detail_page(self) -> None:
        category_url = "https://www.freelancer.com/jobs/data-processing/"
        project_url = "https://www.freelancer.com/projects/data-processing/small-public-data-cleanup"
        category = b'''<html><body>
        <a href="/projects/data-processing/small-public-data-cleanup">Small Public Data Cleanup</a>
        <span>6 days left</span>
        <p>Clean a bounded public CSV and return the corrected file.</p>
        <span>$55 Average bid</span><span>2 bids</span>
        </body></html>'''
        detail = b'''<html><body>
        <h1>Small Public Data Cleanup</h1>
        <h2>$60 - $90</h2><span>Open</span><span>Ends in 4 days</span>
        <p>Clean a bounded public CSV and return the corrected file.</p>
        <span>3 proposals</span><span>Open for bidding</span>
        </body></html>'''

        def fetch(url: str) -> bytes:
            return detail if url == project_url else category

        source = FreelancerPublicJobsSource(
            category_urls=(category_url,),
            fetcher=fetch,
        )
        opportunities, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 60.0)
        self.assertEqual(item.metadata["active_bids"], 3)
        self.assertEqual(item.metadata["category_active_bids"], 2)
        self.assertTrue(item.metadata["detail_page_verified"])
        self.assertEqual(item.payment_evidence[0], project_url)

    def test_verifies_low_bid_inr_hourly_budget_on_official_detail_page(self) -> None:
        category_url = "https://www.freelancer.com/jobs/data-entry/"
        project_url = "https://www.freelancer.com/projects/adobe-acrobat/pdf-editable-text"
        category = b'''<html><body>
        <a href="/projects/adobe-acrobat/pdf-editable-text">PDF to Editable Text</a>
        <span>6 days left</span>
        <p>Convert scanned PDF pages into accurately formatted editable text.</p>
        <span>INR 1,000 Average bid</span><span>1 bid</span>
        </body></html>'''
        detail = '''<html><body>
        <h1>PDF to Editable Text</h1>
        <h2>₹750-1250 INR / hour</h2><span>Open</span><span>Ends in 6 days</span>
        <p>Convert scanned PDF pages into accurately formatted editable text.</p>
        <span>1 proposal</span><span>Open for bidding</span>
        </body></html>'''.encode("utf-8")

        def fetch(url: str) -> bytes:
            return detail if url == project_url else category

        source = FreelancerPublicJobsSource(
            category_urls=(category_url,),
            fetcher=fetch,
        )
        opportunities, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 750.0)
        self.assertEqual(item.currency, "INR")
        self.assertEqual(item.metadata["budget_currency"], "INR")
        self.assertEqual(item.metadata["active_bids"], 1)
        self.assertTrue(item.metadata["detail_page_verified"])

    def test_rejects_closed_or_crowded_detail_page(self) -> None:
        category_url = "https://www.freelancer.com/jobs/data-processing/"
        project_url = "https://www.freelancer.com/projects/data-processing/closed-cleanup"
        category = b'''<a href="/projects/data-processing/closed-cleanup">Closed Cleanup</a>
        <span>6 days left</span><span>$55 Average bid</span><span>2 bids</span>'''
        closed_detail = b'''<h1>Closed Cleanup</h1><h2>$60 - $90</h2>
        <span>Closed</span><span>Ends in 4 days</span><span>2 proposals</span>'''
        source = FreelancerPublicJobsSource(
            category_urls=(category_url,),
            fetcher=lambda url: closed_detail if url == project_url else category,
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

    def test_rejects_exact_production_location_bound_verification(self) -> None:
        html = b'''<html><body>
        <a href="/projects/human-resources/iraq-previous-employment-verification">Iraq Previous Employment Verification</a>
        <span>6 days left</span>
        <p>I need reliable, on-the-ground assistance in Iraq to confirm a candidate's previous employment history. You will receive the candidate consent form and must contact the HR or former employer and obtain stamped confirmation.</p>
        <span>Data Collection</span><span>Human Resources</span><span>Research</span>
        <strong>$10 - $50</strong><span>0 bids</span>
        </body></html>'''
        source = FreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/data-entry/",),
            fetcher=lambda _: html,
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

    def test_explicit_bounded_plain_text_scope_is_cash_first(self) -> None:
        effort = estimate_simple_effort(
            "Quick Text Transfer Task",
            (
                "I have between one and ten pages of pure text that must be transferred "
                "into the supplied document. No images, tables, or data manipulation."
            ),
        )
        self.assertEqual(effort, 3.0)

    def test_ambiguous_text_collection_keeps_conservative_estimate(self) -> None:
        effort = estimate_simple_effort(
            "Handwritten Notes to Plain Text",
            "Convert my collection of handwritten notes to plain text.",
        )
        self.assertEqual(effort, 12.0)

    def test_large_plain_text_scope_keeps_conservative_estimate(self) -> None:
        self.assertEqual(
            estimate_simple_effort("Text Transfer", "Transfer 25 pages of pure text."),
            12.0,
        )

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
