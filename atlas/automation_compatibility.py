"""Delivery-method, eligibility and sensitive-data policy for paid opportunities.

Explicit payer prohibitions of AI/automation, identity or location requirements that
Louis OS cannot truthfully satisfy, requests for sensitive personal records, mass
reproduction of protected works, and clearly sub-floor hourly tasks are policy
rejections rather than capability gaps. The checks are phrase-based and fail closed
on concrete evidence in the public listing.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


_PROHIBITION_PATTERNS = (
    re.compile(r"\bno\s+ai\b", re.I),
    re.compile(r"\bno\s+ai[-\s]generated\b", re.I),
    re.compile(r"\bno\s+artificial\s+intelligence\b", re.I),
    re.compile(r"\bdo\s+not\s+use\s+ai\b", re.I),
    re.compile(r"\bwithout\s+ai\b", re.I),
    re.compile(r"\bai\s+tools?\s+(?:are\s+)?prohibited\b", re.I),
    re.compile(r"\bai[-\s]generated\s+(?:wording|content|text|copy)\s+is\s+not\s+acceptable\b", re.I),
    re.compile(r"\b(?:human[-\s]written|written\s+by\s+a\s+human)\s+only\b", re.I),
    re.compile(r"\bmust\s+be\s+written\s+by\s+a\s+human\b", re.I),
    re.compile(r"\bmanual\s+only\b", re.I),
    re.compile(r"\bno\s+automated\s+tools?\b", re.I),
    re.compile(r"\bno\s+automation\b", re.I),
)

_UNVERIFIABLE_ELIGIBILITY_PATTERNS = (
    re.compile(r"\bnative\s+(?:thai|malay|speaker|speakers)\b", re.I),
    re.compile(r"\bnative\s+speaker\b", re.I),
    re.compile(r"\bstandard\s+(?:thai|malaysian|native)\s+accent\b", re.I),
    re.compile(r"\blocated\s+in\s+(?:thailand|malaysia)\b", re.I),
    re.compile(r"\bmust\s+be\s+based\s+in\b", re.I),
    re.compile(r"\bgovernment[-\s]issued\s+id\b", re.I),
    re.compile(r"\bpersonal\s+voice\s+recording\b", re.I),
)

_SENSITIVE_RECORD_PATTERNS = (
    re.compile(r"\bprison\s+(?:call|calls|visitor|visit)\b", re.I),
    re.compile(r"\binmate\b", re.I),
    re.compile(r"\bincarcerated\s+individual\b", re.I),
    re.compile(r"\bphone\s+call\s+transcript\b", re.I),
    re.compile(r"\bvisitor\s+logs?\b", re.I),
    re.compile(r"\bcriminal\s+(?:record|background)\b", re.I),
    re.compile(r"\bmedical\s+records?\b", re.I),
    re.compile(r"\bemployment\s+verification\b", re.I),
    re.compile(r"\bbackground\s+(?:check|verification)\b", re.I),
    re.compile(r"\bcandidate\s+consent\s+form\b", re.I),
)

_COPYRIGHT_REPRODUCTION_PATTERNS = (
    re.compile(r"\b(?:copy|scrape|download|reproduce|republish)\b.{0,80}\b(?:song\s+lyrics?|lyrics?)\b", re.I | re.S),
    re.compile(r"\b(?:500|hundreds?\s+of|bulk)\s+(?:songs?|lyrics?)\b", re.I),
    re.compile(r"\b(?:copy|scrape|download|reproduce|republish)\b.{0,80}\b(?:books?|articles?|paywalled\s+content)\b", re.I | re.S),
    re.compile(r"\b(?:genius|azlyrics|metrolyrics)\b", re.I),
)

_HOURLY_RANGE_PATTERN = re.compile(
    r"(?P<symbol>[$€£])\s*(?P<minimum>[0-9]+(?:\.[0-9]+)?)\s*-\s*(?P=symbol)?\s*"
    r"(?P<maximum>[0-9]+(?:\.[0-9]+)?)\s*(?:/\s*(?:hr|hour)|per\s+hour)",
    re.I,
)
_MINIMUM_CASH_FIRST_HOURLY = 10.0


def evidence_text(opportunity: Mapping[str, Any]) -> str:
    pieces = [
        str(opportunity.get("title") or ""),
        str(opportunity.get("description") or ""),
    ]
    pieces.extend(str(item) for item in opportunity.get("payment_evidence") or [])
    pieces.extend(str(item) for item in opportunity.get("evidence") or [])
    return "\n".join(pieces)


def policy_rejection_reason(opportunity: Mapping[str, Any]) -> str | None:
    text = evidence_text(opportunity)
    if any(pattern.search(text) is not None for pattern in _PROHIBITION_PATTERNS):
        return "automation_prohibited_by_payer"
    if any(pattern.search(text) is not None for pattern in _UNVERIFIABLE_ELIGIBILITY_PATTERNS):
        return "unverifiable_personal_eligibility"
    if any(pattern.search(text) is not None for pattern in _SENSITIVE_RECORD_PATTERNS):
        return "sensitive_personal_records_request"
    if any(pattern.search(text) is not None for pattern in _COPYRIGHT_REPRODUCTION_PATTERNS):
        return "copyright_reproduction_risk"
    hourly = _HOURLY_RANGE_PATTERN.search(text)
    if hourly and float(hourly.group("minimum")) < _MINIMUM_CASH_FIRST_HOURLY:
        return "hourly_rate_below_cash_first_floor"
    return None


def explicitly_prohibits_automated_delivery(opportunity: Mapping[str, Any]) -> bool:
    return policy_rejection_reason(opportunity) == "automation_prohibited_by_payer"


def reject_incompatible_delivery_methods(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    rejected = 0
    for raw in rows:
        item = dict(raw)
        reason = policy_rejection_reason(item)
        if reason:
            decision = dict(item.get("decision") or {})
            blockers = [str(value) for value in decision.get("blockers") or []]
            if reason not in blockers:
                blockers.append(reason)
            decision.update(
                {
                    "status": "rejected",
                    "blockers": blockers,
                    "missing_capabilities": [],
                    "next_action": "reject_and_continue_discovery",
                    "human_action_minimal": "none",
                    "evidence": list(
                        dict.fromkeys(
                            [
                                *[str(value) for value in decision.get("evidence") or []],
                                *[str(value) for value in item.get("evidence") or []],
                            ]
                        )
                    ),
                }
            )
            metadata = dict(item.get("metadata") or {})
            metadata.update(
                {
                    "policy_rejection": reason,
                    "policy_rejection_verified": True,
                    "capability_gap_allowed": False,
                    "submission_dossier_prepared": False,
                    "human_action_instructions": [],
                }
            )
            item["decision"] = decision
            item["metadata"] = metadata
            rejected += 1
        output.append(item)
    return output, rejected
