from __future__ import annotations

import unittest

from scripts.classify_software_micro_missions import unvalidated_vendor_workspace_reason


class VendorWorkspacePolicyTests(unittest.TestCase):
    def test_rejects_production_smartsheet_false_positive(self) -> None:
        title = "Congress Event Task Tracker Demo"
        description = (
            "Build a self-contained Smartsheet workspace with a task master sheet, "
            "filtered reports, dashboard and Smartsheet deadline automations."
        )
        self.assertEqual(
            unvalidated_vendor_workspace_reason(title, description),
            "unvalidated_vendor_specific_workspace",
        )

    def test_rejects_other_vendor_native_workspace_builds(self) -> None:
        for request in (
            "Build an Airtable automation and dashboard",
            "Create a Monday.com project workspace",
            "Set up a ClickUp workflow",
            "Create a Notion database automation",
        ):
            with self.subTest(request=request):
                self.assertEqual(
                    unvalidated_vendor_workspace_reason(request),
                    "unvalidated_vendor_specific_workspace",
                )

    def test_does_not_reject_generic_bounded_web_work(self) -> None:
        self.assertIsNone(
            unvalidated_vendor_workspace_reason(
                "Responsive landing page",
                "Build one static HTML and CSS page with supplied content.",
            )
        )


if __name__ == "__main__":
    unittest.main()
