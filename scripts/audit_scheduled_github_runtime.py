#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
OUTPUT = ROOT / "results" / "scheduled_github_runtime_audit.json"
MARKER = "uses: ./.github/actions/github-runtime-preflight"


def main() -> int:
    rows = []
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        scheduled = "schedule:" in text
        if not scheduled:
            continue
        has_preflight = MARKER in text
        rows.append({
            "workflow": str(path.relative_to(ROOT)),
            "scheduled": True,
            "github_runtime_preflight": has_preflight,
            "status": "compliant" if has_preflight else "migration_required",
        })
    missing = [row for row in rows if not row["github_runtime_preflight"]]
    payload = {
        "schema_version": "1.0",
        "scheduled_workflows": len(rows),
        "compliant_workflows": len(rows) - len(missing),
        "migration_required": len(missing),
        "workflows": rows,
        "truth": "Prompt text is not runtime authorization; only authenticated preflight proves GitHub access.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if not missing else 3


if __name__ == "__main__":
    raise SystemExit(main())
