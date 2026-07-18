from __future__ import annotations

import argparse
from pathlib import Path

from atlas.opportunity_discovery import AutonomousOpportunityDiscovery
from atlas.source_registry import OpportunitySourceRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ATLAS opportunity discovery from a source registry.")
    parser.add_argument("--config", required=True, help="Path to source registry JSON")
    parser.add_argument("--output", required=True, help="Path to discovery result JSON")
    args = parser.parse_args()

    registry = OpportunitySourceRegistry.from_file(args.config)
    sources = registry.build_sources()
    if not sources:
        raise SystemExit("no enabled opportunity sources")

    result = AutonomousOpportunityDiscovery().discover(
        sources=sources,
        output_path=Path(args.output),
    )
    print(
        f"signals={result.signal_count} accepted={result.accepted_count} "
        f"rejected={result.rejected_count} artifact={result.artifact_path}"
    )


if __name__ == "__main__":
    main()
