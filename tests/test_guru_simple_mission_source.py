from __future__ import annotations

from datetime import datetime, timezone
import unittest

from atlas.guru_simple_mission_source import GuruPublicJobsSource


class GuruPublicJobsSourceTests(unittest.TestCase):
    def source(self, html: bytes, **overrides) -> GuruPublicJobsSource:
        return GuruPublicJobsSource(
            directory_urls=("https://www.guru.com/d/jobs/",),
            fetcher=lambda _: html,
            now=datetime(2026, 7, 27, tzinfo=timezone.utc),
            **overrides,
        )

    def test_accepts_explicit_fixed_remote_research_with_payment_history(self) -> None:
        html = b'''<html><body>
        <span>Posted 2 hrs ago &middot; 4 Quotes Received</span>
        <a href="/jobs/verified-public-company-research/2119000&SearchUrl=search.aspx">Verified Public Company Research</a>
        <strong>Fixed Price | $50-$100</strong>
        <span>Send before Aug 15, 2026</span>
        <a href="/jobs/verified-public-company-research/2119000&SearchUrl=search.aspx">Send Quote</a>
        <p>Research 75 companies using public official websites and deliver a clean spreadsheet with source URLs. No outreach or account creation is required.</p>
        <span>Web Research</span><span>Lead Generation</span><span>Data Collection</span>
        <h3>Reliable Employer</h3><span>United States</span><span>1,250 Spent | 100%</span>
        </body></html>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.source_id, "guru_public_simple_jobs")
        self.assertEqual(item.reward_amount, 50.0)
        self.assertEqual(item.currency, "USD")
        self.assertEqual(item.required_capabilities, ("evidence_research_dossier",))
        self.assertEqual(item.metadata["active_quotes"], 4)
        self.assertEqual(item.metadata["employer_spend"], 1250.0)
        self.assertEqual(item.metadata["employer_payment_percent"], 100.0)
        self.assertEqual(item.metadata["platform"], "Guru")
        self.assertEqual(item.metadata["reward_unit"], "fixed_total")
        self.assertTrue(item.reward_verified)
        self.assertTrue(item.account_required)
        self.assertTrue(item.terms_required)

    def test_accepts_bounded_hourly_spreadsheet_work(self) -> None:
        html = b'''<html><body>
        <span>Posted 1 hr ago &middot; No Quotes Received</span>
        <a href="/jobs/excel-data-cleanup/2119001&SearchUrl=search.aspx">Excel Data Cleanup</a>
        <strong>Hourly|$10 - $15|1-10 hrs/wk|1-4 weeks</strong>
        <span>Send before Aug 10, 2026</span>
        <p>Clean a supplied spreadsheet, remove duplicates, validate formulas and return Excel and CSV files.</p>
        <span>Excel</span><span>Data Cleansing</span>
        <span>900 Spent | 99.5%</span>
        </body></html>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.metadata["budget_kind"], "hourly_range")
        self.assertEqual(item.metadata["budget_min"], 10.0)
        self.assertEqual(item.metadata["budget_max"], 15.0)
        self.assertEqual(item.reward_amount, 10.0)
        self.assertEqual(item.metadata["reward_unit"], "per_hour")
        self.assertEqual(item.metadata["estimated_total_min"], 80.0)
        self.assertEqual(item.required_capabilities, ("python_data_analysis",))

    def test_rejects_under_budget_without_verified_lower_bound(self) -> None:
        html = b'''<span>Posted 2 hrs ago &middot; 1 Quote Received</span>
        <a href="/jobs/lead-list/2119002&SearchUrl=search.aspx">Lead List</a>
        <span>Fixed Price | Under $250</span><span>Send before Aug 15, 2026</span>
        <p>Research public companies and provide a spreadsheet.</p><span>500 Spent | 100%</span>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_rejects_location_sensitive_manual_or_long_term_work(self) -> None:
        html = b'''<html><body>
        <span>Posted 2 hrs ago &middot; No Quotes Received</span>
        <a href="/jobs/iraq-employment-verification/2119003&SearchUrl=search.aspx">Iraq Employment Verification</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 15, 2026</span>
        <p>On-the-ground employment verification. Visit the premises and obtain stamped confirmation from the former employer.</p><span>500 Spent | 100%</span>
        <span>Posted 3 hrs ago &middot; 2 Quotes Received</span>
        <a href="/jobs/manual-transcription/2119004&SearchUrl=search.aspx">Manual Transcription</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 16, 2026</span>
        <p>Manual only. No AI or automated tools. Long-term part-time work.</p><span>700 Spent | 100%</span>
        </body></html>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_rejects_crowded_expired_or_unproven_employer(self) -> None:
        html = b'''<html><body>
        <span>Posted 2 hrs ago &middot; 30 Quotes Received</span>
        <a href="/jobs/crowded-research/2119005&SearchUrl=search.aspx">Crowded Research</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 15, 2026</span>
        <p>Web research and spreadsheet delivery.</p><span>500 Spent | 100%</span>
        <span>Posted 3 hrs ago &middot; 2 Quotes Received</span>
        <a href="/jobs/expired-research/2119006&SearchUrl=search.aspx">Expired Research</a>
        <span>Fixed Price | $50-$100</span><span>Send before Jul 20, 2026</span>
        <p>Web research and spreadsheet delivery.</p><span>500 Spent | 100%</span>
        <span>Posted 4 hrs ago &middot; 1 Quote Received</span>
        <a href="/jobs/unproven-research/2119007&SearchUrl=search.aspx">Unproven Research</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 20, 2026</span>
        <p>Web research and spreadsheet delivery.</p><span>10 Spent | 70%</span>
        </body></html>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_adjacent_card_employer_evidence_cannot_leak(self) -> None:
        html = b'''<html><body>
        <span>Posted 2 hrs ago &middot; 1 Quote Received</span>
        <a href="/jobs/good-research/2119008&SearchUrl=search.aspx">Good Research</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 15, 2026</span>
        <p>Web research with source URLs.</p><span>500 Spent | 100%</span>
        <span>Posted 3 hrs ago &middot; 1 Quote Received</span>
        <a href="/jobs/unproven-research/2119009&SearchUrl=search.aspx">Unproven Research</a>
        <span>Fixed Price | $50-$100</span><span>Send before Aug 16, 2026</span>
        <p>Web research with source URLs.</p><span>0 Spent | 0%</span>
        </body></html>'''
        opportunities, state = self.source(html).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual([item.title for item in opportunities], ["Good Research"])

    def test_source_failure_is_isolated(self) -> None:
        source = GuruPublicJobsSource(
            directory_urls=("https://www.guru.com/d/jobs/",),
            fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("x")),
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("TimeoutError", state.reason)


if __name__ == "__main__":
    unittest.main()
