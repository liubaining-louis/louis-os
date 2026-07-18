from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlas.venture_runtime import CeoAgent, Opportunity, VentureDecisionEngine, build_dry_run_artifact


def load_opportunities(path: Path) -> list[Opportunity]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("opportunity input must be a JSON array")
    return [Opportunity(**item) for item in raw]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded Autonomous Venture Builder dry-run")
    parser.add_argument("--input", required=True, type=Path, help="JSON array of evidence-backed opportunities")
    parser.add_argument("--output", required=True, type=Path, help="Path for the generated decision artifact")
    parser.add_argument("--venture-id", default="avb-dry-run-001")
    args = parser.parse_args()

    opportunities = load_opportunities(args.input)
    engine = VentureDecisionEngine()
    ranking = engine.rank(opportunities)
    decision = CeoAgent(engine).decide(opportunities)
    artifact = build_dry_run_artifact(args.venture_id, decision, ranking, args.output)
    print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
