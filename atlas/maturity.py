"""Evidence-backed maturity scorecards and monotonic promotion gate."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Iterable


DOMAINS = ("architecture", "autonomy", "initiative", "results", "robustness", "safety", "memory")
EVIDENCE_KINDS = {"local", "ci", "production"}
EVIDENCE_RANK = {"local": 0, "ci": 1, "production": 2}
REMEDIATION_SEVERITIES = {"high", "critical"}


@dataclass(frozen=True)
class DomainScore:
    score: int
    rationale: str
    evidence: tuple[str, ...]
    evidence_kind: str


@dataclass(frozen=True)
class Remediation:
    remediation_id: str
    domain: str
    severity: str
    finding: str
    evidence: tuple[str, ...]
    evidence_kind: str


@dataclass(frozen=True)
class MaturityScorecard:
    assessment_id: str
    measured_at: str
    revision: str
    domains: dict[str, DomainScore]
    remediations: tuple[Remediation, ...] = ()

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
    remediated_findings: tuple[str, ...]
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
    remediation_values = payload.get("remediations", [])
    if not isinstance(remediation_values, list):
        raise ValueError("remediations must be an array")
    remediations: list[Remediation] = []
    remediation_ids: set[str] = set()
    for value in remediation_values:
        if not isinstance(value, dict):
            raise ValueError("each remediation must be an object")
        remediation_id = str(value.get("remediation_id", "")).strip()
        domain = str(value.get("domain", "")).strip().casefold()
        severity = str(value.get("severity", "")).strip().casefold()
        finding = str(value.get("finding", "")).strip()
        evidence = value.get("evidence")
        evidence_kind = str(value.get("evidence_kind", "")).strip().casefold()
        if not remediation_id or remediation_id in remediation_ids:
            raise ValueError("remediation_id must be present and unique")
        if domain not in DOMAINS:
            raise ValueError(f"remediation {remediation_id} has an invalid domain")
        if severity not in REMEDIATION_SEVERITIES:
            raise ValueError(f"remediation {remediation_id} must be high or critical")
        if not finding:
            raise ValueError(f"remediation {remediation_id} requires a finding")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            raise ValueError(f"remediation {remediation_id} requires evidence references")
        if len(set(evidence)) != len(evidence):
            raise ValueError(f"remediation {remediation_id} evidence references must be unique")
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"remediation {remediation_id} has an invalid evidence kind")
        remediation_ids.add(remediation_id)
        remediations.append(
            Remediation(remediation_id, domain, severity, finding, tuple(evidence), evidence_kind)
        )
    return MaturityScorecard(assessment_id, measured_at, revision, parsed, tuple(remediations))


def compare_scorecards(previous: MaturityScorecard, current: MaturityScorecard) -> MaturityGateResult:
    regressions = tuple(name for name in DOMAINS if current.domains[name].score < previous.domains[name].score)
    improved = tuple(name for name in DOMAINS if current.domains[name].score > previous.domains[name].score)
    previous_remediations = {item.remediation_id for item in previous.remediations}
    current_remediations = {item.remediation_id for item in current.remediations}
    remediated = tuple(
        item.remediation_id for item in current.remediations if item.remediation_id not in previous_remediations
    )
    blockers: list[str] = []
    if previous.assessment_id == current.assessment_id:
        blockers.append("assessment_id must change")
    if current.measured_at <= previous.measured_at:
        blockers.append("measured_at must increase")
    if regressions:
        blockers.append("maturity regression detected")
    if not previous_remediations.issubset(current_remediations):
        blockers.append("remediation history must be append-only")
    if not improved and not remediated:
        blockers.append("at least one maturity domain or high-severity finding must improve")
    for name in DOMAINS:
        if EVIDENCE_RANK[current.domains[name].evidence_kind] < EVIDENCE_RANK[previous.domains[name].evidence_kind]:
            blockers.append(f"evidence kind regressed for {name}")
    for name in improved:
        if not set(current.domains[name].evidence) - set(previous.domains[name].evidence):
            blockers.append(f"improved domain {name} requires new evidence")
        if current.domains[name].rationale == previous.domains[name].rationale:
            blockers.append(f"improved domain {name} requires a new rationale")
    for remediation in current.remediations:
        if remediation.remediation_id not in remediated:
            continue
        previous_domain_evidence = set(previous.domains[remediation.domain].evidence)
        if not set(remediation.evidence) - previous_domain_evidence:
            blockers.append(
                f"remediation {remediation.remediation_id} requires new evidence for {remediation.domain}"
            )
        if EVIDENCE_RANK[remediation.evidence_kind] < EVIDENCE_RANK[current.domains[remediation.domain].evidence_kind]:
            blockers.append(
                f"remediation {remediation.remediation_id} evidence is weaker than its domain"
            )
    promoted = not blockers
    return MaturityGateResult(
        status="promoted" if promoted else "blocked",
        promoted=promoted,
        improved_domains=improved,
        remediated_findings=remediated,
        regressions=regressions,
        blockers=tuple(blockers),
        previous_overall=previous.overall_score,
        current_overall=current.overall_score,
    )


def validate_evidence(scorecard: MaturityScorecard, repository_root: str | Path) -> None:
    root = Path(repository_root).resolve()
    for name, domain in scorecard.domains.items():
        for reference in domain.evidence:
            if domain.evidence_kind == "production":
                parsed = urlparse(reference)
                if parsed.scheme != "https" or not parsed.netloc:
                    raise ValueError(f"production evidence for {name} must be an HTTPS URL")
                continue
            candidate = Path(reference)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"evidence for {name} must be repository-relative")
            resolved = (root / candidate).resolve()
            if root != resolved and root not in resolved.parents:
                raise ValueError(f"evidence for {name} escapes the repository")
            if not resolved.exists():
                raise ValueError(f"evidence for {name} does not exist: {reference}")
    for remediation in scorecard.remediations:
        for reference in remediation.evidence:
            if remediation.evidence_kind == "production":
                parsed = urlparse(reference)
                if parsed.scheme != "https" or not parsed.netloc:
                    raise ValueError(
                        f"production evidence for remediation {remediation.remediation_id} must be an HTTPS URL"
                    )
                continue
            candidate = Path(reference)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"evidence for remediation {remediation.remediation_id} must be repository-relative")
            resolved = (root / candidate).resolve()
            if root != resolved and root not in resolved.parents:
                raise ValueError(f"evidence for remediation {remediation.remediation_id} escapes the repository")
            if not resolved.exists():
                raise ValueError(
                    f"evidence for remediation {remediation.remediation_id} does not exist: {reference}"
                )


def _repository_root(scorecard_path: Path) -> Path:
    for candidate in scorecard_path.resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "atlas").is_dir():
            return candidate
    raise ValueError("could not locate repository root for maturity evidence")


def verify_history(paths: Iterable[str | Path]) -> list[MaturityGateResult]:
    ordered = sorted((Path(path) for path in paths), key=lambda item: item.name)
    if len(ordered) < 2:
        raise ValueError("at least two maturity scorecards are required")
    scorecards = [load_scorecard(path) for path in ordered]
    repository_root = _repository_root(ordered[0])
    for scorecard in scorecards:
        validate_evidence(scorecard, repository_root)
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
