"""Evidence-backed maturity scorecards and monotonic promotion gate."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DOMAINS = ("architecture", "autonomy", "initiative", "results", "robustness", "safety", "memory")
EVIDENCE_KINDS = {"local", "ci", "production"}


@dataclass(frozen=True)
class DomainScore:
    score: int
    rationale: str
    evidence: tuple[str, ...]
    evidence_kind: str


@dataclass(frozen=True)
class MaturityScorecard:
    assessment_id: str
    measured_at: str
    revision: str
    domains: dict[str, DomainScore]

    @property
    def overall_score(self) -> float:
        return round(sum(item.score for item in self.domains.values()) / len(DOMAINS), 2)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["overall_score"] = self.overall_score
        return payload


@dataclass(frozen=True)
class MaturityGateResult:
    status: str
    promoted: bool
    improved_domains: tuple[str, ...]
    regressions: tuple[str, ...]
    blockers: tuple[str, ...]
    previous_overall: float
    current_overall: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_scorecard(path: str | Path) -> MaturityScorecard:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scorecard must be an object")
    domains = payload.get("domains")
    if not isinstance(domains, dict) or set(domains) != set(DOMAINS):
        raise ValueError("scorecard must contain every maturity domain exactly once")
    parsed: dict[str, DomainScore] = {}
    for name in DOMAINS:
        value = domains[name]
        if not isinstance(value, dict):
            raise ValueError(f"domain {name} must be an object")
        score = value.get("score")
        rationale = str(value.get("rationale", "")).strip()
        evidence = value.get("evidence")
        evidence_kind = str(value.get("evidence_kind", "")).strip().casefold()
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 10:
            raise ValueError(f"domain {name} score must be an integer from 0 to 10")
        if not rationale:
            raise ValueError(f"domain {name} requires a rationale")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            raise ValueError(f"domain {name} requires evidence references")
        if len(set(evidence)) != len(evidence):
            raise ValueError(f"domain {name} evidence references must be unique")
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"domain {name} has an invalid evidence kind")
        parsed[name] = DomainScore(score, rationale, tuple(evidence), evidence_kind)

    assessment_id = str(payload.get("assessment_id", "")).strip()
    measured_at = str(payload.get("measured_at", "")).strip()
    revision = str(payload.get("revision", "")).strip()
    if not assessment_id or not measured_at or not revision:
        raise ValueError("assessment_id, measured_at and revision are required")
    return MaturityScorecard(assessment_id, measured_at, revision, parsed)


def compare_scorecards(previous: MaturityScorecard, current: MaturityScorecard) -> MaturityGateResult:
    regressions = tuple(name for name in DOMAINS if current.domains[name].score < previous.domains[name].score)
    improved = tuple(name for name in DOMAINS if current.domains[name].score > previous.domains[name].score)
    blockers: list[str] = []
    if previous.assessment_id == current.assessment_id:
        blockers.append("assessment_id must change")
    if current.measured_at <= previous.measured_at:
        blockers.append("measured_at must increase")
    if regressions:
        blockers.append("maturity regression detected")
    if not improved:
        blockers.append("at least one maturity domain must improve")
    for name in improved:
        if not set(current.domains[name].evidence) - set(previous.domains[name].evidence):
            blockers.append(f"improved domain {name} requires new evidence")
    promoted = not blockers
    return MaturityGateResult(
        status="promoted" if promoted else "blocked",
        promoted=promoted,
        improved_domains=improved,
        regressions=regressions,
        blockers=tuple(blockers),
        previous_overall=previous.overall_score,
        current_overall=current.overall_score,
    )


def verify_history(paths: Iterable[str | Path]) -> list[MaturityGateResult]:
    ordered = sorted((Path(path) for path in paths), key=lambda item: item.name)
    if len(ordered) < 2:
        raise ValueError("at least two maturity scorecards are required")
    scorecards = [load_scorecard(path) for path in ordered]
    results = [compare_scorecards(previous, current) for previous, current in zip(scorecards, scorecards[1:])]
    blocked = [result for result in results if not result.promoted]
    if blocked:
        raise ValueError("maturity history is blocked: " + "; ".join(blocked[0].blockers))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m atlas.maturity")
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("previous")
    compare.add_argument("current")
    history = subparsers.add_parser("verify-history")
    history.add_argument("directory")
    args = parser.parse_args()
    if args.command == "compare":
        result = compare_scorecards(load_scorecard(args.previous), load_scorecard(args.current))
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.promoted else 1)
    results = verify_history(Path(args.directory).glob("*.json"))
    print(json.dumps({"status": "promoted", "comparisons": [item.to_dict() for item in results]}, indent=2))


if __name__ == "__main__":
    main()
