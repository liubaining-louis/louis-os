from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SourceMeshPolicyTests(unittest.TestCase):
    def test_source_mesh_requires_diversification_and_receipts(self) -> None:
        text = (ROOT / "docs/decisions/CASH_FIRST_SOURCE_MESH.md").read_text(encoding="utf-8")
        self.assertIn("must not depend on one marketplace", text)
        self.assertIn("Prepare a complete proposal dossier", text)
        self.assertIn("Never count a proposal, award, contract, payout or revenue without a platform receipt", text)
        self.assertIn("Continue adding independent official sources", text)


if __name__ == "__main__":
    unittest.main()
