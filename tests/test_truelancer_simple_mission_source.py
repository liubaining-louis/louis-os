from __future__ import annotations

import unittest

from atlas.truelancer_simple_mission_source import TruelancerPublicJobsSource


class TruelancerPublicJobsSourceTests(unittest.TestCase):
    listing_url = "https://www.truelancer.com/freelance-jobs?page=1"
    project_url = "https://www.truelancer.com/freelance-project/public-company-research-700001"

    def source(self, listing: bytes, detail: bytes, **overrides) -> TruelancerPublicJobsSource:
        pages = {self.listing_url: listing, self.project_url: detail}
        return TruelancerPublicJobsSource(
            directory_urls=(self.listing_url,),
            fetcher=pages.__getitem__,
            **overrides,
        )

    def test_accepts_recent_low_competition_hourly_research_with_paid_client(self) -> None:
        listing = f'''<html><body>
        <p>Never pay a security deposit. Keep all transactions within Truelancer.</p>
        <a href="{self.project_url}">Public Company Evidence Research</a>
        <p>Hourly | Posted: 2 hours ago</p>
        <p>Research official company websites and deliver a sourced spreadsheet.</p>
        <span>Research</span><span>Data Collection</span><span>Web Search</span>
        <strong>$12/ Hr</strong><span>approx: 6 Hrs</span><span>2 proposals</span>
        <a href="{self.project_url}">View &amp; Apply</a>
        </body></html>'''.encode()
        detail = b'''<html><body>
        <h1>Public Company Evidence Research</h1>
        <p>Hourly Project | Posted 2 hours ago</p>
        <p>$12/ Hour</p><p>Estimated Hour - 6 hrs</p><p>2 Proposals</p><p>Active Status</p>
        <p>Research official public company websites and deliver a sourced spreadsheet. No outreach is required.</p>
        <p>Projects Paid 4</p><p>Total Spent $ 600</p>
        </body></html>'''
        opportunities, state = self.source(listing, detail).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.source_id, "truelancer_public_simple_jobs")
        self.assertEqual(item.reward_amount, 72.0)
        self.assertEqual(item.currency, "USD")
        self.assertEqual(item.required_capabilities, ("evidence_research_dossier",))
        self.assertEqual(item.metadata["estimated_effort_hours"], 6.0)
        self.assertEqual(item.metadata["active_proposals"], 2)
        self.assertEqual(item.metadata["client_projects_paid"], 4)
        self.assertIn("never pay a security deposit", item.metadata["payment_methods"][0].casefold())
        self.assertTrue(item.reward_verified)
        self.assertTrue(item.account_required)
        self.assertTrue(item.terms_required)

    def test_accepts_recent_fixed_spreadsheet_cleanup(self) -> None:
        listing = f'''<html><body>
        <p>Never pay a security deposit. Keep all transactions within Truelancer.</p>
        <a href="{self.project_url}">Excel Spreadsheet Cleanup</a>
        <p>Fixed Price | Posted: 30 minutes ago</p>
        <p>Clean supplied spreadsheet, remove duplicates and validate formulas.</p>
        <span>Excel</span><span>Data Processing</span><strong>$90</strong><span>Be the first one</span>
        </body></html>'''.encode()
        detail = b'''<html><body>
        <h1>Excel Spreadsheet Cleanup</h1><p>Fixed Price Project | Posted 30 minutes ago</p>
        <p>$90 Budget</p><p>0 Proposals</p><p>Active Status</p>
        <p>Clean supplied spreadsheet, remove duplicates and validate formulas.</p>
        <p>Projects Paid 2</p><p>Total Spent $ 250</p>
        </body></html>'''
        opportunities, state = self.source(listing, detail).collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(opportunities), 1)
        item = opportunities[0]
        self.assertEqual(item.reward_amount, 90.0)
        self.assertEqual(item.required_capabilities, ("python_data_analysis",))
        self.assertEqual(item.metadata["budget_kind"], "fixed_total")
        self.assertEqual(item.metadata["active_proposals"], 0)

    def test_rejects_unpaid_client_even_when_listing_looks_easy(self) -> None:
        listing = f'''<html><body>
        <p>Never pay a security deposit. Keep all transactions within Truelancer.</p>
        <a href="{self.project_url}">Public Company Evidence Research</a>
        <p>Hourly | Posted: 2 hours ago</p><p>Research websites.</p>
        <strong>$12/ Hr</strong><span>approx: 6 Hrs</span><span>2 proposals</span>
        </body></html>'''.encode()
        detail = b'''<html><body>
        <h1>Public Company Evidence Research</h1><p>Hourly Project | Posted 2 hours ago</p>
        <p>$12/ Hour</p><p>Estimated Hour - 6 hrs</p><p>2 Proposals</p><p>Active Status</p>
        <p>Projects Paid 0</p><p>Total Spent $ 0</p>
        </body></html>'''
        opportunities, state = self.source(listing, detail).collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_rejects_stale_crowded_long_or_no_ai_work(self) -> None:
        listing = f'''<html><body>
        <p>Never pay a security deposit. Keep all transactions within Truelancer.</p>
        <a href="{self.project_url}">Manual Data Entry Long Term</a>
        <p>Hourly | Posted: 2 months ago</p>
        <p>Long-term manual only task. No AI or automated tools.</p>
        <strong>$8/ Hr</strong><span>approx: 40 Hrs</span><span>62 proposals</span>
        </body></html>'''.encode()
        source = TruelancerPublicJobsSource(
            directory_urls=(self.listing_url,),
            fetcher=lambda _: listing,
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "empty")

    def test_source_failure_is_isolated(self) -> None:
        source = TruelancerPublicJobsSource(
            directory_urls=(self.listing_url,),
            fetcher=lambda _: (_ for _ in ()).throw(TimeoutError("x")),
        )
        opportunities, state = source.collect()
        self.assertEqual(opportunities, [])
        self.assertEqual(state.status, "failed")
        self.assertIn("TimeoutError", state.reason)


if __name__ == "__main__":
    unittest.main()
