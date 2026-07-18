from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal, Protocol

RunDecision = Literal["blocked", "research_more", "ready_for_approval", "learning"]
ActionAuthorization = Literal["auto_execute", "requires_approval", "forbidden"]


@dataclass(frozen=True)
class MissionInput:
    mission_id: str
    objective: str
    offer: str
    target_segment: str
    consent_scope: str
    maximum_web_signals: int = 10
    maximum_gmail_signals: int = 20
    maximum_prospects: int = 10

    def validate(self) -> None:
        if not all(value.strip() for value in (
            self.mission_id, self.objective, self.offer, self.target_segment, self.consent_scope
        )):
            raise ValueError("mission identity, objective, offer, segment and consent are required")
        for name in ("maximum_web_signals", "maximum_gmail_signals", "maximum_prospects"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class LiveSignal:
    signal_id: str
    source: Literal["web", "gmail"]
    content: str
    provenance: str
    accepted: bool = True


@dataclass(frozen=True)
class ProspectCandidate:
    prospect_id: str
    organization: str
    fit_score: float
    evidence_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.prospect_id.strip() or not self.organization.strip():
            raise ValueError("prospect identity is required")
        if not 0 <= self.fit_score <= 1:
            raise ValueError("fit_score must be between 0 and 1")
        if not self.evidence_ids:
            raise ValueError("prospect requires evidence")


@dataclass(frozen=True)
class ApprovalAction:
    action_id: str
    prospect_id: str
    action_type: str
    subject: str
    body: str
    authorization: ActionAuthorization


@dataclass(frozen=True)
class LiveMissionResult:
    mission_id: str
    decision: RunDecision
    accepted_web_signals: int
    accepted_gmail_signals: int
    qualified_prospects: int
    approval_actions: tuple[ApprovalAction, ...]
    reasons: tuple[str, ...]
    next_actions: tuple[str, ...]


class LiveInputAdapter(Protocol):
    read_only: bool

    def collect(self, mission: MissionInput, limit: int) -> Iterable[LiveSignal]: ...


class ProspectAdapter(Protocol):
    read_only: bool

    def discover(self, mission: MissionInput, evidence: tuple[LiveSignal, ...], limit: int) -> Iterable[ProspectCandidate]: ...


class ControlledLiveMissionRunner:
    """Run a bounded real-world commercial mission and queue outbound work for approval."""

    def __init__(self, *, minimum_web_evidence: int = 3, minimum_fit_score: float = 0.65) -> None:
        if minimum_web_evidence <= 0:
            raise ValueError("minimum_web_evidence must be positive")
        if not 0 <= minimum_fit_score <= 1:
            raise ValueError("minimum_fit_score must be between 0 and 1")
        self.minimum_web_evidence = minimum_web_evidence
        self.minimum_fit_score = minimum_fit_score

    @staticmethod
    def _collect(adapter: LiveInputAdapter, mission: MissionInput, limit: int, source: str) -> tuple[LiveSignal, ...]:
        if not getattr(adapter, "read_only", False):
            raise ValueError(f"{source} adapter must be read-only")
        items = tuple(adapter.collect(mission, limit))[:limit]
        return tuple(item for item in items if item.accepted and item.source == source and item.content.strip())

    def run(
        self,
        mission: MissionInput,
        *,
        web_adapter: LiveInputAdapter,
        gmail_adapter: LiveInputAdapter,
        prospect_adapter: ProspectAdapter,
    ) -> LiveMissionResult:
        mission.validate()
        web = self._collect(web_adapter, mission, mission.maximum_web_signals, "web")
        gmail = self._collect(gmail_adapter, mission, mission.maximum_gmail_signals, "gmail")

        if len(web) < self.minimum_web_evidence:
            return LiveMissionResult(
                mission.mission_id, "research_more", len(web), len(gmail), 0, (),
                ("insufficient accepted Web evidence",),
                ("collect additional independent Web evidence",),
            )

        if not getattr(prospect_adapter, "read_only", False):
            raise ValueError("prospect adapter must be read-only")
        discovered = tuple(prospect_adapter.discover(mission, web, mission.maximum_prospects))[:mission.maximum_prospects]
        qualified: list[ProspectCandidate] = []
        known_evidence = {item.signal_id for item in web}
        for prospect in discovered:
            prospect.validate()
            if not set(prospect.evidence_ids).issubset(known_evidence):
                continue
            if prospect.fit_score >= self.minimum_fit_score:
                qualified.append(prospect)
        qualified.sort(key=lambda item: (-item.fit_score, item.prospect_id))

        if not qualified:
            return LiveMissionResult(
                mission.mission_id, "blocked", len(web), len(gmail), 0, (),
                ("no evidence-backed prospect satisfies the fit threshold",),
                ("revise target segment or prospect discovery query",),
            )

        actions = tuple(
            ApprovalAction(
                action_id=f"approve-{mission.mission_id}-{prospect.prospect_id}",
                prospect_id=prospect.prospect_id,
                action_type="email_draft",
                subject=f"Potential fit for {prospect.organization}",
                body=(
                    f"Hello,\n\nWe believe {mission.offer} may be relevant to {prospect.organization} "
                    f"within {mission.target_segment}. Would a short exchange be useful?\n"
                ),
                authorization="requires_approval",
            )
            for prospect in qualified
        )
        decision: RunDecision = "learning" if gmail else "ready_for_approval"
        reasons = (
            "real Gmail observations are available for learning" if gmail
            else "evidence-backed outreach drafts are ready for human approval",
        )
        next_actions = (
            "classify Gmail responses and update experiment metrics" if gmail
            else "review and approve or reject outbound drafts",
        )
        return LiveMissionResult(
            mission.mission_id, decision, len(web), len(gmail), len(qualified), actions, reasons, next_actions
        )

    def write(self, result: LiveMissionResult, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "live_mission": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
