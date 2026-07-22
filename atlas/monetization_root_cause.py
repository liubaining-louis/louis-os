from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Sequence

Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class RootCause:
    code: str
    severity: Severity
    confidence: float
    evidence: tuple[str, ...]
    explanation: str
    corrective_action: str
    success_metric: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MonetizationDiagnosis:
    revenue_confirmed_eur: float
    primary_cause: RootCause
    contributing_causes: tuple[RootCause, ...]
    time_to_first_euro_band: str
    next_experiment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_counts(candidates: Sequence[Mapping[str, Any]]) -> tuple[int, int, int]:
    total = len(candidates)
    executable = sum(
        item.get("readiness_status") == "executable_now"
        and item.get("external_prerequisites_cleared") is True
        for item in candidates
    )
    return total, executable, total - executable


def analyze_monetization(
    *,
    ledger: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    external_actions: Sequence[Mapping[str, Any]] = (),
    external_receipts: Sequence[Mapping[str, Any]] = (),
) -> MonetizationDiagnosis:
    revenue = float(ledger.get("revenue_confirmed_eur", ledger.get("revenue_received", 0.0)) or 0.0)
    total, executable, gated = _candidate_counts(candidates)
    submitted = int(ledger.get("external_actions_submitted", 0) or 0)
    replies = int(ledger.get("qualified_replies", 0) or 0)
    conversions = int(ledger.get("conversions", 0) or 0)
    verified_receipts = sum(bool(item.get("verified")) for item in external_receipts)
    tested_ready = sum(
        item.get("tested_deliverable") is True and item.get("status") in {"ready", "submitted"}
        for item in external_actions
    )

    if revenue > 0:
        cause = RootCause(
            "no_active_zero_revenue_cause",
            "low",
            1.0,
            (f"revenue_confirmed_eur={revenue}",),
            "Verified revenue exists; the zero-revenue condition is no longer active.",
            "Repeat the proven offer and preserve positive net margin.",
            "second verified profitable payment",
        )
        return MonetizationDiagnosis(revenue, cause, (), "already achieved", cause.corrective_action)

    causes: list[RootCause] = []
    if total == 0:
        causes.append(RootCause(
            "no_qualified_opportunity",
            "critical",
            0.99,
            ("qualified_candidates=0",),
            "The pipeline contains no qualified monetization opportunity, so no path to payment can start.",
            "Broaden sources and search terms while keeping the no-account, no-KYC and non-charcoal filters.",
            "at least 3 qualified opportunities in one cycle",
        ))
    elif executable == 0:
        causes.append(RootCause(
            "all_opportunities_gated",
            "critical",
            0.99,
            (f"qualified_candidates={total}", f"gated_candidates={gated}", "executable_candidates=0"),
            "Every qualified opportunity has an unmet external prerequisite, so none can reach an autonomous submission.",
            "Exclude gated candidates from execution ranking and redirect discovery toward public tasks requiring no account, claim, KYC, payment or user validation.",
            "executable_candidate_rate >= 30%",
        ))
    elif submitted == 0:
        causes.append(RootCause(
            "executable_work_not_submitted",
            "critical",
            0.96,
            (f"executable_candidates={executable}", f"tested_ready_actions={tested_ready}", "external_actions_submitted=0"),
            "Executable opportunities exist, but the pipeline has not produced a verified external market action.",
            "Select one executable candidate, build and test the smallest deliverable, then submit through an allow-listed reversible channel and record the receipt.",
            "one verified external submission receipt",
        ))
    elif replies == 0:
        causes.append(RootCause(
            "submitted_without_market_response",
            "high",
            0.92,
            (f"external_actions_submitted={submitted}", f"verified_receipts={verified_receipts}", "qualified_replies=0"),
            "At least one action was submitted, but no qualified response has been recorded.",
            "Run a bounded follow-up or pivot the message, segment or channel after the configured no-response threshold.",
            "qualified_response_rate > 0",
        ))
    elif conversions == 0:
        causes.append(RootCause(
            "interest_not_converted_to_payment_path",
            "high",
            0.9,
            (f"qualified_replies={replies}", "conversions=0", "revenue_confirmed_eur=0"),
            "Qualified interest exists but has not been converted into a priced commitment, invoice or payment.",
            "Move the strongest reply to a concrete priced offer with acceptance criteria and a verifiable payment path.",
            "one accepted paid offer or invoice",
        ))
    else:
        causes.append(RootCause(
            "conversion_without_verified_payment",
            "critical",
            0.95,
            (f"conversions={conversions}", "revenue_confirmed_eur=0"),
            "A conversion is recorded but no payment evidence is present.",
            "Audit conversion evidence and require a verified payment receipt before counting revenue.",
            "one verified payment receipt",
        ))

    if gated:
        causes.append(RootCause(
            "high_gated_share",
            "medium",
            round(gated / total, 2) if total else 0.0,
            (f"gated_candidates={gated}", f"qualified_candidates={total}"),
            "A large share of research effort is being spent on opportunities that cannot be executed autonomously.",
            "Penalize prerequisite-heavy sources and allocate more search budget to channels with historically executable candidates.",
            "gated_candidate_rate < 50%",
        ))

    primary = causes[0]
    if primary.code in {"no_qualified_opportunity", "all_opportunities_gated"}:
        band = "first euro not currently reachable"
    elif primary.code == "executable_work_not_submitted":
        band = "possible within 7-30 days after verified submission"
    elif primary.code == "submitted_without_market_response":
        band = "possible within 7-14 days if response signal appears"
    else:
        band = "possible within 1-7 days if the payment path is completed"

    return MonetizationDiagnosis(
        revenue_confirmed_eur=0.0,
        primary_cause=primary,
        contributing_causes=tuple(causes[1:]),
        time_to_first_euro_band=band,
        next_experiment=primary.corrective_action,
    )
