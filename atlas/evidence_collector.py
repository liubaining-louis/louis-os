from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal, Protocol

SourceKind = Literal["official", "marketplace", "company", "news", "community", "unknown"]
CollectionDecision = Literal["accepted", "rejected", "quota_exceeded", "adapter_error"]


@dataclass(frozen=True)
class CollectionRequest:
    task_id: str
    query: str
    evidence_type: str
    maximum_sources: int

    def validate(self) -> None:
        if not self.task_id.strip() or not self.query.strip() or not self.evidence_type.strip():
            raise ValueError("task_id, query and evidence_type are required")
        if self.maximum_sources <= 0:
            raise ValueError("maximum_sources must be positive")


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    uri: str
    title: str
    claim: str
    source_kind: SourceKind
    reliability: float
    freshness: float
    retrieved_at: str

    def validate(self) -> None:
        if not all(value.strip() for value in (self.source_id, self.uri, self.title, self.claim, self.retrieved_at)):
            raise ValueError("source provenance fields are required")
        if self.source_kind not in {"official", "marketplace", "company", "news", "community", "unknown"}:
            raise ValueError("unsupported source_kind")
        for name in ("reliability", "freshness"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class CollectedEvidence:
    task_id: str
    source_id: str
    decision: CollectionDecision
    reason: str
    evidence_type: str
    uri: str
    claim: str
    reliability: float
    freshness: float


class EvidenceSourceAdapter(Protocol):
    def collect(self, request: CollectionRequest) -> Iterable[SourceRecord]: ...


class BoundedEvidenceCollector:
    """Execute read-only evidence collection with strict quotas and provenance gates."""

    def __init__(
        self,
        *,
        maximum_total_sources: int = 10,
        minimum_reliability: float = 0.55,
        minimum_freshness: float = 0.40,
        blocked_source_kinds: tuple[SourceKind, ...] = ("unknown",),
    ) -> None:
        if maximum_total_sources <= 0:
            raise ValueError("maximum_total_sources must be positive")
        for value, name in ((minimum_reliability, "minimum_reliability"), (minimum_freshness, "minimum_freshness")):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.maximum_total_sources = maximum_total_sources
        self.minimum_reliability = minimum_reliability
        self.minimum_freshness = minimum_freshness
        self.blocked_source_kinds = frozenset(blocked_source_kinds)

    def execute(
        self,
        requests: Iterable[CollectionRequest],
        adapters: dict[str, EvidenceSourceAdapter],
    ) -> list[CollectedEvidence]:
        results: list[CollectedEvidence] = []
        total_seen = 0
        seen_uris: set[str] = set()

        for request in requests:
            request.validate()
            adapter = adapters.get(request.evidence_type)
            if adapter is None:
                results.append(CollectedEvidence(
                    request.task_id, "", "adapter_error", "no adapter registered",
                    request.evidence_type, "", "", 0.0, 0.0,
                ))
                continue
            try:
                records = list(adapter.collect(request))
            except Exception as exc:  # adapters are external boundaries
                results.append(CollectedEvidence(
                    request.task_id, "", "adapter_error", type(exc).__name__,
                    request.evidence_type, "", "", 0.0, 0.0,
                ))
                continue

            for record in records[: request.maximum_sources]:
                record.validate()
                if total_seen >= self.maximum_total_sources:
                    results.append(CollectedEvidence(
                        request.task_id, record.source_id, "quota_exceeded", "global source quota reached",
                        request.evidence_type, record.uri, record.claim, record.reliability, record.freshness,
                    ))
                    continue
                total_seen += 1
                reason = "source satisfies provenance and quality gates"
                decision: CollectionDecision = "accepted"
                if record.uri in seen_uris:
                    decision, reason = "rejected", "duplicate source URI"
                elif record.source_kind in self.blocked_source_kinds:
                    decision, reason = "rejected", "source kind is blocked"
                elif record.reliability < self.minimum_reliability:
                    decision, reason = "rejected", "source reliability below threshold"
                elif record.freshness < self.minimum_freshness:
                    decision, reason = "rejected", "source freshness below threshold"
                seen_uris.add(record.uri)
                results.append(CollectedEvidence(
                    request.task_id, record.source_id, decision, reason,
                    request.evidence_type, record.uri, record.claim,
                    record.reliability, record.freshness,
                ))
        return results

    def write(self, evidence: Iterable[CollectedEvidence], output_path: str | Path) -> str:
        items = list(evidence)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "result_count": len(items),
            "accepted_count": sum(item.decision == "accepted" for item in items),
            "results": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
