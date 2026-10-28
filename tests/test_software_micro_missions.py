from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from atlas.software_micro_missions import (
    CAPABILITY_BY_ID,
    SoftwareFreelancerPublicJobsSource,
    assess_software_scope,
    capability_catalog,
    capability_specs,
    classify_software_capability,
    demo_bundles,
    estimate_software_effort,
    validate_demo_bundle,
)


class SoftwareMicroMissionTests(unittest.TestCase):
    def test_reserved_listing_is_terminal_in_classification_pipeline(self) -> None:
        from dataclasses import asdict
        from atlas.universal_market import InternetOpportunity
        from scripts import classify_software_micro_missions as classifier

        item = {
            "source_id": "freelancer_public_software_jobs",
            "source_category": "freelance_marketplace",
            "source_url": "https://www.freelancer.com/projects/css/reserved-fix",
            "title": "Fix one CSS bug",
            "description": "Please don't bid if we haven't talked about it.",
            "reward_amount": 100.0, "currency": "USD", "reward_verified": True,
            "payment_evidence": ["https://www.freelancer.com/projects/css/reserved-fix"],
            "required_capabilities": ["frontend_bug_fix"],
            "observed_at": "2026-10-28T08:45:26+00:00",
            "metadata": {"source_kind": "public_freelance_listing"},
        }
        opportunity = InternetOpportunity(**item)
        item = {**asdict(opportunity), "opportunity_id": opportunity.opportunity_id}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            market = root / "market.json"
            receipt = root / "receipt.json"
            market.write_text(json.dumps({"opportunities": [item], "source_states": []}))
            with patch.multiple(classifier, ROOT=root, MARKET_PATH=market,
                                CYCLE_PATH=root / "cycle.json", RECEIPT_PATH=receipt):
                self.assertEqual(classifier.main(), 0)
            row = json.loads(market.read_text())["opportunities"][0]
            summary = json.loads(receipt.read_text())
        self.assertEqual(row["decision"]["status"], "rejected")
        self.assertIn("software_scope_rejected:explicitly_unavailable_or_reserved",
                      row["decision"]["blockers"])
        self.assertFalse(row["metadata"]["capability_gap_allowed"])
        self.assertEqual(row["decision"]["human_action_minimal"], "none")
        self.assertEqual(summary["accepted_count"], 0)
        self.assertEqual(summary["rejected_count"], 1)

    def test_rejects_software_listing_reserved_for_an_existing_freelancer(self) -> None:
        assessment = assess_software_scope(
            "Node.js Security Updates and GitHub Fixes",
            "This project is for a freelancer I've already worked with and talked "
            "it through with in chat. They'll update my Node.js app and clear the "
            "GitHub security alerts as agreed, nothing else in the app changes. "
            "Everything is already agreed with them, so please don't bid if we "
            "haven't talked about it. Thanks! JavaScript",
        )
        self.assertTrue(assessment["matched"])
        self.assertFalse(assessment["accepted"])
        self.assertEqual(assessment["reason"], "explicitly_unavailable_or_reserved")

    def test_rejects_explicit_prior_conversation_only_bidding(self) -> None:
        for description in (
            "Please don't bid if we haven't talked about it.",
            "DO NOT BID IF WE HAVE NOT SPOKEN before.",
            "Please don’t bid if we haven’t talked in chat.",
        ):
            with self.subTest(description=description):
                result = assess_software_scope("Fix one CSS bug", description)
                self.assertFalse(result["accepted"])
                self.assertEqual(result["reason"], "explicitly_unavailable_or_reserved")

    def test_prior_experience_and_open_bidding_are_not_reservations(self) -> None:
        for description in (
            "I have already worked with freelancers. New applicants are welcome.",
            "Please don't bid if you have no CSS experience.",
            "We haven't talked yet; please submit your proposal.",
            "This project is for a freelancer with experience in CSS.",
        ):
            with self.subTest(description=description):
                self.assertTrue(assess_software_scope("Fix one CSS bug", description)["accepted"])

    def test_registers_five_bounded_capabilities_with_eur_guidance(self) -> None:
        specs = capability_specs()
        self.assertEqual(len(specs), 5)
        self.assertEqual(
            {item.capability_id for item in specs},
            {
                "static_website_delivery",
                "frontend_bug_fix",
                "python_automation_delivery",
                "api_integration_delivery",
                "deployment_and_validation",
            },
        )
        self.assertTrue(all(item.maximum_effort_hours <= 16 for item in specs))
        catalog = capability_catalog()
        self.assertEqual(catalog["currency"], "EUR")
        self.assertIn("guidance_only", catalog["pricing_status"])
        self.assertEqual(catalog["external_submissions_verified"], 0)
        self.assertEqual(catalog["revenue_verified_eur"], 0.0)

    def test_classifies_small_web_and_code_work(self) -> None:
        examples = {
            "Build a responsive one-page landing page in HTML and CSS": "static_website_delivery",
            "Fix a mobile CSS alignment bug": "frontend_bug_fix",
            "Create a Python script to deduplicate a CSV": "python_automation_delivery",
            "Connect one REST API endpoint and validate the JSON response": "api_integration_delivery",
            "Deploy a static website to Netlify and verify links": "deployment_and_validation",
        }
        for title, expected in examples.items():
            with self.subTest(title=title):
                self.assertEqual(classify_software_capability(title), expected)
                assessment = assess_software_scope(title)
                self.assertTrue(assessment["accepted"])
                self.assertEqual(assessment["capability_id"], expected)
                self.assertLessEqual(assessment["estimated_effort_hours"], 16)

    def test_rejects_oversized_unsafe_and_unbounded_requests(self) -> None:
        requests = (
            "Build a complete application with HTML and JavaScript",
            "Clone the entire website design in HTML and CSS",
            "Create a landing page with unlimited revisions and 24/7 support",
            "Write a Python script to bypass authentication and steal credentials",
            "Integrate a live payment gateway using an API integration and production database migration",
        )
        for title in requests:
            with self.subTest(title=title):
                assessment = assess_software_scope(title)
                self.assertTrue(assessment["matched"])
                self.assertFalse(assessment["accepted"])
                self.assertNotEqual(assessment["reason"], "not_software_micro_mission")

    def test_effort_remains_bounded(self) -> None:
        self.assertEqual(estimate_software_effort("Small CSS bug fix"), 4.0)
        self.assertLessEqual(estimate_software_effort("Build a five pages responsive website"), 16.0)
        self.assertEqual(CAPABILITY_BY_ID["api_integration_delivery"].maximum_effort_hours, 16.0)

    def test_all_demo_bundles_validate_deterministically(self) -> None:
        bundles = demo_bundles()
        self.assertEqual(set(bundles), {"landing_page", "csv_automation", "api_integration"})
        for demo_id, files in bundles.items():
            checks = validate_demo_bundle(demo_id, files)
            self.assertGreaterEqual(len(checks), 4)

    def test_csv_demo_deduplicates_and_rejects_invalid_email(self) -> None:
        files = demo_bundles()["csv_automation"]
        namespace = {"__name__": "demo_module"}
        exec(files["process_csv.py"], namespace)  # noqa: S102 - repository-owned fixture
        rows = list(csv.DictReader(io.StringIO(files["sample_input.csv"])))
        cleaned = namespace["process_rows"](rows)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0]["email"], "alice@example.com")
        self.assertEqual(cleaned[1]["email"], "bob@example.com")

    def test_software_freelancer_source_uses_dedicated_categories(self) -> None:
        source = SoftwareFreelancerPublicJobsSource(
            category_urls=("https://www.freelancer.com/jobs/html/",),
            fetcher=lambda _: b'''<html><body>
            <a href="/projects/html/responsive-landing-page">Responsive HTML landing page</a>
            <span>4 days left</span><p>Build one responsive page with supplied content.</p>
            <strong>$150 - $250</strong><span>3 bids</span>
            </body></html>''',
        )
        rows, state = source.collect()
        self.assertEqual(state.status, "ok")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_id, "freelancer_public_software_jobs")
        assessment = assess_software_scope(rows[0].title, rows[0].description)
        self.assertTrue(assessment["accepted"])
        self.assertEqual(assessment["capability_id"], "static_website_delivery")


if __name__ == "__main__":
    unittest.main()
