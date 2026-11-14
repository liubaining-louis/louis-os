from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from atlas.submission_executor import SubmissionAuthorization, execute_submission

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


class DryRunAdapter:
    def __init__(self, platform: str) -> None:
        self.platform = platform

    def revalidate(self, dossier: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "listing_open": True,
            "remote_eligible": True,
            "platform_compliant": True,
            "evidence": ["adapter:dry_run_revalidation"],
        }

    def submit(self, dossier: Mapping[str, Any]) -> Mapping[str, Any]:
        raise RuntimeError("DryRunAdapter cannot submit externally")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossiers", default=str(RESULTS / "decision_gated_dossiers.json"))
    parser.add_argument("--output", default=str(RESULTS / "submission_executor.json"))
    parser.add_argument("--platform", default="freelancer")
    parser.add_argument("--authorization-id", default="")
    args = parser.parse_args()

    source = Path(args.dossiers)
    payload = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {"dossiers": []}
    dossiers = payload.get("dossiers", []) if isinstance(payload, dict) else []
    results = []
    for dossier in dossiers:
        authorization = SubmissionAuthorization(
            authorization_id=args.authorization_id or "dry-run-authorization",
            dossier_id=str(dossier.get("dossier_id", "")),
            platform=args.platform,
            approved=True,
            approved_at="dry-run",
        )
        results.append(execute_submission(dossier, DryRunAdapter(args.platform), authorization, dry_run=True).to_dict())

    output = {
        "schema_version": "1.0",
        "mode": "dry_run",
        "input_count": len(dossiers),
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0,
        "results": results,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
