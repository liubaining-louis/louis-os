from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import ROOT

_ALLOWED_TYPES = {"fact", "preference", "decision", "procedure", "outcome"}
_SECRET_PATTERNS = (
    re.compile(r"\bgsk_[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]+\b"),
)


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    created_at: str
    updated_at: str
    memory_type: str
    domain: str
    content: str
    confidence: float
    tags: list[str]
    source: str
    state: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_secret(value: str) -> bool:
    lowered = value.casefold()
    if any(marker in lowered for marker in ("api_key", "api key", "password", "secret=")):
        return True
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _validate(memory_type: str, domain: str, content: str, confidence: float) -> None:
    if memory_type not in _ALLOWED_TYPES:
        raise ValueError(f"unsupported memory_type: {memory_type}")
    if not domain.strip():
        raise ValueError("domain is required")
    if not content.strip():
        raise ValueError("content is required")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if _contains_secret(content):
        raise ValueError("memory content appears to contain a secret")


def _local_dir() -> Path:
    return ROOT / "results" / "memories"


def _firestore_collection():
    from google.cloud import firestore

    client = firestore.Client()
    return client.collection(os.environ.get("FIRESTORE_MEMORIES_COLLECTION", "memories"))


def create_memory(
    memory_type: str,
    domain: str,
    content: str,
    confidence: float,
    tags: list[str] | None = None,
    source: str = "user",
) -> MemoryRecord:
    tags = sorted({str(tag).strip().casefold() for tag in (tags or []) if str(tag).strip()})
    _validate(memory_type, domain, content, confidence)
    now = datetime.now(timezone.utc).isoformat()
    record = MemoryRecord(
        memory_id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        memory_type=memory_type,
        domain=domain.strip().casefold(),
        content=content.strip(),
        confidence=float(confidence),
        tags=tags,
        source=source.strip() or "unknown",
    )
    payload = record.to_dict()
    if os.environ.get("MEMORY_STORE", "local") == "firestore":
        _firestore_collection().document(record.memory_id).set(payload)
    else:
        path = _local_dir() / f"{record.memory_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def get_memory(memory_id: str) -> dict[str, Any] | None:
    if os.environ.get("MEMORY_STORE", "local") == "firestore":
        snapshot = _firestore_collection().document(memory_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    path = _local_dir() / f"{memory_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_memories(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(int(limit), 1), 100)
    if os.environ.get("MEMORY_STORE", "local") == "firestore":
        docs = _firestore_collection().order_by("updated_at", direction="DESCENDING").limit(limit).stream()
        return [doc.to_dict() for doc in docs]
    directory = _local_dir()
    if not directory.exists():
        return []
    records = [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")]
    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return records[:limit]


def retrieve_memories(query: str, domain: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    terms = {term for term in re.findall(r"[\w-]+", query.casefold()) if len(term) > 2}
    candidates = list_memories(limit=100)
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        if item.get("state") != "active":
            continue
        if domain and item.get("domain") != domain.casefold():
            continue
        haystack = " ".join([
            str(item.get("content", "")),
            str(item.get("domain", "")),
            " ".join(item.get("tags", [])),
        ]).casefold()
        overlap = sum(1 for term in terms if term in haystack)
        if terms and overlap == 0:
            continue
        score = overlap + float(item.get("confidence", 0.0))
        scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].get("updated_at", "")), reverse=True)
    return [item for _, item in scored[: min(max(limit, 1), 20)]]
