from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.bountybook_authorized_submit import ARTIFACT_SHA256, EXPECTED_TITLE, JOB_ID, execute


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "deliverables" / "bountybook_http_server_19a16071" / "http_server.py"


def authorization() -> dict:
    return {
        "active": True,
        "authorized_at": "2026-08-28T20:22:16Z",
        "job_id": JOB_ID,
        "artifact_path": "deliverables/bountybook_http_server_19a16071/http_server.py",
        "artifact_sha256": ARTIFACT_SHA256,
        "terms_reviewed_and_accepted": True,
        "platform_auth_signing_authorized": True,
        "claim_authorized": True,
        "submission_authorized": True,
        "spend_authorized": False,
        "financial_transaction_signing_authorized": False,
        "kyc_authorized": False,
        "asset_transfer_authorized": False,
    }


class FakePlatform:
    def __init__(self, *, state: str = "open") -> None:
        self.state = state
        self.calls = []
        self.address = "0x" + "1" * 40

    def __call__(self, method, path, body, headers):
        self.calls.append((method, path, body, headers))
        if method == "GET" and path.startswith("/auth/nonce?"):
            return 200, {"nonce": "sign this exact nonce"}
        if path == "/auth/verify":
            return 200, {"token": "session-secret"}
        if path.endswith("/claim"):
            self.state = "claimed"
            return 200, {"success": True, "jobId": JOB_ID}
        if path.endswith("/submit"):
            self.state = "submitted"
            return 202, {"success": True, "submissionId": "submission-1"}
        return 200, {
            "job": {
                "id": JOB_ID,
                "title": EXPECTED_TITLE,
                "status": self.state,
                "budget_usdc": 8,
                "executorAddress": self.address if self.state != "open" else None,
            }
        }


class BountyBookAuthorizedSubmitTests(unittest.TestCase):
    def test_executes_exact_claim_and_inline_submission(self) -> None:
        platform = FakePlatform()
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "receipt.json"
            receipt = execute(
                authorization=authorization(),
                artifact_path=ARTIFACT,
                private_key_path=Path(directory) / "unused",
                receipt_path=receipt_path,
                transport=platform,
                signer=lambda message: (platform.address, "0xsigned-" + message),
                executor_address=platform.address,
            )
            self.assertTrue(receipt["claim"]["verified"])
            self.assertTrue(receipt["submission"]["verified"])
            self.assertEqual(receipt["platform_state"]["status"], "submitted")
            self.assertFalse(receipt["payment"]["paid"])
            self.assertFalse(receipt["oracle"]["observed"])
            self.assertFalse(receipt["safety"]["financial_transaction_signed"])
            submit = next(call for call in platform.calls if call[1].endswith("/submit"))
            submitted_output = submit[2]["outputData"]
            self.assertEqual(submitted_output["filename"], "http_server.py")
            self.assertEqual(submitted_output["language"], "python")
            self.assertEqual(submitted_output["sha256"], ARTIFACT_SHA256)
            self.assertEqual(submitted_output["code"], ARTIFACT.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(submitted_output["code"].splitlines()), 100)
            self.assertNotIn("files", submitted_output)
            persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertNotIn("session-secret", json.dumps(persisted))
            self.assertNotIn("0xsigned", json.dumps(persisted))

    def test_closed_job_blocks_before_authentication(self) -> None:
        platform = FakePlatform(state="claimed")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "job is not open"):
                execute(
                    authorization=authorization(),
                    artifact_path=ARTIFACT,
                    private_key_path=Path(directory) / "unused",
                    receipt_path=Path(directory) / "receipt.json",
                    transport=platform,
                    signer=lambda message: (platform.address, "0xsigned"),
                    executor_address=platform.address,
                )
        self.assertEqual(len(platform.calls), 1)

    def test_hash_mismatch_blocks_without_network_access(self) -> None:
        platform = FakePlatform()
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "http_server.py"
            artifact.write_text("tampered = True\n", encoding="utf-8")
            self.assertNotEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), ARTIFACT_SHA256)
            with self.assertRaisesRegex(ValueError, "artifact hash"):
                execute(
                    authorization=authorization(),
                    artifact_path=artifact,
                    private_key_path=Path(directory) / "unused",
                    receipt_path=Path(directory) / "receipt.json",
                    transport=platform,
                    signer=lambda message: (platform.address, "0xsigned"),
                    executor_address=platform.address,
                )
        self.assertEqual(platform.calls, [])

    def test_financial_boundary_must_remain_disabled(self) -> None:
        approval = authorization()
        approval["spend_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "boundaries"):
                execute(
                    authorization=approval,
                    artifact_path=ARTIFACT,
                    private_key_path=Path(directory) / "unused",
                    receipt_path=Path(directory) / "receipt.json",
                    transport=FakePlatform(),
                    signer=lambda message: ("0x" + "1" * 40, "0xsigned"),
                    executor_address="0x" + "1" * 40,
                )


if __name__ == "__main__":
    unittest.main()
