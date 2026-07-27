"""Delivery-method compatibility policy for paid opportunities.

An explicit payer prohibition of AI or automation is a policy rejection, not a
capability gap. The checks are intentionally phrase-based and fail closed only on
explicit prohibitions; positive statements such as "AI is acceptable" remain valid.
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


def evidence_text(opportunity: Mapping[str, Any]) -> str:
    pieces = [
        str(opportunity.get("title") or ""),
        str(opportunity.get("description") or ""),
    ]
    pieces.extend(str(item) for item in opportunity.get("payment_evidence") or [])
    pieces.extend(str(item) for item in opportunity.get("evidence") or [])
    return "\n".join(pieces)


def explicitly_prohibits_automated_delivery(opportunity: Mapping[str, Any]) -> bool:
    text = evidence_text(opportunity)
    return any(pattern.search(text) is not None for pattern in _PROHIBITION_PATTERNS)


def reject_incompatible_delivery_methods(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    rejected = 0
    for raw in rows:
        item = dict(raw)
        if explicitly_prohibits_automated_delivery(item):
            decision = dict(item.get("decision") or {})
            blockers = [str(value) for value in decision.get("blockers") or []]
            if "automation_prohibited_by_payer" not in blockers:
                blockers.append("automation_prohibited_by_payer")
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
                    "policy_rejection": "automation_prohibited_by_payer",
                    "policy_rejection_verified": True,
                    "capability_gap_allowed": False,
                }
            )
            item["decision"] = decision
            item["metadata"] = metadata
            rejected += 1
        output.append(item)
    return output, rejected
