from __future__ import annotations

import json
from typing import Any

_DATA_TERMS = {
    "gmail", "email", "e-mail", "mail", "inbox", "boîte mail", "boite mail",
    "drive", "calendar", "slack", "crm", "facture", "thread", "fil de discussion",
}


def requires_external_evidence(objective: str) -> bool:
    text = objective.casefold()
    return any(term in text for term in _DATA_TERMS)


def _valid_evidence_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    source = str(item.get("source", "")).strip()
    content = str(item.get("content", "")).strip()
    return bool(source and content)


def normalize_evidence(context: dict[str, Any]) -> list[dict[str, Any]]:
    raw = context.get("evidence", [])
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not _valid_evidence_item(item):
            continue
        normalized.append({
            "source": str(item.get("source", "")).strip(),
            "reference": str(item.get("reference", "")).strip(),
            "content": str(item.get("content", "")).strip(),
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
        })
    return normalized


def has_external_evidence(context: dict[str, Any]) -> bool:
    return bool(normalize_evidence(context))


def evidence_gate_error(objective: str, context: dict[str, Any]) -> str | None:
    if requires_external_evidence(objective) and not has_external_evidence(context):
        return (
            "external_evidence_required: this mission asks for connected-source data, "
            "but no evidence bundle was supplied. Refusing to fabricate records or metrics."
        )
    return None


def format_evidence_context(context: dict[str, Any], max_chars: int = 30000) -> str:
    evidence = normalize_evidence(context)
    if not evidence:
        return ""
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[:max_chars] + "\n[evidence bundle truncated]"
