from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

ProspectStatus = Literal["qualified", "disqualified"]
ActionAuthorization = Literal["auto_execute", "requires_approval", "forbidden"]
MarketSignal = Literal["no_response", "negative", "neutral", "positive", "commercial_intent"]
ExperimentDecision = Literal["continue", "revise", "stop", "promote"]


@dataclass(frozen=True)
class Prospect:
    prospect_id: str
    organization: str
    contact_channel: str
    fit_score: float
    evidence_ids: tuple[str, ...]

    def validate(self) -> None:
        if not all(value.strip() for value in (self.prospect_id, self.organization, self.contact_channel)):
            raise ValueError("prospect identity and channel are required")
        if not 0 <= self.fit_score <= 1:
            raise ValueError("fit_score must be between 0 and 1")
        if not self.evidence_ids:
            raise ValueError("prospect qualification requires evidence")


@dataclass(frozen=True)
class OutreachDraft:
    prospect_id: str
    subject: str
    body: str
    authorization: ActionAuthorization
    rationale: str


@dataclass(frozen=True)
class MarketObservation:
    prospect_id: str
    signal: MarketSignal
    response_text: str = ""
    estimated_value: float = 0.0

    def validate(self) -> None:
        if not self.prospect_id.strip():
            raise ValueError("prospect_id is required")
        if self.estimated_value < 0:
            raise ValueError("estimated_value cannot be negative")


@dataclass(frozen=True)
class MarketExperimentResult:
    opportunity_id: str
    decision: ExperimentDecision
    qualified_prospects: int
    approval_required_drafts: int
    responses: int
    positive_signals: int
    commercial_intents: int
    response_rate: float
    positive_rate: float
    estimated_pipeline_value: float
    reasons: tuple[str, ...]
    next_actions: tuple[str, ...]


class RealMarketExperimentLoop:
    """Prepare safe outreach and learn deterministically from real market observations."""

    def __init__(
        self,
        *,
        minimum_fit_score: float = 0.60,
        minimum_sample_size: int = 5,
        promote_positive_rate: float = 0.30,
        stop_positive_rate: float = 0.05,
    ) -> None:
        for value, name in (
            (minimum_fit_score, "minimum_fit_score"),
            (promote_positive_rate, "promote_positive_rate"),
            (stop_positive_rate, "stop_positive_rate"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if minimum_sample_size <= 0:
            raise ValueError("minimum_sample_size must be positive")
        if stop_positive_rate > promote_positive_rate:
            raise ValueError("stop threshold cannot exceed promote threshold")
        self.minimum_fit_score = minimum_fit_score
        self.minimum_sample_size = minimum_sample_size
        self.promote_positive_rate = promote_positive_rate
        self.stop_positive_rate = stop_positive_rate

    def qualify(self, prospects: Iterable[Prospect]) -> tuple[Prospect, ...]:
        qualified: list[Prospect] = []
        for prospect in prospects:
            prospect.validate()
            if prospect.fit_score >= self.minimum_fit_score:
                qualified.append(prospect)
        return tuple(sorted(qualified, key=lambda item: (-item.fit_score, item.prospect_id)))

    def draft_outreach(self, prospect: Prospect, *, offer: str, value_proposition: str) -> OutreachDraft:
        prospect.validate()
        if prospect.fit_score < self.minimum_fit_score:
            raise ValueError("cannot draft outreach for an unqualified prospect")
        if not offer.strip() or not value_proposition.strip():
            raise ValueError("offer and value proposition are required")
        return OutreachDraft(
            prospect_id=prospect.prospect_id,
            subject=f"Potential fit for {prospect.organization}",
            body=(
                f"Hello,\n\nWe identified a potential fit between {prospect.organization} "
                f"and our offer: {offer}. {value_proposition}\n\n"
                "Would a short exchange be relevant?\n"
            ),
            authorization="requires_approval",
            rationale="external commercial communication requires human approval",
        )

    def evaluate(
        self,
        opportunity_id: str,
        qualified_prospects: Iterable[Prospect],
        drafts: Iterable[OutreachDraft],
        observations: Iterable[MarketObservation],
    ) -> MarketExperimentResult:
        if not opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        prospects = tuple(qualified_prospects)
        prospect_ids = {item.prospect_id for item in prospects}
        draft_items = tuple(drafts)
        observations_list = list(observations)
        for item in observations_list:
            item.validate()
            if item.prospect_id not in prospect_ids:
                raise ValueError("observation references an unknown prospect")

        responses = [item for item in observations_list if item.signal != "no_response"]
        positives = [item for item in observations_list if item.signal in {"positive", "commercial_intent"}]
        intents = [item for item in observations_list if item.signal == "commercial_intent"]
        sample_size = len(observations_list)
        response_rate = round(len(responses) / sample_size, 6) if sample_size else 0.0
        positive_rate = round(len(positives) / sample_size, 6) if sample_size else 0.0
        pipeline_value = round(sum(item.estimated_value for item in intents), 2)

        reasons: list[str] = []
        next_actions: list[str] = []
        if sample_size < self.minimum_sample_size:
            decision: ExperimentDecision = "continue"
            reasons.append("sample size is below the minimum learning threshold")
            next_actions.append("collect more market observations")
        elif positive_rate >= self.promote_positive_rate and intents:
            decision = "promote"
            reasons.append("positive signal rate and commercial intent satisfy promotion gate")
            next_actions.append("prepare a bounded commercial follow-up for approval")
        elif positive_rate <= self.stop_positive_rate:
            decision = "stop"
            reasons.append("market signal rate is below the stop threshold")
            next_actions.append("archive the offer and preserve lessons")
        else:
            decision = "revise"
            reasons.append("market interest exists but does not satisfy promotion gate")
            next_actions.extend(("revise target segment or value proposition", "run a new bounded experiment"))

        return MarketExperimentResult(
            opportunity_id=opportunity_id,
            decision=decision,
            qualified_prospects=len(prospects),
            approval_required_drafts=sum(item.authorization == "requires_approval" for item in draft_items),
            responses=len(responses),
            positive_signals=len(positives),
            commercial_intents=len(intents),
            response_rate=response_rate,
            positive_rate=positive_rate,
            estimated_pipeline_value=pipeline_value,
            reasons=tuple(reasons),
            next_actions=tuple(next_actions),
        )

    def write(self, result: MarketExperimentResult, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "market_experiment": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
