from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from atlas.opportunity_discovery import OpportunitySignal


@dataclass(frozen=True)
class NoveltyDecision:
    fingerprint: str
    is_novel: bool
    source_id: str
    reason: str


class OpportunityNoveltyLedger:
    """Persist deterministic fingerprints so repeated signals are not reprocessed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen = self._load()

    @staticmethod
    def fingerprint(signal: OpportunitySignal) -> str:
        canonical = "\n".join(
            part.strip().lower()
            for part in (
                signal.source_url,
                signal.title,
                signal.problem,
                signal.target_customer,
                signal.proposed_offer,
            )
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def filter_novel(self, signals: Iterable[OpportunitySignal]) -> tuple[list[OpportunitySignal], list[NoveltyDecision]]:
        novel: list[OpportunitySignal] = []
        decisions: list[NoveltyDecision] = []
        pending: set[str] = set()

        for signal in signals:
            fingerprint = self.fingerprint(signal)
            duplicate = fingerprint in self._seen or fingerprint in pending
            decisions.append(
                NoveltyDecision(
                    fingerprint=fingerprint,
                    is_novel=not duplicate,
                    source_id=signal.source_id,
                    reason="new fingerprint" if not duplicate else "fingerprint already processed",
                )
            )
            if not duplicate:
                novel.append(signal)
                pending.add(fingerprint)

        self._seen.update(pending)
        self._save()
        return novel, decisions

    def report(self, decisions: Iterable[NoveltyDecision]) -> list[dict[str, object]]:
        return [asdict(decision) for decision in decisions]

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("novelty ledger schema_version must be 1.0")
        fingerprints = payload.get("fingerprints")
        if not isinstance(fingerprints, list) or not all(isinstance(item, str) for item in fingerprints):
            raise ValueError("novelty ledger fingerprints must be a string list")
        return set(fingerprints)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "fingerprints": sorted(self._seen),
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
