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
        self.assertIn("at least one maturity domain must improve", compare_scorecards(previous, current).blockers)

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
