from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "autonomous-monetization-scout.yml"
).read_text(encoding="utf-8")


class AutonomousMonetizationWorkflowTests(unittest.TestCase):
    def test_uses_workload_identity_before_firestore(self):
        auth = WORKFLOW.index("Authenticate to Google Cloud")
        scout = WORKFLOW.index("Search and score public opportunities")
        sync = WORKFLOW.index("Synchronize final operational state")
        self.assertLess(auth, scout)
        self.assertLess(auth, sync)
        self.assertIn("id-token: write", WORKFLOW)
        self.assertIn("google-github-actions/auth@v3", WORKFLOW)

    def test_sync_failure_preserves_evidence_then_fails_job(self):
        sync = WORKFLOW.index("id: sync_state")
        commit = WORKFLOW.index("Commit evidence ledger")
        final_gate = WORKFLOW.index("Enforce operational state synchronization")
        self.assertIn("continue-on-error: true", WORKFLOW[sync:commit])
        self.assertLess(sync, commit)
        self.assertLess(commit, final_gate)
        self.assertIn("steps.sync_state.outcome != 'success'", WORKFLOW[final_gate:])

    def test_report_uses_executable_ledger_candidate(self):
        self.assertIn("top = ledger.get('top_opportunity')", WORKFLOW)
        self.assertNotIn("top = (data.get('candidates') or [None])[0]", WORKFLOW)

    def test_root_cause_runs_after_execution_and_before_sync(self):
        executor = WORKFLOW.index("Execute approved external action with receipt")
        diagnosis = WORKFLOW.index("Diagnose zero-revenue root cause")
        sync = WORKFLOW.index("Synchronize final operational state")
        self.assertLess(executor, diagnosis)
        self.assertLess(diagnosis, sync)
        self.assertIn("python scripts/analyze_monetization_root_cause.py", WORKFLOW)

    def test_root_cause_artifact_is_committed_and_reported(self):
        self.assertIn("results/monetization_root_cause.json", WORKFLOW)
        self.assertIn("Cause racine", WORKFLOW)
        self.assertIn("Critère de succès", WORKFLOW)
        self.assertIn("Horizon premier euro", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
