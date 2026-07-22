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

    def test_issue_77_cycle_is_hourly_and_excludes_charcoal(self):
        self.assertIn('- cron: "23 * * * *"', WORKFLOW)
        self.assertNotIn('cron: "*/5 * * * *"', WORKFLOW)
        self.assertIn('ATLAS_MASTER_ISSUE: "77"', WORKFLOW)
        self.assertIn('ATLAS_CYCLE_CADENCE: "hourly"', WORKFLOW)
        self.assertIn('ATLAS_EXCLUDED_DOMAINS: "charcoal"', WORKFLOW)

    def test_issue_77_report_distinguishes_gated_and_executable_work(self):
        self.assertIn("Opportunités bloquées", WORKFLOW)
        self.assertIn("Meilleure piste exécutable", WORKFLOW)
        self.assertIn("aucune actuellement vérifiée sans prérequis externe", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
