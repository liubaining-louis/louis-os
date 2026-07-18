from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from atlas.opportunity_discovery import AutonomousOpportunityDiscovery
from atlas.real_world_sources import HttpJsonOpportunitySource, HttpSourcePolicy


def main() -> None:
    endpoint = os.environ.get(
        "ATLAS_LIVE_FEED_URL",
        "https://raw.githubusercontent.com/liubaining-louis/louis-os/test/live-real-world-source-smoke/tests/fixtures/live_opportunity_feed.json",
    )
    source = HttpJsonOpportunitySource(
        source_name="github-live-feed",
        endpoint_url=endpoint,
        policy=HttpSourcePolicy(
            allowed_hosts=("raw.githubusercontent.com",),
            timeout_seconds=10.0,
            maximum_bytes=100_000,
        ),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        artifact = Path(tmpdir) / "live-discovery.json"
        result = AutonomousOpportunityDiscovery().discover(
            sources=[source],
            output_path=artifact,
        )
        payload = json.loads(artifact.read_text(encoding="utf-8"))

        assert result.signal_count == 2, result
        assert result.accepted_count == 1, result
        assert result.rejected_count == 1, result
        assert result.opportunities[0].title == "Automated B2B charcoal distributor qualification"
        assert payload["opportunities"][0]["decision_score"] > 0
        assert "autonomy below threshold" in payload["rejected"][0]["reason"]
        assert "human dependency above threshold" in payload["rejected"][0]["reason"]

        print(json.dumps({
            "status": "PASS",
            "endpoint": endpoint,
            "signal_count": result.signal_count,
            "accepted_count": result.accepted_count,
            "rejected_count": result.rejected_count,
            "winner": result.opportunities[0].title,
            "decision_score": payload["opportunities"][0]["decision_score"],
            "rejection_reason": payload["rejected"][0]["reason"],
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
