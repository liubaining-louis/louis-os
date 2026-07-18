from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from atlas.opportunity_discovery import OpportunitySignal


@dataclass(frozen=True)
class SourceCollectionStatus:
    source_name: str
    success: bool
    signal_count: int
    error_type: str = ""
    error_message: str = ""


class ResilientCompositeOpportunitySource:
    """Collect from independent sources without letting one failure stop the cycle."""

    def __init__(self, source_name: str, sources: Sequence[object]) -> None:
        if not source_name.strip():
            raise ValueError("source_name is required")
        if not sources:
            raise ValueError("sources is required")
        self.source_name = source_name
        self.sources = tuple(sources)
        self._statuses: tuple[SourceCollectionStatus, ...] = ()

    @property
    def statuses(self) -> tuple[SourceCollectionStatus, ...]:
        return self._statuses

    def collect(self) -> Iterable[OpportunitySignal]:
        signals: list[OpportunitySignal] = []
        statuses: list[SourceCollectionStatus] = []

        for index, source in enumerate(self.sources):
            collect = getattr(source, "collect", None)
            if not callable(collect):
                raise TypeError("all resilient sources must implement collect()")
            source_name = str(getattr(source, "source_name", f"source-{index}"))
            try:
                collected = list(collect())
            except Exception as exc:  # source isolation boundary
                statuses.append(
                    SourceCollectionStatus(
                        source_name=source_name,
                        success=False,
                        signal_count=0,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                continue

            signals.extend(collected)
            statuses.append(
                SourceCollectionStatus(
                    source_name=source_name,
                    success=True,
                    signal_count=len(collected),
                )
            )

        self._statuses = tuple(statuses)
        if not any(status.success for status in statuses):
            raise RuntimeError("all opportunity sources failed")
        return signals

    def report(self) -> list[dict[str, object]]:
        return [asdict(status) for status in self._statuses]
