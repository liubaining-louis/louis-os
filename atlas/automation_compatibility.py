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
    re.compile(r"\b(?:researcher|contractor|freelancer|candidate|applicant)\s+based\s+in\b", re.I),
    re.compile(r"\byou\s+must\s+be\s+in\s+(?:the\s+)?(?:u\.?s\.?a?|united\s+states|india|benin|thailand|malaysia)\b", re.I),
    re.compile(r"\bgovernment[-\s]issued\s+id\b", re.I),
    re.compile(r"\b(?:proven|demonstrable)\s+(?:professional\s+)?experience\b.{0,80}\b(?:recruitment|hiring|candidate\s+screening)\b", re.I | re.S),
    re.compile(r"\b(?:own|active|established)\s+(?:candidate\s+)?(?:database|network|talent\s+pool)\b", re.I),
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
    re.compile(r"\b(?:degree|university|academic|education)\s+(?:authenticity|verification|authentication)\b", re.I),
    re.compile(r"\bverify\b.{0,80}\b(?:degree|graduation\s+date|academic\s+record)\b", re.I | re.S),
    re.compile(r"\b(?:candidate|graduate|applicant)(?:['’]s)?\s+(?:consent\s+(?:letter|form)|id\s+copy)\b", re.I),
    re.compile(r"\b(?:registrar|records\s+office)\b.{0,80}\b(?:candidate|graduate|degree|confirmation)\b", re.I | re.S),
    re.compile(r"\bbackground\s+(?:check|verification)\b", re.I),
    re.compile(r"\bcandidate\s+consent\s+form\b", re.I),
)

_PLATFORM_EVASION_PATTERNS = (
    re.compile(r"\b(?:advanced\s+)?proxy\s+rotat(?:or|ion)\b", re.I),
    re.compile(r"\b(?:good\s+)?proxy\s+or\s+mobile\s+ip\b", re.I),
    re.compile(r"\bhuman\s+detection\b", re.I),
    re.compile(r"\b(?:bypass|solve|retry)\b.{0,60}\bcaptcha\b", re.I | re.S),
    re.compile(r"\bauto[-\s]?login\b.{0,120}\b(?:proxy|captcha|human\s+detection)\b", re.I | re.S),
)

_EXPLOITATION_PATTERNS = (
    re.compile(r"\bescort\s+services?\b", re.I),
    re.compile(r"\bcall\s+girls?\b", re.I),
)

_EXTERNAL_PROCUREMENT_PATTERNS = (
    re.compile(
        r"\b(?:organize|organise|coordinate|arrange)\b.{0,100}"
        r"\b(?:courier|shipment|shipping|physical\s+delivery)\b",
        re.I | re.S,
    ),
    re.compile(
        r"\b(?:facilitate|complete|place|make)\b.{0,80}"
        r"\b(?:purchase|order|payment)\b",
        re.I | re.S,
    ),
)

_COPYRIGHT_REPRODUCTION_PATTERNS = (
    re.compile(r"\b(?:copy|scrape|download|reproduce|republish)\b.{0,80}\b(?:song\s+lyrics?|lyrics?)\b", re.I | re.S),
    re.compile(r"\b(?:500|hundreds?\s+of|bulk)\s+(?:songs?|lyrics?)\b", re.I),
    re.compile(r"\b(?:copy|scrape|download|reproduce|republish)\b.{0,80}\b(?:books?|articles?|paywalled\s+content)\b", re.I | re.S),
    re.compile(r"\b(?:genius|azlyrics|metrolyrics)\b", re.I),
)

_REGULATED_FINANCIAL_SERVICE_PATTERN = re.compile(
    r"\b(?:financial\s+(?:consulting|advice|advis(?:er|or))|investment\s+management|"
    r"portfolio\s+management|konsultasi\s+investasi|penasihat\s+keuangan)\b",
    re.I,
)
_PERSONALIZED_FINANCIAL_ADVICE_PATTERN = re.compile(
    r"\b(?:personal\s+risk\s+profile|personalized\s+investment|asset\s+allocation|"
    r"broker\s+platform|investment\s+portfolio|profil\s+risiko\s+pribadi|"
    r"rekomendasi\s+instrumen|alokasi\s+aset|platform\s+broker|portofolio\s+investasi)\b",
    re.I,
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
        str(opportunity.get("skills") or ""),
        str(opportunity.get("category") or ""),
    ]
    pieces.extend(str(item) for item in opportunity.get("payment_evidence") or [])
    pieces.extend(str(item) for item in opportunity.get("evidence") or [])
    return "\n".join(pieces)


def policy_rejection_reason(opportunity: Mapping[str, Any]) -> str | None:
    text = evidence_text(opportunity)
    if any(pattern.search(text) is not None for pattern in _PROHIBITION_PATTERNS):
        return "automation_prohibited_by_payer"
    if any(pattern.search(text) is not None for pattern in _PLATFORM_EVASION_PATTERNS):
        return "platform_policy_evasion"
    if any(pattern.search(text) is not None for pattern in _EXPLOITATION_PATTERNS):
        return "sexual_services_or_exploitation_risk"
    if any(pattern.search(text) is not None for pattern in _EXTERNAL_PROCUREMENT_PATTERNS):
        return "external_procurement_or_physical_fulfillment"
    if any(pattern.search(text) is not None for pattern in _UNVERIFIABLE_ELIGIBILITY_PATTERNS):
        return "unverifiable_personal_eligibility"
    if any(pattern.search(text) is not None for pattern in _SENSITIVE_RECORD_PATTERNS):
        return "sensitive_personal_records_request"
    if any(pattern.search(text) is not None for pattern in _COPYRIGHT_REPRODUCTION_PATTERNS):
        return "copyright_reproduction_risk"
    if (
        _REGULATED_FINANCIAL_SERVICE_PATTERN.search(text)
        and _PERSONALIZED_FINANCIAL_ADVICE_PATTERN.search(text)
    ):
        return "regulated_personalized_financial_advice"
    hourly = _HOURLY_RANGE_PATTERN.search(text)
    if hourly and float(hourly.group("minimum")) < _MINIMUM_CASH_FIRST_HOURLY:
        return "hourly_rate_below_cash_first_floor"
    return None


def persistent_rejection_reason(
    opportunity: Mapping[str, Any],
    registry: Mapping[str, Any] | None,
) -> str | None:
    """Return an exact prior rejection without depending on mutable listing text."""

    if not isinstance(registry, Mapping):
        return None
    opportunity_id = str(opportunity.get("opportunity_id") or "").strip()
    source_url = str(opportunity.get("source_url") or "").strip().rstrip("/")
    for raw in registry.get("items") or []:
        if not isinstance(raw, Mapping) or raw.get("active") is False:
            continue
        blocked_id = str(raw.get("opportunity_id") or "").strip()
        blocked_url = str(raw.get("source_url") or "").strip().rstrip("/")
        if (blocked_id and blocked_id == opportunity_id) or (blocked_url and blocked_url == source_url):
            return str(raw.get("reason") or "persistently_rejected_opportunity")
    return None


def explicitly_prohibits_automated_delivery(opportunity: Mapping[str, Any]) -> bool:
    return policy_rejection_reason(opportunity) == "automation_prohibited_by_payer"


def reject_incompatible_delivery_methods(
    rows: Sequence[Mapping[str, Any]],
    *,
    persistent_rejections: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    rejected = 0
    for raw in rows:
        item = dict(raw)
        persistent_reason = persistent_rejection_reason(item, persistent_rejections)
        reason = persistent_reason or policy_rejection_reason(item)
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
                    "policy_rejection_source": "persistent_registry" if persistent_reason else "semantic_policy",
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
