from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from atlas.autonomous_venture_cycle import (
    AutonomousVentureCycle,
    BaselineSnapshot,
    ExperimentObservation,
    VentureCycleResult,
)
from atlas.opportunity_discovery import (
    AutonomousOpportunityDiscovery,
    DiscoveryResult,
    OpportunitySource,
)


@dataclass(frozen=True)
class OpportunityVentureRun:
    discovery: DiscoveryResult
    cycle: VentureCycleResult | None
    status: str


class OpportunityToVenturePipeline:
    """Discover opportunities, then feed accepted candidates into one bounded AVB cycle."""

    def __init__(
        self,
        discovery: AutonomousOpportunityDiscovery | None = None,
        cycle: AutonomousVentureCycle | None = None,
    ) -> None:
        self.discovery = discovery or AutonomousOpportunityDiscovery()
        self.cycle = cycle or AutonomousVentureCycle()

    def run(
        self,
        *,
        venture_id: str,
        sources: Iterable[OpportunitySource],
        baseline: BaselineSnapshot,
        output_dir: str | Path,
        success_threshold: float,
        observation: ExperimentObservation | None = None,
        external_action: bool = False,
        approval_granted: bool = False,
    ) -> OpportunityVentureRun:
        root = Path(output_dir)
        discovery_result = self.discovery.discover(
            sources=sources,
            output_path=root / "opportunity-discovery.json",
        )
        if not discovery_result.opportunities:
            return OpportunityVentureRun(
                discovery=discovery_result,
                cycle=None,
                status="no_eligible_opportunity",
            )

        cycle_result = self.cycle.run(
            venture_id=venture_id,
            opportunities=discovery_result.opportunities,
            baseline=baseline,
            output_dir=root / "venture-cycle",
            success_threshold=success_threshold,
            observation=observation,
            external_action=external_action,
            approval_granted=approval_granted,
        )
        return OpportunityVentureRun(
            discovery=discovery_result,
            cycle=cycle_result,
            status=cycle_result.status,
        )
