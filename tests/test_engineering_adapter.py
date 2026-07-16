from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from atlas.engineering.codex_adapter import CodexEngineeringAdapter, JsonlEngineeringEvidenceStore
from atlas.engineering.evaluator import evaluate_benchmark
from atlas.engineering.models import CommandResult, EngineeringMission, PatchResult
from atlas.engineering.policies import PolicyViolation
from atlas.engineering.sandbox import LocalCommandSandbox


def command_result(exit_code: int = 0) -> CommandResult:
    return CommandResult("fake", exit_code, 1 if exit_code == 0 else 0, 0, int(exit_code != 0), 0.01, "", "")


class FakeRunner:
    def __init__(self, results=None):
        self.results = list(results or [command_result()])
        self.commands = []

    def run(self, command, cwd):
        self.commands.append((tuple(command), Path(cwd)))
        return self.results.pop(0)


class EngineeringAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        subprocess.run(("git", "init", "-b", "main"), cwd=self.root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=self.root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=self.root, check=True)
        (self.root / "tests").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "atlas" / "engineering").mkdir(parents=True)
        (self.root / "tests" / "sample.txt").write_text("before\n", encoding="utf-8")
        (self.root / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-m", "initial"), cwd=self.root, check=True, capture_output=True)
        subprocess.run(("git", "switch", "-c", "feature/test"), cwd=self.root, check=True, capture_output=True)
        self.mission = EngineeringMission(
            "m-1", str(self.root), ["tests/", "docs/", "atlas/engineering/"], "Improve a test"
        )
        self.adapter = CodexEngineeringAdapter(runner=FakeRunner(), python_executable=sys.executable)

    def test_inspection_is_read_only(self):
        before = self._tree_state()
        result = self.adapter.inspect_repository(self.mission)
        self.assertEqual(result.status, "completed")
        self.assertEqual(before, self._tree_state())

    def test_dry_run_is_default_and_does_not_write(self):
        self.assertTrue(self.mission.dry_run)
        result = self.adapter.generate_patch(self.mission, {"tests/sample.txt": "after\n"})
        self.assertTrue(result.dry_run)
        self.assertIn("+after", result.diff)
        self.assertEqual((self.root / "tests" / "sample.txt").read_text(), "before\n")

    def test_write_outside_allowed_paths_is_refused(self):
        result = self.adapter.generate_patch(self.mission, {"atlas/core.py": "safe\n"})
        self.assertEqual(result.status, "blocked")

    def test_modification_on_main_is_refused(self):
        subprocess.run(("git", "switch", "main"), cwd=self.root, check=True, capture_output=True)
        result = self.adapter.generate_patch(self.mission, {"tests/sample.txt": "after\n"})
        self.assertEqual(result.status, "blocked")
        self.assertIn("main", result.risks[0])

    def test_secret_path_and_content_are_refused(self):
        path_result = self.adapter.generate_patch(self.mission, {"docs/secrets/token.txt": "placeholder"})
        secret_value = "sk-" + "unit-test-credential"
        content_result = self.adapter.generate_patch(
            self.mission, {"docs/guide.md": "api_key=" + secret_value}
        )
        self.assertEqual(path_result.status, "approval_required")
        self.assertEqual(content_result.status, "approval_required")

    def test_destructive_action_is_approval_required(self):
        result = self.adapter.generate_patch(self.mission, {"docs/guide.md": "Run: drop database\n"})
        self.assertEqual(result.status, "approval_required")

    def test_failed_test_command_is_detected(self):
        adapter = CodexEngineeringAdapter(runner=FakeRunner([command_result(1)]), python_executable=sys.executable)
        result = adapter.run_tests(self.mission)[0]
        self.assertEqual(result.exit_code, 1)
        self.assertGreater(result.errors, 0)

    def test_benchmark_regression_is_detected(self):
        summary = {
            "baseline": {"score": 0.9, "pass_rate": 0.9, "critical_regressions": 0},
            "guarded_v1": {"score": 0.8, "pass_rate": 0.7, "critical_regressions": 1},
        }
        result = evaluate_benchmark("benchmark", summary, [command_result()], reproducible=True, evidence_complete=True)
        self.assertTrue(result.regression_detected)
        self.assertFalse(result.promotion_allowed)

    def test_promotion_is_blocked_when_evidence_is_missing(self):
        summary = {
            "baseline": {"score": 0.5, "pass_rate": 0.5, "critical_regressions": 0},
            "guarded_v1": {"score": 0.8, "pass_rate": 0.9, "critical_regressions": 0},
        }
        result = evaluate_benchmark("benchmark", summary, [command_result()], reproducible=False, evidence_complete=False)
        self.assertFalse(result.promotion_allowed)
        self.assertIn("benchmark is not reproducible", result.blockers)

    def test_summary_is_structured_and_json_serializable(self):
        inspection = self.adapter.inspect_repository(self.mission)
        patch = PatchResult("m-1", "completed", True, "diff", ["tests/sample.txt"])
        benchmark = evaluate_benchmark(
            "benchmark",
            {
                "baseline": {"score": 0.5, "pass_rate": 0.5, "critical_regressions": 0},
                "guarded_v1": {"score": 0.8, "pass_rate": 0.9, "critical_regressions": 0},
            },
            [command_result()],
            reproducible=True,
            evidence_complete=True,
        )
        summary = self.adapter.summarize_result(
            self.mission, inspection, patch, [command_result()], [benchmark]
        )
        payload = summary.to_dict()
        json.dumps(payload)
        self.assertEqual(payload["status"], "validation")

    def test_same_mission_is_idempotent(self):
        with tempfile.TemporaryDirectory() as evidence_dir:
            evidence = JsonlEngineeringEvidenceStore(Path(evidence_dir) / "evidence.jsonl")
            adapter = CodexEngineeringAdapter(runner=FakeRunner(), python_executable=sys.executable, evidence_store=evidence)
            first = adapter.inspect_repository(self.mission)
            second = adapter.inspect_repository(self.mission)
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(len(evidence.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_logs_are_truncated(self):
        sandbox = LocalCommandSandbox(((sys.executable, "-c"),), max_output_chars=40)
        result = sandbox.run((sys.executable, "-c", "print('x' * 200)"), self.root)
        self.assertLessEqual(len(result.stdout_excerpt), 60)
        self.assertIn("[output truncated]", result.stdout_excerpt)

    def test_secrets_are_redacted_from_errors_and_logs(self):
        sandbox = LocalCommandSandbox(((sys.executable, "-c"),), max_output_chars=200)
        secret_value = "sk-" + "unit-test-credential"
        program = "import sys; value='sk-' + 'unit-test-credential'; sys.stderr.write('api_key=' + value); raise SystemExit(1)"
        result = sandbox.run(
            (sys.executable, "-c", program),
            self.root,
        )
        self.assertNotIn(secret_value, result.stderr_excerpt)
        self.assertIn("[REDACTED]", result.stderr_excerpt)

    def test_risky_action_sets_approval_required(self):
        result = self.adapter.generate_patch(self.mission, {"docs/guide.md": "send email to a customer\n"})
        self.assertEqual(result.status, "approval_required")

    def test_risky_objective_sets_approval_required(self):
        mission = EngineeringMission(
            "m-risky", str(self.root), ["docs/"], "Deploy production now", dry_run=True
        )
        result = self.adapter.generate_patch(mission, {"docs/guide.md": "Safe text.\n"})
        self.assertEqual(result.status, "approval_required")

    def test_existing_safety_language_does_not_block_safe_addition(self):
        path = self.root / "docs" / "guide.md"
        path.write_text("payment is forbidden\n", encoding="utf-8")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-m", "document safety"), cwd=self.root, check=True, capture_output=True)
        result = self.adapter.generate_patch(
            self.mission, {"docs/guide.md": "payment is forbidden\nSafe dry-run note.\n"}
        )
        self.assertEqual(result.status, "completed")

    def test_sandbox_rejects_non_allowlisted_command(self):
        sandbox = LocalCommandSandbox(((sys.executable, "-m", "unittest"),))
        with self.assertRaises(PolicyViolation):
            sandbox.run(("git", "push"), self.root)

    def _tree_state(self):
        sha = subprocess.run(("git", "rev-parse", "HEAD"), cwd=self.root, check=True, capture_output=True, text=True).stdout
        status = subprocess.run(("git", "status", "--porcelain"), cwd=self.root, check=True, capture_output=True, text=True).stdout
        return sha, status


if __name__ == "__main__":
    unittest.main()
