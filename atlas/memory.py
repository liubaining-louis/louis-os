from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .runner import ROOT

MEMORY_TYPES = {"fact", "preference", "decision", "procedure", "outcome"}
LIFECYCLE_STATES = {"active", "superseded", "archived", "deleted"}
_SECRET_KEY_RE = re.compile(
    r"(^|_)(api[_-]?key|token|secret|password|passwd|credential|private[_-]?key)($|_)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
)


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    memory_type: str
    content: dict[str, Any]
    provenance: dict[str, Any]
    confidence: float
    tags: list[str] = field(default_factory=list)
    lifecycle_state: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_secret_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def _sanitize(value: Any, path: str = "root") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                raise ValueError(f"secret-like field is not allowed in memory: {path}.{key_text}")
            sanitized[key_text] = _sanitize(item, f"{path}.{key_text}")
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, f"{path}[]") for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item, f"{path}[]") for item in value]
    if isinstance(value, str):
        if _contains_secret_value(value):
            raise ValueError(f"secret-like value is not allowed in memory: {path}")
        return value.strip()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError(f"unsupported memory value at {path}: {type(value).__name__}")


def build_memory(
    memory_type: str,
    content: dict[str, Any],
    provenance: dict[str, Any],
    confidence: float,
    tags: Iterable[str] = (),
    lifecycle_state: str = "active",
    memory_id: str | None = None,
) -> MemoryRecord:
    normalized_type = memory_type.strip().lower()
    normalized_state = lifecycle_state.strip().lower()
    if normalized_type not in MEMORY_TYPES:
        raise ValueError(f"unsupported memory type: {memory_type}")
    if normalized_state not in LIFECYCLE_STATES:
        raise ValueError(f"unsupported lifecycle state: {lifecycle_state}")
    if not isinstance(content, dict) or not content:
        raise ValueError("memory content must be a non-empty object")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("memory provenance must be a non-empty object")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    normalized_tags = sorted({tag.strip().lower() for tag in tags if tag.strip()})
    now = datetime.now(timezone.utc).isoformat()
    return MemoryRecord(
        memory_id=memory_id or str(uuid.uuid4()),
        memory_type=normalized_type,
        content=_sanitize(content, "content"),
        provenance=_sanitize(provenance, "provenance"),
        confidence=float(confidence),
        tags=normalized_tags,
        lifecycle_state=normalized_state,
        created_at=now,
        updated_at=now,
    )


class MemoryStore:
    def save(self, record: MemoryRecord) -> None:
        raise NotImplementedError

    def get(self, memory_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def search(self, query: str, tags: Iterable[str] = (), limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError


class LocalMemoryStore(MemoryStore):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (ROOT / "results" / "memories")

    def save(self, record: MemoryRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{record.memory_id}.json"
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, memory_id: str) -> dict[str, Any] | None:
        path = self.root / f"{memory_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def search(self, query: str, tags: Iterable[str] = (), limit: int = 20) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        terms = {term for term in query.casefold().split() if term}
        required_tags = {tag.strip().lower() for tag in tags if tag.strip()}
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for path in self.root.glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("lifecycle_state") != "active":
                continue
            item_tags = set(item.get("tags", []))
            if required_tags and not required_tags.issubset(item_tags):
                continue
            haystack = json.dumps(item.get("content", {}), ensure_ascii=False).casefold()
            matches = sum(term in haystack for term in terms)
            if terms and matches == 0:
                continue
            score = matches + float(item.get("confidence", 0.0))
            scored.append((score, item.get("updated_at", ""), item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [item for _, _, item in scored[: max(1, min(limit, 100))]]


class FirestoreMemoryStore(MemoryStore):
    def __init__(self) -> None:
        from google.cloud import firestore

        self.client = firestore.Client()
        self.collection = self.client.collection(
            os.environ.get("FIRESTORE_MEMORIES_COLLECTION", "memories")
        )

    def save(self, record: MemoryRecord) -> None:
        self.collection.document(record.memory_id).set(record.to_dict())

    def get(self, memory_id: str) -> dict[str, Any] | None:
        snapshot = self.collection.document(memory_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def search(self, query: str, tags: Iterable[str] = (), limit: int = 20) -> list[dict[str, Any]]:
        normalized_tags = [tag.strip().lower() for tag in tags if tag.strip()]
        firestore_query = self.collection.where("lifecycle_state", "==", "active")
        if normalized_tags:
            firestore_query = firestore_query.where("tags", "array_contains", normalized_tags[0])
        candidates = [doc.to_dict() for doc in firestore_query.limit(min(max(limit * 5, 20), 100)).stream()]
        terms = {term for term in query.casefold().split() if term}
        ranked = []
        for item in candidates:
            if not set(normalized_tags).issubset(set(item.get("tags", []))):
                continue
            haystack = json.dumps(item.get("content", {}), ensure_ascii=False).casefold()
            matches = sum(term in haystack for term in terms)
            if terms and matches == 0:
                continue
            ranked.append((matches + float(item.get("confidence", 0.0)), item))
        ranked.sort(key=lambda row: row[0], reverse=True)
        return [item for _, item in ranked[:limit]]


def get_memory_store() -> MemoryStore:
    backend = os.environ.get("MEMORY_STORE", os.environ.get("MISSION_STORE", "local")).strip().lower()
    if backend == "firestore":
        return FirestoreMemoryStore()
    return LocalMemoryStore()
