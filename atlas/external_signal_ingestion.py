from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Literal

SignalSource = Literal["web", "gmail"]
SignalDecision = Literal["accepted", "rejected", "duplicate"]
SignalKind = Literal["evidence", "market_observation"]


@dataclass(frozen=True)
class ExternalSignal:
    source: SignalSource
    external_id: str
    uri: str
    title: str
    content: str
    occurred_at: str
    consent_scope: str
    read_only: bool = True
    sender: str = ""
    recipient: str = ""

    def validate(self) -> None:
        if self.source not in {"web", "gmail"}:
            raise ValueError("unsupported signal source")
        if not all(value.strip() for value in (self.external_id, self.title, self.content, self.occurred_at)):
            raise ValueError("external signal identity, title, content and time are required")
        if not self.consent_scope.strip():
            raise ValueError("explicit consent scope is required")
        if not self.read_only:
            raise ValueError("ingestion adapters must be read-only")


@dataclass(frozen=True)
class NormalizedSignal:
    signal_id: str
    source: SignalSource
    external_id: str
    decision: SignalDecision
    reason: str
    kind: SignalKind
    title: str
    redacted_content: str
    provenance_uri: str
    occurred_at: str
    content_hash: str


class ExternalSignalIngestionGateway:
    """Normalize read-only Web/Gmail inputs into auditable internal signals."""

    EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")

    def __init__(self, *, maximum_content_chars: int = 6000) -> None:
        if maximum_content_chars <= 0:
            raise ValueError("maximum_content_chars must be positive")
        self.maximum_content_chars = maximum_content_chars

    @classmethod
    def redact_sensitive_data(cls, text: str) -> str:
        text = cls.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        return cls.PHONE_PATTERN.sub("[REDACTED_PHONE]", text)

    @staticmethod
    def _hash(signal: ExternalSignal) -> str:
        canonical = "|".join((signal.source, signal.external_id, signal.uri, signal.title, signal.content))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def ingest(self, signals: Iterable[ExternalSignal]) -> tuple[NormalizedSignal, ...]:
        results: list[NormalizedSignal] = []
        seen_external_ids: set[tuple[str, str]] = set()
        seen_hashes: set[str] = set()

        for signal in signals:
            signal.validate()
            identity = (signal.source, signal.external_id)
            content_hash = self._hash(signal)
            signal_id = f"sig-{content_hash[:16]}"
            kind: SignalKind = "market_observation" if signal.source == "gmail" else "evidence"

            if identity in seen_external_ids or content_hash in seen_hashes:
                decision: SignalDecision = "duplicate"
                reason = "signal already ingested in this batch"
            elif len(signal.content) > self.maximum_content_chars:
                decision = "rejected"
                reason = "signal content exceeds bounded ingestion size"
            elif signal.source == "web" and not signal.uri.strip():
                decision = "rejected"
                reason = "web evidence requires a provenance URI"
            else:
                decision = "accepted"
                reason = "signal satisfies consent, provenance and read-only gates"

            seen_external_ids.add(identity)
            seen_hashes.add(content_hash)
            results.append(
                NormalizedSignal(
                    signal_id=signal_id,
                    source=signal.source,
                    external_id=signal.external_id,
                    decision=decision,
                    reason=reason,
                    kind=kind,
                    title=signal.title.strip(),
                    redacted_content=self.redact_sensitive_data(signal.content.strip()),
                    provenance_uri=signal.uri.strip(),
                    occurred_at=signal.occurred_at,
                    content_hash=content_hash,
                )
            )

        return tuple(results)

    def write(self, signals: Iterable[NormalizedSignal], output_path: str | Path) -> str:
        items = tuple(signals)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "accepted_count": sum(item.decision == "accepted" for item in items),
            "rejected_count": sum(item.decision == "rejected" for item in items),
            "duplicate_count": sum(item.decision == "duplicate" for item in items),
            "signals": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
