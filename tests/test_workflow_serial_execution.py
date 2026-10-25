import json
from pathlib import Path
import unittest

from scripts.validate_workflow_governance import serial_execution_errors, workflow_jobs


ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/workflow_governance.json").read_text())
LOCK = """    concurrency:
      group: louis-os-single-execution
      cancel-in-progress: false
      queue: max
"""
GUARD = "    if: github.event_name != 'push' || !contains(github.event.head_commit.message, '[workflow-policy-only]')\n"


class WorkflowSerialExecutionTests(unittest.TestCase):
    def workflow(self, body):
        return "name: Example\njobs:\n  work:\n" + body

    def test_old_distinct_workflow_locks_do_not_serialize_repository(self):
        text = "concurrency:\n  group: per-workflow\n  cancel-in-progress: true\n" + self.workflow("    runs-on: ubuntu-latest\n")
        errors = serial_execution_errors(text, POLICY)
        self.assertIn("workflow_level_concurrency_not_allowed", errors)
        self.assertIn("job:work:shared_execution_lock_missing", errors)

    def test_runner_uses_one_non_cancelling_bounded_shared_queue(self):
        self.assertEqual(serial_execution_errors(self.workflow(GUARD + LOCK + "    runs-on: ubuntu-latest\n"), POLICY), [])

    def test_wrong_group_cancellation_and_lost_pending_work_are_rejected(self):
        variants = (
            (LOCK.replace("louis-os-single-execution", "per-workflow"), "wrong_execution_group"),
            (LOCK.replace("cancel-in-progress: false", "cancel-in-progress: true"), "running_work_must_not_be_cancelled"),
            (LOCK.replace("      queue: max\n", ""), "bounded_queue_missing"),
        )
        for lock, reason in variants:
            with self.subTest(reason=reason):
                self.assertIn("job:work:" + reason, serial_execution_errors(self.workflow(GUARD + lock + "    runs-on: ubuntu-latest\n"), POLICY))

    def test_reusable_parent_never_acquires_the_child_lock(self):
        child = "    uses: ./.github/workflows/degraded-monetization.yml\n"
        self.assertEqual(serial_execution_errors(self.workflow(GUARD + child), POLICY), [])
        self.assertIn("job:work:reusable_parent_must_not_hold_lock", serial_execution_errors(self.workflow(GUARD + LOCK + child), POLICY))

    def test_uncontrolled_external_reusable_is_not_an_exception(self):
        self.assertIn("job:work:external_reusable_not_serialized", serial_execution_errors(self.workflow(GUARD + "    uses: other/repo/.github/workflows/run.yml@main\n"), POLICY))

    def test_matrix_must_also_be_serial(self):
        text = self.workflow(LOCK + "    runs-on: ubuntu-latest\n    strategy:\n      matrix:\n        python: ['3.11', '3.12']\n")
        self.assertIn("job:work:matrix_must_be_serial", serial_execution_errors(text, POLICY, ci=True))
        self.assertEqual(serial_execution_errors(text.replace("    strategy:\n", "    strategy:\n      max-parallel: 1\n"), POLICY, ci=True), [])

    def test_rollout_does_not_run_legacy_push_actions_but_ci_is_not_skipped(self):
        text = self.workflow(LOCK + "    runs-on: ubuntu-latest\n")
        self.assertIn("job:work:policy_rollout_guard_missing", serial_execution_errors(text, POLICY))
        self.assertEqual(serial_execution_errors(text, POLICY, ci=True), [])
        decoy = text + "    steps:\n      - run: echo \"" + GUARD.strip() + "\"\n"
        self.assertIn("job:work:policy_rollout_guard_missing", serial_execution_errors(decoy, POLICY))

    def test_unsupported_jobs_fail_closed(self):
        self.assertIn("jobs_mapping_missing_or_unsupported", serial_execution_errors("name: Empty\n", POLICY))
        self.assertIn("jobs_mapping_missing_or_unsupported", serial_execution_errors('jobs:\n  "quoted-job":\n    runs-on: ubuntu-latest\n', POLICY))
        self.assertIn("job:work:runner_job_shape_unsupported", serial_execution_errors(self.workflow(GUARD + "    steps: []\n"), POLICY))

    def test_job_parser_does_not_read_step_or_heredoc_mappings_as_jobs(self):
        text = self.workflow(GUARD + LOCK + "    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          jobs:\n            unrelated: value\n")
        self.assertEqual([name for name, _ in workflow_jobs(text)], ["work"])

    def test_every_repository_workflow_obeys_the_same_contract(self):
        for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
            with self.subTest(workflow=path.name):
                self.assertEqual(serial_execution_errors(path.read_text(), POLICY, ci=path.name == "ci.yml"), [])

    def test_dossier_ci_uses_module_entrypoint_without_missing_atlas_import(self):
        text = (ROOT / ".github/workflows/decision-gated-dossiers.yml").read_text()
        self.assertIn("run: python -m scripts.build_decision_gated_dossiers", text)
        self.assertNotIn("run: python scripts/build_decision_gated_dossiers.py", text)


if __name__ == "__main__":
    unittest.main()
