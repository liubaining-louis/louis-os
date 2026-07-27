#!/usr/bin/env python3
"""Generate reusable tested software micro-mission demos and receipts."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.software_micro_missions import capability_catalog, demo_bundles, validate_demo_bundle

RESULTS = ROOT / "results"
DEMOS_ROOT = RESULTS / "software_micro_mission_demos"
CATALOG_PATH = RESULTS / "software_micro_mission_catalog.json"
RECEIPT_PATH = RESULTS / "software_micro_mission_demo_receipts.json"
CYCLE_PATH = RESULTS / "universal_market_cycle.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    if DEMOS_ROOT.exists():
        shutil.rmtree(DEMOS_ROOT)
    DEMOS_ROOT.mkdir(parents=True, exist_ok=True)

    receipts: list[dict[str, Any]] = []
    for demo_id, files in demo_bundles().items():
        checks = validate_demo_bundle(demo_id, files)
        workspace = DEMOS_ROOT / demo_id
        workspace.mkdir(parents=True, exist_ok=True)
        file_receipts: list[dict[str, str]] = []
        for relative_path, content in sorted(files.items()):
            target = workspace / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            file_receipts.append(
                {
                    "path": str(target.relative_to(ROOT)),
                    "sha256": sha256(target),
                }
            )
        manifest = {
            "schema_version": "1.0",
            "demo_id": demo_id,
            "status": "validated",
            "checks": list(checks),
            "files": file_receipts,
            "generated_at": generated_at,
            "externally_deployed": False,
            "externally_submitted": False,
            "external_receipt": None,
            "revenue_verified": False,
        }
        manifest_path = workspace / "manifest.json"
        save_json(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path.relative_to(ROOT))
        manifest["manifest_sha256"] = sha256(manifest_path)
        receipts.append(manifest)

    catalog = capability_catalog()
    catalog.update(
        {
            "generated_at": generated_at,
            "capability_count": len(catalog["capabilities"]),
            "validated_demo_count": len(receipts),
            "demo_receipt_path": str(RECEIPT_PATH.relative_to(ROOT)),
            "demo_ids": [item["demo_id"] for item in receipts],
        }
    )
    save_json(CATALOG_PATH, catalog)
    save_json(
        RECEIPT_PATH,
        {
            "schema_version": "1.0",
            "generated_at": generated_at,
            "validated_demo_count": len(receipts),
            "receipts": receipts,
            "external_deployments_verified": 0,
            "external_submissions_verified": 0,
            "revenue_verified_eur": 0.0,
        },
    )

    cycle = load_json(CYCLE_PATH, {})
    cycle.update(
        {
            "software_micro_mission_engine": "active",
            "software_micro_mission_capability_count": len(catalog["capabilities"]),
            "software_micro_mission_validated_demo_count": len(receipts),
        }
    )
    if cycle.get("next_action") in (None, "", "activate_next_small_mission_source", "activate_next_authorized_official_source"):
        cycle["next_action"] = "search_validated_software_micro_missions"
    evidence = list(cycle.get("evidence") or [])
    for path in (CATALOG_PATH, RECEIPT_PATH):
        relative = str(path.relative_to(ROOT))
        if relative not in evidence:
            evidence.append(relative)
    cycle["evidence"] = evidence
    save_json(CYCLE_PATH, cycle)

    print(
        json.dumps(
            {
                "capabilities": len(catalog["capabilities"]),
                "validated_demos": len(receipts),
                "external_submissions": 0,
                "revenue_eur": 0.0,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
