from __future__ import annotations

import unittest

from atlas.patch_capabilities import classify_patch_capability


class PatchCapabilityTests(unittest.TestCase):
    def test_broken_link_replacement_is_classified(self) -> None:
        match = classify_patch_capability(
            {
                "title": "Fix broken link",
                "body": "In `README.md`, replace https://old.example/docs with https://new.example/docs.",
            }
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.capability_id, "broken_link_replacement")
        self.assertEqual(match.target_path, "README.md")

    def test_simple_python_test_expectation_is_classified(self) -> None:
        match = classify_patch_capability(
            {
                "title": "Fix failing test expected value",
                "body": "In `tests/test_total.py`, replace `assert total == 4` with `assert total == 5`.",
            }
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.capability_id, "simple_test_expectation_replacement")

    def test_json_configuration_scalar_is_classified(self) -> None:
        match = classify_patch_capability(
            {
                "title": "Update configuration",
                "body": "In `config.json`, set key `timeout` from `30` to `45`.",
            }
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.capability_id, "configuration_scalar_replacement")
        self.assertEqual(match.old_value, "30")
        self.assertEqual(match.new_value, "45")

    def test_open_ended_task_has_no_deterministic_capability(self) -> None:
        self.assertIsNone(
            classify_patch_capability(
                {"title": "Improve API", "body": "Refactor the API and add comprehensive tests."}
            )
        )


if __name__ == "__main__":
    unittest.main()
