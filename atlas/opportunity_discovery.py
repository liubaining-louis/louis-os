from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import urlparse

from atlas.venture_runtime import Opportunity, VentureDecisionEngine


@dataclass(frozen=True)
class OpportunitySignal:
    source_id: str
    source_url: str
    title: str
    problem: str
    target_customer: str
    proposed_offer: str
    expected_value: float
    autonomy: float
    learning_value: float
    speed: float
    human_dependency: float
    cost: float
    risk: float
    observed_at: str = ""

    def validate(self) -> None:
        required = {
            "source_id": self.source_id,
            "source_url": self.source_url,
            "title": self.title,
            "problem": self.problem,
            "target_customer": self.target_customer,
            "proposed_offer": self.proposed_offer,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing opportunity signal fields: {', '.join(missing)}")
        parsed = urlparse(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        for name in (
            "expected_value",
            "autonomy",
            "learning_value",
            "speed",
            "human_dependency",
            "cost",
            "risk",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


class OpportunitySource(Protocol):
    source_name: str

    def collect(self) -> Iterable[OpportunitySignal]: ...


@dataclass(frozen=True)
class DiscoveryResult:
    signal_count: int
    accepted_count: int
    rejected_count: int
    opportunities: list[Opportunity]
    rejected: list[dict[str, str]]
    artifact_path: str


class StaticOpportunitySource:
    """Deterministic source adapter used for tests and connector-fed signals."""

    def __init__(self, source_name: str, signals: Iterable[OpportunitySignal]) -> None:
        if not source_name.strip():
            raise ValueError("source_name is required")
        self.source_name = source_name
        self._signals = list(signals)

    def collect(self) -> Iterable[OpportunitySignal]:
        return list(self._signals)


class AutonomousOpportunityDiscovery:
    """Normalize, deduplicate and gate evidence-backed opportunity signals."""

    def __init__(
        self,
        *,
        minimum_autonomy: float = 0.80,
        maximum_human_dependency: float = 0.30,
        maximum_risk: float = 0.70,
        engine: VentureDecisionEngine | None = None,
    ) -> None:
        for value, name in (
            (minimum_autonomy, "minimum_autonomy"),
            (maximum_human_dependency, "maximum_human_dependency"),
            (maximum_risk, "maximum_risk"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.minimum_autonomy = minimum_autonomy
        self.maximum_human_dependency = maximum_human_dependency
        self.maximum_risk = maximum_risk
        self.engine = engine or VentureDecisionEngine()

    def discover(
        self,
        *,
        sources: Iterable[OpportunitySource],
        output_path: str | Path,
    ) -> DiscoveryResult:
        signals: list[tuple[str, OpportunitySignal]] = []
        for source in sources:
            for signal in source.collect():
                signals.append((source.source_name, signal))

        accepted: dict[str, Opportunity] = {}
        rejected: list[dict[str, str]] = []

        for source_name, signal in signals:
            try:
                signal.validate()
            except ValueError as exc:
                rejected.append({"source": source_name, "source_id": signal.source_id, "reason": str(exc)})
                continue

            reasons: list[str] = []
            if signal.autonomy < self.minimum_autonomy:
                reasons.append("autonomy below threshold")
            if signal.human_dependency > self.maximum_human_dependency:
                reasons.append("human dependency above threshold")
            if signal.risk > self.maximum_risk:
                reasons.append("risk above threshold")
            if reasons:
                rejected.append(
                    {
                        "source": source_name,
                        "source_id": signal.source_id,
                        "reason": "; ".join(reasons),
                    }
                )
                continue

            fingerprint = self._fingerprint(signal)
            candidate = Opportunity(
                opportunity_id=f"opp-{fingerprint[:12]}",
                title=signal.title.strip(),
                problem=signal.problem.strip(),
                target_customer=signal.target_customer.strip(),
                proposed_offer=signal.proposed_offer.strip(),
                evidence_references=[signal.source_url],
                expected_value=signal.expected_value,
                autonomy=signal.autonomy,
                learning_value=signal.learning_value,
                speed=signal.speed,
                human_dependency=signal.human_dependency,
                cost=signal.cost,
                risk=signal.risk,
            )
            existing = accepted.get(fingerprint)
            if existing is None:
                accepted[fingerprint] = candidate
            else:
                merged_refs = sorted(set(existing.evidence_references + candidate.evidence_references))
                accepted[fingerprint] = Opportunity(
                    **{**asdict(existing), "evidence_references": merged_refs}
                )

        ranked = self.engine.rank(accepted.values())
        opportunities = [item.opportunity for item in ranked]
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "signal_count": len(signals),
            "accepted_count": len(opportunities),
            "rejected_count": len(rejected),
            "opportunities": [
                {
                    **asdict(item.opportunity),
                    "decision_score": item.score,
                    "rationale": item.rationale,
                }
                for item in ranked
            ],
            "rejected": rejected,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return DiscoveryResult(
            signal_count=len(signals),
            accepted_count=len(opportunities),
            rejected_count=len(rejected),
            opportunities=opportunities,
            rejected=rejected,
            artifact_path=str(path),
        )

    @staticmethod
    def _fingerprint(signal: OpportunitySignal) -> str:
        normalized = "|".join(
            value.strip().lower()
            for value in (
                signal.title,
                signal.problem,
                signal.target_customer,
                signal.proposed_offer,
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
