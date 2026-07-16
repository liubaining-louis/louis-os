from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .providers import ModelResponse, complete_with


DEFAULT_AXES = {
    "offre_produit": ["produit", "charbon", "ogatan", "10 kg"],
    "marches_cibles": ["marché", "horeca", "distribution", "grossiste"],
    "attentes_clients": ["prix", "moq", "palette", "conteneur", "dropshipping"],
    "preuves_techniques": ["fiche technique", "origine", "certification", "coa", "msds"],
    "risques": ["risque", "non confirmé", "manquant", "incertitude"],
    "actions": ["action", "priorité", "prochaine étape", "suivi"],
}


@dataclass(frozen=True)
class ComparisonMission:
    mission_id: str
    objective: str
    context: dict[str, Any]
    providers: list[str] = field(default_factory=lambda: ["groq", "vertex"])
    evaluation_axes: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_AXES))


@dataclass(frozen=True)
class ModelComparisonRun:
    requested_provider: str
    provider: str
    model: str
    status: str
    output: str
    error: str | None
    axis_coverage: dict[str, bool]
    coverage_score: float


@dataclass(frozen=True)
class ModelComparisonResult:
    mission_id: str
    objective: str
    status: str
    prompt_digest: str
    runs: list[ModelComparisonRun]
    best_coverage_provider: str | None
    discrepancies: list[str]
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProviderInvoker = Callable[[str, str], ModelResponse]


def _prompt(mission: ComparisonMission) -> str:
    return (
        "Analyse the supplied email evidence in read-only mode. Do not send, modify or invent emails. "
        "Separate observed facts from inferences. Return: executive summary, major themes, qualified leads, "
        "customer requirements, technical/documentary gaps, risks, and prioritized next actions.\n"
        f"Objective: {mission.objective}\n"
        f"Evidence: {json.dumps(mission.context, ensure_ascii=False, sort_keys=True)}"
    )


def _coverage(text: str, axes: dict[str, list[str]]) -> tuple[dict[str, bool], float]:
    normalized = text.casefold()
    coverage = {
        axis: any(term.casefold() in normalized for term in terms)
        for axis, terms in axes.items()
    }
    score = sum(coverage.values()) / len(coverage) if coverage else 0.0
    return coverage, round(score, 6)


def _safe_error(exc: Exception) -> str:
    value = str(exc)
    value = re.sub(
        r"(?i)\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*[^\s,;]+",
        "[REDACTED]",
        value,
    )
    value = re.sub(r"\b(?:sk|gsk)[-_][A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
    return value[:1000] + (" [truncated]" if len(value) > 1000 else "")


def compare_models(
    mission: ComparisonMission,
    *,
    invoke: ProviderInvoker = complete_with,
) -> ModelComparisonResult:
    if not mission.mission_id.strip() or not mission.objective.strip():
        raise ValueError("mission_id and objective are required")
    providers = list(dict.fromkeys(item.strip().casefold() for item in mission.providers if item.strip()))
    if len(providers) < 2:
        raise ValueError("at least two distinct providers are required")

    prompt = _prompt(mission)
    import hashlib

    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    runs: list[ModelComparisonRun] = []
    blockers: list[str] = []
    for requested in providers:
        try:
            response = invoke(requested, prompt)
            coverage, score = _coverage(response.text, mission.evaluation_axes)
            runs.append(ModelComparisonRun(
                requested_provider=requested,
                provider=response.provider,
                model=response.model,
                status="completed",
                output=response.text,
                error=None,
                axis_coverage=coverage,
                coverage_score=score,
            ))
        except (RuntimeError, ValueError) as exc:
            blockers.append(f"{requested}: unavailable or failed")
            runs.append(ModelComparisonRun(
                requested_provider=requested,
                provider=requested,
                model="unknown",
                status="blocked",
                output="",
                error=_safe_error(exc),
                axis_coverage={axis: False for axis in mission.evaluation_axes},
                coverage_score=0.0,
            ))

    completed = [run for run in runs if run.status == "completed"]
    status = "completed" if len(completed) == len(providers) else "blocked"
    best = None
    if completed:
        highest = max(run.coverage_score for run in completed)
        leaders = [run.requested_provider for run in completed if run.coverage_score == highest]
        best = leaders[0] if len(leaders) == 1 else None
    discrepancies = []
    for axis in mission.evaluation_axes:
        values = {run.requested_provider: run.axis_coverage[axis] for run in completed}
        if len(set(values.values())) > 1:
            discrepancies.append(f"axis coverage differs for {axis}")
    return ModelComparisonResult(
        mission_id=mission.mission_id,
        objective=mission.objective,
        status=status,
        prompt_digest=digest,
        runs=runs,
        best_coverage_provider=best,
        discrepancies=discrepancies,
        blockers=blockers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m atlas.model_comparison")
    parser.add_argument("--input", required=True, help="JSON mission file")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    mission = ComparisonMission(
        mission_id=str(payload["mission_id"]),
        objective=str(payload["objective"]),
        context=dict(payload.get("context", {})),
        providers=list(payload.get("providers", ["groq", "vertex"])),
        evaluation_axes=dict(payload.get("evaluation_axes", DEFAULT_AXES)),
    )
    print(json.dumps(compare_models(mission).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
