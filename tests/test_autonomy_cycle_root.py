from __future__ import annotations

from pathlib import Path
import unittest

import scripts.autonomy_cycle as autonomy_cycle


class AutonomyCycleRootTests(unittest.TestCase):
    def test_runtime_state_uses_script_repository_root(self) -> None:
        expected_root = Path(autonomy_cycle.__file__).resolve().parents[1]

        self.assertEqual(expected_root, autonomy_cycle.ROOT)
        self.assertEqual(expected_root / "results", autonomy_cycle.RESULTS)
        self.assertEqual(autonomy_cycle.RESULTS / "autonomy_state.json", autonomy_cycle.STATE_PATH)
        self.assertEqual(autonomy_cycle.RESULTS / "autonomy_decisions.jsonl", autonomy_cycle.DECISIONS_PATH)

    def test_does_not_import_root_from_installed_atlas_package(self) -> None:
        source = Path(autonomy_cycle.__file__).read_text(encoding="utf-8")

        self.assertNotIn("from atlas.runner import ROOT", source)


if __name__ == "__main__":
    unittest.main()
