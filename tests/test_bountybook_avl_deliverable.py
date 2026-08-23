from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DELIVERABLE = ROOT / "deliverables" / "bountybook_1063de95" / "avl.py"
SPEC = importlib.util.spec_from_file_location("bountybook_avl", DELIVERABLE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
AVLTree = MODULE.AVLTree


class BountyBookAVLDeliverableTests(unittest.TestCase):
    def assert_balanced(self, tree: AVLTree) -> None:
        def visit(node):
            if node is None:
                return 0
            left = visit(node.left)
            right = visit(node.right)
            self.assertLessEqual(abs(left - right), 1)
            self.assertEqual(node.height, 1 + max(left, right))
            return node.height

        self.assertEqual(visit(tree._root), tree.height())

    def test_balance_survives_insertions_and_deletions(self) -> None:
        tree = AVLTree()
        values = [50, 20, 70, 10, 30, 60, 80, 25, 27, 26, 90, 5, 15]
        for value in values:
            tree.insert(value)
            self.assert_balanced(tree)
        tree.insert(30)
        self.assertEqual(tree.inorder(), sorted(set(values)))
        for value in [20, 70, 50, 5, 999]:
            tree.delete(value)
            self.assert_balanced(tree)
        self.assertEqual(tree.inorder(), sorted(set(values) - {20, 70, 50, 5}))

    def test_required_standalone_contract(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(DELIVERABLE)],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("All tests passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
