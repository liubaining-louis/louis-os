import datetime as dt
import unittest
from unittest.mock import patch

from scripts import gcp_vm_health as health


class GcpVmHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 15, 18, 0, tzinfo=dt.timezone.utc)

    def heartbeat(self, status="FRESH"):
        return health.HeartbeatResult(
            status=status,
            observed_at="2026-09-15T17:59:00Z",
            age_seconds=60,
            detail="historical evidence only",
        )

    def test_billing_disabled_never_claims_vm_state(self):
        compute_result = health.CommandResult(
            argv=("gcloud",),
            returncode=1,
            stdout="",
            stderr=(
                "ERROR: (gcloud.compute.instances.describe) "
                "Billing is disabled for this project."
            ),
        )

        with patch.object(health, "utc_now", return_value=self.now), \
             patch.object(health, "read_heartbeat", return_value=self.heartbeat()), \
             patch.object(health, "run_command", return_value=compute_result):
            report = health.probe(
                project="test-bot-499814",
                instance="worker-1",
                zone="us-central1-a",
                heartbeat_document="health/worker-1",
                stale_after_seconds=900,
            )

        self.assertEqual("BILLING_DISABLED", report.status)
        self.assertEqual("UNKNOWN", report.vm_state)
        self.assertIn("No conclusion", report.vm_detail)

    def test_non_billing_compute_error_is_not_reclassified(self):
        compute_result = health.CommandResult(
            argv=("gcloud",),
            returncode=1,
            stdout="",
            stderr="ERROR: (gcloud.compute.instances.describe) Permission denied.",
        )

        with patch.object(health, "utc_now", return_value=self.now), \
             patch.object(health, "read_heartbeat", return_value=self.heartbeat()), \
             patch.object(health, "run_command", return_value=compute_result):
            report = health.probe(
                "test-bot-499814", "worker-1", "us-central1-a",
                "health/worker-1", 900,
            )

        self.assertEqual("COMPUTE_UNAVAILABLE", report.status)
        self.assertEqual("UNKNOWN", report.vm_state)

    def test_invalid_compute_json_is_explicit_protocol_error(self):
        compute_result = health.CommandResult(
            argv=("gcloud",),
            returncode=0,
            stdout="<html>proxy error</html>",
            stderr="",
        )

        with patch.object(health, "utc_now", return_value=self.now), \
             patch.object(health, "read_heartbeat", return_value=self.heartbeat()), \
             patch.object(health, "run_command", return_value=compute_result):
            report = health.probe(
                "test-bot-499814", "worker-1", "us-central1-a",
                "health/worker-1", 900,
            )

        self.assertEqual("COMPUTE_PROTOCOL_ERROR", report.status)
        self.assertEqual("UNKNOWN", report.vm_state)
        self.assertIn("invalid JSON", report.vm_detail)

    def test_valid_vm_metadata_is_reported_without_worker_health_claim(self):
        compute_result = health.CommandResult(
            argv=("gcloud",),
            returncode=0,
            stdout='{"name":"worker-1","status":"RUNNING"}',
            stderr="",
        )

        with patch.object(health, "utc_now", return_value=self.now), \
             patch.object(health, "read_heartbeat", return_value=self.heartbeat()), \
             patch.object(health, "run_command", return_value=compute_result):
            report = health.probe(
                "test-bot-499814", "worker-1", "us-central1-a",
                "health/worker-1", 900,
            )

        self.assertEqual("OK", report.status)
        self.assertEqual("RUNNING", report.vm_state)
        self.assertIn("does not by itself prove", report.vm_detail)

    def test_firestore_timestamp_is_fresh(self):
        document = {
            "fields": {
                "heartbeat_at": {"timestampValue": "2026-09-15T17:55:00Z"}
            }
        }

        with patch.object(health, "gcloud_access_token", return_value="token"), \
             patch.object(health, "fetch_json", return_value=document):
            result = health.read_heartbeat(
                "test-bot-499814",
                "health/worker-1",
                self.now,
                stale_after_seconds=900,
            )

        self.assertEqual("FRESH", result.status)
        self.assertEqual(300, result.age_seconds)

    def test_firestore_stale_heartbeat_is_not_worker_failure_proof(self):
        document = {
            "fields": {
                "last_heartbeat": {"timestampValue": "2026-09-15T05:14:15Z"}
            }
        }

        with patch.object(health, "gcloud_access_token", return_value="token"), \
             patch.object(health, "fetch_json", return_value=document):
            result = health.read_heartbeat(
                "test-bot-499814",
                "health/worker-1",
                self.now,
                stale_after_seconds=900,
            )

        self.assertEqual("STALE", result.status)
        self.assertIn("does not prove", result.detail)

    def test_firestore_read_failure_is_contained(self):
        with patch.object(
            health,
            "gcloud_access_token",
            side_effect=RuntimeError("credential unavailable"),
        ):
            result = health.read_heartbeat(
                "test-bot-499814",
                "health/worker-1",
                self.now,
                stale_after_seconds=900,
            )

        self.assertEqual("UNAVAILABLE", result.status)
        self.assertEqual("credential unavailable", result.detail)

    def test_billing_matcher_is_case_insensitive(self):
        result = health.CommandResult(
            argv=("gcloud",),
            returncode=1,
            stdout="",
            stderr="The BILLING ACCOUNT is INACTIVE for this consumer.",
        )
        self.assertTrue(health.billing_is_disabled(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
