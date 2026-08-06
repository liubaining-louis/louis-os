from __future__ import annotations

import unittest

from atlas.submission_executor import SubmissionAuthorization, execute_submission


class Adapter:
    platform = "freelancer"

    def __init__(self, *, open_: bool = True, compliant: bool = True, receipt: bool = True) -> None:
        self.open_ = open_
        self.compliant = compliant
        self.receipt = receipt

    def revalidate(self, dossier):
        return {
            "listing_open": self.open_,
            "remote_eligible": True,
            "platform_compliant": self.compliant,
            "evidence": ["fresh-page-check"],
        }

    def submit(self, dossier):
        if not self.receipt:
            return {"evidence": ["submit-clicked"]}
        return {
            "receipt_id": "bid-123",
            "confirmation_url": "https://www.freelancer.com/bids/123",
            "submitted_at": "2026-08-06T20:00:00+00:00",
            "evidence": ["confirmation-page"],
        }


class SubmissionExecutorTests(unittest.TestCase):
    def dossier(self):
        return {
            "dossier_id": "dossier-1",
            "opportunity_id": "opp-1",
            "canonical_url": "https://www.freelancer.com/projects/1",
            "proposal_text": "I can deliver the tested artifact.",
            "status": "prepare_then_gate",
            "external_submission_verified": False,
            "reward_amount": 50,
            "currency": "USD",
        }

    def auth(self, **changes):
        values = {
            "authorization_id": "auth-1",
            "dossier_id": "dossier-1",
            "platform": "freelancer",
            "approved": True,
            "approved_at": "2026-08-06T19:00:00+00:00",
        }
        values.update(changes)
        return SubmissionAuthorization(**values)

    def test_requires_explicit_authorization(self):
        result = execute_submission(self.dossier(), Adapter(), None)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.blocker, "explicit_authorization_required")

    def test_dry_run_never_claims_submission(self):
        result = execute_submission(self.dossier(), Adapter(), self.auth(), dry_run=True)
        self.assertEqual(result.status, "dry_run_ready")
        self.assertFalse(result.externally_submitted)
        self.assertFalse(result.external_submission_verified)

    def test_closed_listing_blocks_before_submit(self):
        result = execute_submission(self.dossier(), Adapter(open_=False), self.auth(), dry_run=False)
        self.assertEqual(result.blocker, "listing_not_open")
        self.assertFalse(result.externally_submitted)

    def test_missing_receipt_is_attempted_but_unverified(self):
        result = execute_submission(self.dossier(), Adapter(receipt=False), self.auth(), dry_run=False)
        self.assertTrue(result.externally_submitted)
        self.assertFalse(result.external_submission_verified)
        self.assertEqual(result.blocker, "missing_platform_receipt")

    def test_platform_receipt_verifies_submission(self):
        result = execute_submission(self.dossier(), Adapter(), self.auth(), dry_run=False)
        self.assertEqual(result.status, "submitted_verified")
        self.assertTrue(result.external_submission_verified)
        self.assertEqual(result.receipt.receipt_id, "bid-123")
        self.assertEqual(len(result.receipt.payload_hash), 64)

    def test_authorization_cannot_be_reused_for_other_dossier(self):
        dossier = self.dossier()
        dossier["dossier_id"] = "dossier-2"
        result = execute_submission(dossier, Adapter(), self.auth(), dry_run=False)
        self.assertEqual(result.blocker, "authorization_dossier_mismatch")


if __name__ == "__main__":
    unittest.main()
