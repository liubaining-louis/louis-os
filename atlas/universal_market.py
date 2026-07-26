"""Universal, evidence-first internet opportunity normalization and routing.

The market engine is deliberately source-agnostic. Source adapters collect facts; this
module validates, deduplicates and routes each paid opportunity without relaxing legal,
identity, account, payment or platform-rule boundaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse, urlunparse


TERMINAL_REJECTIONS = {
    "illegal_or_prohibited",
    "unauthorized_security_testing",
    "payment_unverified",
    "source_untrusted",
    "physically_inaccessible",
}


@dataclass(frozen=True)
class SourceState:
    source_id: str
    category: str
    status: str
    reason: str = ""
    evidence: tuple[str, ...] = ()
    observed_count: int = 0

    def validate(self) -> None:
        if not self.source_id.strip() or not self.category.strip() or not self.status.strip():
            raise ValueError("source state requires source_id, category and status")
        if self.observed_count < 0:
            raise ValueError("source observed_count cannot be negative")


@dataclass(frozen=True)
class InternetOpportunity:
    source_id: str
    source_category: str
    source_url: str
    title: str
    description: str
    reward_amount: float
    currency: str
    reward_verified: bool
    payment_evidence: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    observed_at: str
    deadline: str = ""
    account_required: bool = False
    terms_required: bool = False
    legal_entity_required: bool = False
    identity_or_kyc_required: bool = False
    security_scope_authorized: bool = True
    physical_presence_required: bool = False
    accessibility: float = 1.0
    human_dependency: float = 0.0
    risk: float = 0.0
    cost: float = 0.0
    competition: float = 0.5
    time_to_cash_days: int = 30
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        required = {
            "source_id": self.source_id,
            "source_category": self.source_category,
            "source_url": self.source_url,
            "title": self.title,
            "description": self.description,
            "currency": self.currency,
            "observed_at": self.observed_at,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing opportunity fields: {', '.join(missing)}")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("source_url must be an absolute HTTPS URL")
        if self.reward_amount < 0:
            raise ValueError("reward_amount cannot be negative")
        if self.reward_verified and (self.reward_amount <= 0 or not self.payment_evidence):
            raise ValueError("verified reward requires a positive amount and payment evidence")
        if not self.required_capabilities:
            raise ValueError("required_capabilities cannot be empty")
        for name in ("accessibility", "human_dependency", "risk", "cost", "competition"):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.time_to_cash_days < 0:
            raise ValueError("time_to_cash_days cannot be negative")

    @property
    def canonical_url(self) -> str:
        parsed = urlparse(self.source_url)
        normalized = parsed._replace(fragment="", query="")
        return urlunparse(normalized).rstrip("/")

    @property
    def opportunity_id(self) -> str:
        fingerprint = f"{self.source_id}|{self.canonical_url}|{self.title.strip().casefold()}"
        return "market-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    status: str
    evidence: tuple[str, ...] = ()
    handler: str = ""
    test_command: str = ""

    def validate(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("capability_id is required")
        if self.status not in {"validated", "experimental", "unavailable", "forbidden"}:
            raise ValueError("unknown capability status")
        if self.status == "validated" and not self.evidence:
            raise ValueError("validated capability requires evidence")


class CapabilityRegistry:
    def __init__(self, capabilities: Iterable[CapabilityDefinition]) -> None:
        values = tuple(capabilities)
        ids = [item.capability_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("capability ids must be unique")
        for item in values:
            item.validate()
        self._items = {item.capability_id: item for item in values}

    @classmethod
    def from_file(cls, path: str | Path) -> "CapabilityRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("capability registry schema_version must be 1.0")
        raw = payload.get("capabilities")
        if not isinstance(raw, list):
            raise ValueError("capability registry must contain a capabilities list")
        return cls(
            CapabilityDefinition(
                capability_id=str(item.get("id") or ""),
                status=str(item.get("status") or ""),
                evidence=tuple(str(value) for value in item.get("evidence") or []),
                handler=str(item.get("handler") or ""),
                test_command=str(item.get("test_command") or ""),
            )
            for item in raw
            if isinstance(item, Mapping)
        )

    def status(self, capability_id: str) -> str:
        item = self._items.get(capability_id)
        return item.status if item else "unavailable"

    def validated(self, capability_id: str) -> bool:
        return self.status(capability_id) == "validated"

    def experimental(self, capability_id: str) -> bool:
        return self.status(capability_id) == "experimental"

    def missing(self, required: Sequence[str]) -> list[str]:
        return [item for item in required if not self.validated(item)]


@dataclass(frozen=True)
class OpportunityDecision:
    opportunity_id: str
    status: str
    score: float
    missing_capabilities: tuple[str, ...]
    blockers: tuple[str, ...]
    next_action: str
    human_action_minimal: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    priority_score: float
    originating_opportunity_ids: tuple[str, ...]
    market_value: float
    specification: Mapping[str, Any]

    @property
    def marker(self) -> str:
        return f"<!-- louis-capability-gap:{self.capability_id} -->"


@dataclass(frozen=True)
class MarketEvaluation:
    generated_at: str
    source_states: tuple[SourceState, ...]
    opportunities: tuple[InternetOpportunity, ...]
    decisions: tuple[OpportunityDecision, ...]
    capability_gaps: tuple[CapabilityGap, ...]
    rejected_inputs: tuple[Mapping[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "generated_at": self.generated_at,
            "source_states": [asdict(item) for item in self.source_states],
            "opportunity_count": len(self.opportunities),
            "decision_counts": {
                status: sum(item.status == status for item in self.decisions)
                for status in ("executable_now", "prepare_then_gate", "capability_build", "rejected")
            },
            "opportunities": [
                {
                    **asdict(opportunity),
                    "opportunity_id": opportunity.opportunity_id,
                    "canonical_url": opportunity.canonical_url,
                    "decision": asdict(decision),
                }
                for opportunity, decision in zip(self.opportunities, self.decisions, strict=True)
            ],
            "capability_gaps": [asdict(item) | {"marker": item.marker} for item in self.capability_gaps],
            "rejected_inputs": list(self.rejected_inputs),
        }


class UniversalMarketEngine:
    """Rank and route opportunities while preserving exact external-action gates."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        *,
        minimum_accessibility: float = 0.20,
        maximum_risk: float = 0.80,
        maximum_capability_gaps: int = 5,
    ) -> None:
        self.capabilities = capabilities
        self.minimum_accessibility = minimum_accessibility
        self.maximum_risk = maximum_risk
        self.maximum_capability_gaps = maximum_capability_gaps

    def evaluate(
        self,
        opportunities: Iterable[InternetOpportunity],
        source_states: Iterable[SourceState] = (),
    ) -> MarketEvaluation:
        valid_sources: list[SourceState] = []
        for state in source_states:
            state.validate()
            valid_sources.append(state)

        rejected_inputs: list[Mapping[str, str]] = []
        deduplicated: dict[str, InternetOpportunity] = {}
        for opportunity in opportunities:
            try:
                opportunity.validate()
            except ValueError as exc:
                rejected_inputs.append(
                    {
                        "source_id": opportunity.source_id,
                        "source_url": opportunity.source_url,
                        "reason": str(exc),
                    }
                )
                continue
            existing = deduplicated.get(opportunity.canonical_url)
            if existing is None or self._raw_score(opportunity) > self._raw_score(existing):
                deduplicated[opportunity.canonical_url] = opportunity

        ordered = sorted(
            deduplicated.values(),
            key=lambda item: (-self._raw_score(item), item.opportunity_id),
        )
        decisions = tuple(self._decide(item) for item in ordered)
        gaps = self._build_capability_gaps(ordered, decisions)
        return MarketEvaluation(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_states=tuple(valid_sources),
            opportunities=tuple(ordered),
            decisions=decisions,
            capability_gaps=tuple(gaps),
            rejected_inputs=tuple(rejected_inputs),
        )

    def _decide(self, opportunity: InternetOpportunity) -> OpportunityDecision:
        blockers: list[str] = []
        evidence = list(dict.fromkeys(opportunity.payment_evidence + opportunity.evidence))
        missing = self.capabilities.missing(opportunity.required_capabilities)
        experimental = [item for item in missing if self.capabilities.experimental(item)]
        unavailable = [item for item in missing if not self.capabilities.experimental(item)]

        if not opportunity.reward_verified:
            blockers.append("payment_unverified")
        if opportunity.source_category == "security_bounty" and not opportunity.security_scope_authorized:
            blockers.append("unauthorized_security_testing")
        if opportunity.physical_presence_required or opportunity.accessibility < self.minimum_accessibility:
            blockers.append("physically_inaccessible")
        if opportunity.risk > self.maximum_risk:
            blockers.append("illegal_or_prohibited")

        score = round(self._raw_score(opportunity), 2)
        if any(item in TERMINAL_REJECTIONS for item in blockers):
            return OpportunityDecision(
                opportunity_id=opportunity.opportunity_id,
                status="rejected",
                score=score,
                missing_capabilities=tuple(missing),
                blockers=tuple(blockers),
                next_action="preserve_evidence_and_continue_other_sources",
                human_action_minimal="none",
                evidence=tuple(evidence),
            )

        if missing:
            blockers.extend(f"capability_missing:{item}" for item in missing)
            if experimental:
                blockers.extend(f"capability_requires_validation:{item}" for item in experimental)
            return OpportunityDecision(
                opportunity_id=opportunity.opportunity_id,
                status="capability_build",
                score=score,
                missing_capabilities=tuple(missing),
                blockers=tuple(blockers),
                next_action="create_bounded_capability_spec_test_promote_and_retry",
                human_action_minimal="none",
                evidence=tuple(evidence),
            )

        external_gates: list[str] = []
        if opportunity.account_required:
            external_gates.append("account_required")
        if opportunity.terms_required:
            external_gates.append("terms_acceptance_required")
        if opportunity.legal_entity_required:
            external_gates.append("legal_entity_required")
        if opportunity.identity_or_kyc_required:
            external_gates.append("identity_or_kyc_required")
        if external_gates:
            return OpportunityDecision(
                opportunity_id=opportunity.opportunity_id,
                status="prepare_then_gate",
                score=score,
                missing_capabilities=(),
                blockers=tuple(external_gates),
                next_action="prepare_complete_submission_dossier_then_request_minimal_external_authorization",
                human_action_minimal=", ".join(external_gates),
                evidence=tuple(evidence),
            )

        return OpportunityDecision(
            opportunity_id=opportunity.opportunity_id,
            status="executable_now",
            score=score,
            missing_capabilities=(),
            blockers=(),
            next_action="route_to_verified_executor_and_require_submission_receipt",
            human_action_minimal="none",
            evidence=tuple(evidence),
        )

    @staticmethod
    def _raw_score(opportunity: InternetOpportunity) -> float:
        value = min(1.0, opportunity.reward_amount / 5_000.0) if opportunity.reward_amount else 0.0
        speed = 1.0 / (1.0 + opportunity.time_to_cash_days / 30.0)
        capability_breadth_penalty = min(0.25, max(0, len(opportunity.required_capabilities) - 1) * 0.04)
        score = 100.0 * (
            value * 0.30
            + speed * 0.20
            + opportunity.accessibility * 0.15
            + (1.0 - opportunity.human_dependency) * 0.10
            + (1.0 - opportunity.cost) * 0.10
            + (1.0 - opportunity.risk) * 0.10
            + (1.0 - opportunity.competition) * 0.05
            - capability_breadth_penalty
        )
        if opportunity.reward_verified:
            score += 8.0
        return max(0.0, min(100.0, score))

    def _build_capability_gaps(
        self,
        opportunities: Sequence[InternetOpportunity],
        decisions: Sequence[OpportunityDecision],
    ) -> list[CapabilityGap]:
        grouped: dict[str, list[tuple[InternetOpportunity, OpportunityDecision]]] = {}
        for opportunity, decision in zip(opportunities, decisions, strict=True):
            if decision.status != "capability_build":
                continue
            for capability_id in decision.missing_capabilities:
                if self.capabilities.status(capability_id) == "forbidden":
                    continue
                grouped.setdefault(capability_id, []).append((opportunity, decision))

        gaps: list[CapabilityGap] = []
        for capability_id, items in grouped.items():
            opportunity_ids = tuple(item.opportunity_id for item, _ in items)
            market_value = round(sum(item.reward_amount for item, _ in items), 2)
            priority = round(max(decision.score for _, decision in items) + min(20.0, len(items) * 3.0), 2)
            reference = max(items, key=lambda pair: pair[1].score)[0]
            specification = {
                "objective": f"Acquire and validate capability `{capability_id}` for real paid opportunities.",
                "originating_market_url": reference.source_url,
                "required_interface": {
                    "input": "canonical opportunity dossier and source evidence",
                    "output": "testable deliverable, validation evidence and execution receipt",
                },
                "acceptance_tests": [
                    "reject missing or unverified source evidence",
                    "produce a deterministic or bounded artifact",
                    "record hashes and test evidence",
                    "fail closed on legal, account, identity, payment and scope gates",
                    "pass a fixture based on the originating opportunity type",
                ],
                "promotion_rule": "Promote only after unit tests and one dry-run artifact; never infer external submission or revenue.",
                "budget_rule": "Use existing infrastructure first; any new paid dependency requires explicit approval.",
                "retry_action": "Re-run universal market qualification after promotion.",
            }
            gaps.append(
                CapabilityGap(
                    capability_id=capability_id,
                    priority_score=priority,
                    originating_opportunity_ids=opportunity_ids,
                    market_value=market_value,
                    specification=specification,
                )
            )
        gaps.sort(key=lambda item: (-item.priority_score, -item.market_value, item.capability_id))
        return gaps[: self.maximum_capability_gaps]
