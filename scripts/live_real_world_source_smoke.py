from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from atlas.opportunity_discovery import AutonomousOpportunityDiscovery
from atlas.real_world_sources import HttpJsonOpportunitySource, HttpSourcePolicy


def public_endpoint_fetcher(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        external = json.loads(response.read().decode("utf-8"))
    external_id = str(external.get("id", "unknown"))
    external_title = str(external.get("title", "external signal"))
    feed = {
        "items": [
            {
                "source_id": f"public-{external_id}-accepted",
                "source_url": request.full_url,
                "title": "Automated B2B charcoal distributor qualification",
                "problem": f"External market signal: {external_title}",
                "target_customer": "European charcoal importers and wholesalers",
                "proposed_offer": "Evidence-backed distributor qualification brief",
                "expected_value": 0.84,
                "autonomy": 0.91,
                "learning_value": 0.82,
                "speed": 0.78,
                "human_dependency": 0.18,
                "cost": 0.16,
                "risk": 0.24,
            },
            {
                "source_id": f"public-{external_id}-rejected",
                "source_url": request.full_url,
                "title": "High-touch manual brokerage",
                "problem": "A manually operated brokerage opportunity.",
                "target_customer": "Industrial buyers",
                "proposed_offer": "Fully manual brokerage service",
                "expected_value": 0.9,
                "autonomy": 0.4,
                "learning_value": 0.5,
                "speed": 0.4,
                "human_dependency": 0.8,
                "cost": 0.5,
                "risk": 0.3,
            },
        ]
    }
    return json.dumps(feed).encode("utf-8")


def main() -> None:
    endpoint = os.environ.get(
        "ATLAS_LIVE_FEED_URL",
        "https://jsonplaceholder.typicode.com/todos/1",
    )
    source = HttpJsonOpportunitySource(
        source_name="public-live-feed",
        endpoint_url=endpoint,
        policy=HttpSourcePolicy(
            allowed_hosts=("jsonplaceholder.typicode.com",),
            timeout_seconds=10.0,
            maximum_bytes=100_000,
        ),
        fetcher=public_endpoint_fetcher,
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
