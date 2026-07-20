from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from atlas.maturity import compare_scorecards, load_scorecard, validate_evidence, verify_history


DOMAINS = ("architecture", "autonomy", "initiative", "results", "robustness", "safety", "memory")


def payload(identifier: str, measured_at: str, *, robustness: int = 8) -> dict:
    return {
        "assessment_id": identifier,
        "measured_at": measured_at,
        "revision": identifier,
        "domains": {
            name: {
                "score": robustness if name == "robustness" else 7,
                "rationale": f"Measured {name} at {robustness if name == 'robustness' else 7}",
                "evidence": [f"tests/{name}.py"] + (["atlas/maturity.py"] if name == "robustness" and robustness > 8 else []),
                "evidence_kind": "ci" if name == "robustness" else "local",
            }
            for name in DOMAINS
        },
    }


class MaturityGateTests(unittest.TestCase):
    def write(self, root: Path, name: str, data: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_promotes_one_evidenced_improvement_without_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "previous.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "current.json", payload("b", "2026-07-20T01:00:00Z", robustness=9)))
        result = compare_scorecards(previous, current)
        self.assertTrue(result.promoted)
        self.assertEqual(result.improved_domains, ("robustness",))

    def test_blocks_any_domain_regression(self) -> None:
        previous_data = payload("a", "2026-07-20T00:00:00Z")
        current_data = payload("b", "2026-07-20T01:00:00Z", robustness=9)
        current_data["domains"]["results"]["score"] = 6
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", previous_data))
            current = load_scorecard(self.write(root, "b.json", current_data))
        result = compare_scorecards(previous, current)
        self.assertFalse(result.promoted)
        self.assertEqual(result.regressions, ("results",))

    def test_blocks_unchanged_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", payload("b", "2026-07-20T01:00:00Z")))
        self.assertIn(
            "at least one maturity domain, high-severity finding or capability validation must improve",
            compare_scorecards(previous, current).blockers,
        )

    def test_promotes_evidenced_capability_validation_without_score_inflation(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z")
        current_data["validations"] = [
            {
                "validation_id": "authenticated-mcp-bridge",
                "domain": "architecture",
                "capability": "Codex can exchange messages with a dedicated Louis OS session over MCP.",
                "evidence": ["tests/test_louis_mcp.py"],
                "evidence_kind": "local",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", current_data))
        result = compare_scorecards(previous, current)
        self.assertTrue(result.promoted)
        self.assertEqual(result.improved_domains, ())
        self.assertEqual(result.validated_capabilities, ("authenticated-mcp-bridge",))

    def test_capability_validation_requires_new_domain_evidence(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z")
        current_data["validations"] = [
            {
                "validation_id": "no-new-proof",
                "domain": "architecture",
                "capability": "Claimed capability",
                "evidence": ["tests/architecture.py"],
                "evidence_kind": "local",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", current_data))
        self.assertIn(
            "capability validation no-new-proof requires new evidence for architecture",
            compare_scorecards(previous, current).blockers,
        )

    def test_capability_validation_history_is_append_only_and_immutable(self) -> None:
        previous_data = payload("a", "2026-07-20T00:00:00Z")
        previous_data["validations"] = [
            {
                "validation_id": "existing-capability",
                "domain": "architecture",
                "capability": "Original claim",
                "evidence": ["tests/new_architecture.py"],
                "evidence_kind": "local",
            }
        ]
        current_data = payload("b", "2026-07-20T01:00:00Z", robustness=9)
        current_data["validations"] = [
            {
                "validation_id": "existing-capability",
                "domain": "architecture",
                "capability": "Rewritten claim",
                "evidence": ["tests/new_architecture.py"],
                "evidence_kind": "local",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", previous_data))
            current = load_scorecard(self.write(root, "b.json", current_data))
        self.assertIn(
            "capability validation history must be immutable",
            compare_scorecards(previous, current).blockers,
        )

    def test_promotes_evidenced_critical_remediation_without_score_inflation(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z")
        current_data["remediations"] = [
            {
                "remediation_id": "security-auth-bypass",
                "domain": "safety",
                "severity": "critical",
                "finding": "Anonymous clients received authenticated sessions.",
                "evidence": ["tests/test_server_auth.py"],
                "evidence_kind": "ci",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", current_data))
        result = compare_scorecards(previous, current)
        self.assertTrue(result.promoted)
        self.assertEqual(result.improved_domains, ())
        self.assertEqual(result.remediated_findings, ("security-auth-bypass",))

    def test_remediation_requires_new_domain_evidence(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z")
        current_data["remediations"] = [
            {
                "remediation_id": "no-new-proof",
                "domain": "safety",
                "severity": "critical",
                "finding": "Finding",
                "evidence": ["tests/safety.py"],
                "evidence_kind": "local",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", current_data))
        result = compare_scorecards(previous, current)
        self.assertIn("remediation no-new-proof requires new evidence for safety", result.blockers)

    def test_improvement_requires_new_evidence(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z", robustness=9)
        current_data["domains"]["robustness"]["evidence"] = ["tests/robustness.py"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", payload("a", "2026-07-20T00:00:00Z")))
            current = load_scorecard(self.write(root, "b.json", current_data))
        self.assertIn("improved domain robustness requires new evidence", compare_scorecards(previous, current).blockers)

    def test_rejects_missing_domain(self) -> None:
        data = payload("a", "2026-07-20T00:00:00Z")
        del data["domains"]["memory"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), "invalid.json", data)
            with self.assertRaisesRegex(ValueError, "every maturity domain"):
                load_scorecard(path)

    def test_history_is_ordered_by_versioned_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (root / "atlas").mkdir()
            (root / "tests").mkdir()
            for name in DOMAINS:
                (root / "tests" / f"{name}.py").write_text("", encoding="utf-8")
            (root / "atlas" / "maturity.py").write_text("", encoding="utf-8")
            scorecards = root / "docs" / "maturity" / "scorecards"
            scorecards.mkdir(parents=True)
            self.write(scorecards, "002.json", payload("b", "2026-07-20T01:00:00Z", robustness=9))
            self.write(scorecards, "001.json", payload("a", "2026-07-20T00:00:00Z"))
            results = verify_history(scorecards.glob("*.json"))
        self.assertTrue(results[0].promoted)

    def test_rejects_missing_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write(root, "scorecard.json", payload("a", "2026-07-20T00:00:00Z"))
            with self.assertRaisesRegex(ValueError, "does not exist"):
                validate_evidence(load_scorecard(path), root)

    def test_blocks_evidence_kind_downgrade(self) -> None:
        current_data = payload("b", "2026-07-20T01:00:00Z", robustness=9)
        current_data["domains"]["architecture"]["evidence_kind"] = "local"
        previous_data = payload("a", "2026-07-20T00:00:00Z")
        previous_data["domains"]["architecture"]["evidence_kind"] = "ci"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = load_scorecard(self.write(root, "a.json", previous_data))
            current = load_scorecard(self.write(root, "b.json", current_data))
        self.assertIn("evidence kind regressed for architecture", compare_scorecards(previous, current).blockers)


if __name__ == "__main__":
    unittest.main()
