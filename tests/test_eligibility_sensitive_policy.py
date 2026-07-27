from __future__ import annotations

import unittest

from atlas.automation_compatibility import policy_rejection_reason, reject_incompatible_delivery_methods


class EligibilitySensitivePolicyTests(unittest.TestCase):
    def opportunity(self, title: str, description: str) -> dict:
        return {
            "opportunity_id": "market-test",
            "title": title,
            "description": description,
            "payment_evidence": [],
            "evidence": [],
            "decision": {
                "status": "prepare_then_gate",
                "blockers": ["account_required"],
                "missing_capabilities": [],
                "human_action_minimal": "account_required",
            },
            "metadata": {
                "submission_dossier_prepared": True,
                "human_action_instructions": ["Use account"],
            },
        }

    def test_rejects_native_thai_recording_requirement(self) -> None:
        item = self.opportunity(
            "Native Thai Speaker for Recording Project",
            "Native Thai speakers needed, located in Thailand, with a standard Thai accent.",
        )
        self.assertEqual(policy_rejection_reason(item), "unverifiable_personal_eligibility")

    def test_rejects_native_malay_recording_requirement(self) -> None:
        item = self.opportunity(
            "Malay Sentence Recording Project",
            "Native Malay speaker with a standard Malaysian Malay accent.",
        )
        self.assertEqual(policy_rejection_reason(item), "unverifiable_personal_eligibility")

    def test_rejects_prison_call_and_visitor_record_collection(self) -> None:
        item = self.opportunity(
            "Prison Call Transcript Collection visit logs",
            "Obtain visitor logs and phone call transcripts for an incarcerated individual.",
        )
        self.assertEqual(policy_rejection_reason(item), "sensitive_personal_records_request")
        rows, rejected = reject_incompatible_delivery_methods([item])
        self.assertEqual(rejected, 1)
        result = rows[0]
        self.assertEqual(result["decision"]["status"], "rejected")
        self.assertEqual(result["decision"]["human_action_minimal"], "none")
        self.assertFalse(result["metadata"]["submission_dossier_prepared"])
        self.assertEqual(result["metadata"]["human_action_instructions"], [])
        self.assertFalse(result["metadata"]["capability_gap_allowed"])

    def test_keeps_bounded_public_research_mission(self) -> None:
        item = self.opportunity(
            "Research 30 public supplier websites",
            "Collect company name, official website and public contact page into a spreadsheet.",
        )
        self.assertIsNone(policy_rejection_reason(item))
        rows, rejected = reject_incompatible_delivery_methods([item])
        self.assertEqual(rejected, 0)
        self.assertEqual(rows[0]["decision"]["status"], "prepare_then_gate")


if __name__ == "__main__":
    unittest.main()
