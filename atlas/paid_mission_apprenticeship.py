from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

STAGES = [
    "discovered", "qualified", "proposal_ready", "submitted", "response_received",
    "scope_agreed", "in_delivery", "delivered", "accepted", "payment_requested", "paid",
]

@dataclass(frozen=True)
class CoachingDecision:
    stage: str
    next_action: str
    owner: str
    missing_evidence: List[str]
    stop_condition: str
    risk: str
    countermeasure: str


def _has(record: Dict[str, Any], key: str) -> bool:
    value = record.get(key)
    return value not in (None, "", [], {}, False)


def determine_stage(record: Dict[str, Any]) -> str:
    if _has(record, "payment_receipt"): return "paid"
    if _has(record, "payment_request_receipt"): return "payment_requested"
    if _has(record, "acceptance_receipt"): return "accepted"
    if _has(record, "delivery_receipt"): return "delivered"
    if _has(record, "work_started_receipt"): return "in_delivery"
    if _has(record, "scope_agreement_receipt"): return "scope_agreed"
    if _has(record, "client_response_receipt"): return "response_received"
    if _has(record, "submission_receipt"): return "submitted"
    if record.get("proposal_ready") is True: return "proposal_ready"
    if record.get("qualified") is True: return "qualified"
    return "discovered"


def coach(record: Dict[str, Any]) -> CoachingDecision:
    stage = determine_stage(record)
    mapping = {
        "discovered": ("verify eligibility, scope, payment and acceptance criteria", "louis_os", ["fresh_status", "payment_terms", "acceptance_criteria"], "reject if any critical fact cannot be verified", "wasted effort", "fail closed before proposal"),
        "qualified": ("prepare a tailored fixed-scope proposal and bounded proof", "louis_os", ["proposal", "proof_sample", "delivery_estimate"], "stop if product fit is below 0.70", "generic proposal", "mirror buyer language and define one outcome"),
        "proposal_ready": ("submit through the authorized channel and capture receipt", "human_or_louis_os", ["submission_receipt"], "do not claim submission without receipt", "false pipeline", "require immutable external evidence"),
        "submitted": ("track response and send one evidence-based follow-up", "louis_os", ["client_response_receipt"], "stop after configured follow-up limit", "spam or reputation damage", "respect channel cadence and opt-outs"),
        "response_received": ("clarify scope, acceptance, deadline and payment trigger", "louis_os", ["scope_agreement_receipt"], "do not start material work without agreement", "scope creep", "write exclusions and change-control rule"),
        "scope_agreed": ("build delivery plan, tests, milestones and rollback", "louis_os", ["work_started_receipt", "delivery_plan"], "pause if required inputs are missing", "rework", "validate inputs before execution"),
        "in_delivery": ("complete, test and package the agreed deliverable", "louis_os", ["delivery_receipt", "test_evidence"], "stop on failed acceptance tests", "defective delivery", "run deterministic QA before handoff"),
        "delivered": ("request explicit acceptance against the checklist", "louis_os", ["acceptance_receipt"], "escalate only documented objections", "silent non-acceptance", "send concise acceptance request with evidence"),
        "accepted": ("request invoice payment or platform milestone release", "human_or_louis_os", ["payment_request_receipt"], "never mark paid at request stage", "payment delay", "state due date and payment method clearly"),
        "payment_requested": ("follow payment until receipt, then reconcile amount and fees", "louis_os", ["payment_receipt"], "escalate according to contract and platform rules", "non-payment", "document reminders and dispute evidence"),
        "paid": ("record net revenue, cycle time, defects and reusable lessons", "louis_os", [], "close only after reconciliation", "bad learning data", "store external receipt and actual net amount"),
    }
    action, owner, missing, stop, risk, counter = mapping[stage]
    return CoachingDecision(stage, action, owner, missing, stop, risk, counter)


def coach_portfolio(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for record in records:
        decision = coach(record)
        output.append({"opportunity_id": record.get("opportunity_id"), **decision.__dict__})
    return output
