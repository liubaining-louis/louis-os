from __future__ import annotations

import os
from dataclasses import dataclass

from .providers import complete, complete_with


@dataclass(frozen=True)
class RoutingDecision:
    score: float
    tier: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RoutedModelResponse:
    provider: str
    model: str
    text: str
    tier: str
    difficulty_score: float
    routing_reasons: tuple[str, ...]
    escalated: bool
    escalation_fallback: bool = False


def _threshold() -> float:
    try:
        value = float(os.environ.get("LLM_REASONING_ESCALATION_THRESHOLD", "0.55"))
    except (TypeError, ValueError):
        value = 0.55
    return min(max(value, 0.20), 0.95)


def assess_difficulty(prompt: str) -> RoutingDecision:
    text = prompt.casefold()
    score = 0.0
    reasons: list[str] = []

    if len(prompt) >= 6000:
        score += 0.20
        reasons.append("large_context")
    elif len(prompt) >= 2500:
        score += 0.10
        reasons.append("medium_context")

    reasoning_terms = (
        "root cause", "diagnos", "trade-off", "compare", "critique", "verify",
        "architecture", "strategy", "reasoning", "regression", "contradiction",
        "planification", "analyse approfondie", "cause racine",
    )
    if any(term in text for term in reasoning_terms):
        score += 0.22
        reasons.append("deep_reasoning")

    execution_terms = (
        "execute_now", "prepare_then_gate", "submission", "soumission",
        "payment", "paiement", "revenue", "revenu", "contract", "contrat",
        "external action", "action externe", "approval", "approbation",
    )
    if any(term in text for term in execution_terms):
        score += 0.28
        reasons.append("economic_or_external_boundary")

    uncertainty_terms = (
        "uncertain", "incertain", "ambiguous", "ambigu", "conflict", "conflit",
        "insufficient evidence", "preuve insuffisante", "low confidence",
    )
    if any(term in text for term in uncertainty_terms):
        score += 0.18
        reasons.append("uncertainty")

    high_impact_terms = (
        "irreversible", "legal", "juridique", "security", "sécurité", "risk",
        "risque", "production", "deploy", "déploi", "money", "argent",
    )
    if any(term in text for term in high_impact_terms):
        score += 0.18
        reasons.append("high_impact")

    score = min(score, 1.0)
    tier = "reasoning" if score >= _threshold() else "fast"
    return RoutingDecision(score=score, tier=tier, reasons=tuple(reasons))


def routed_complete(prompt: str) -> RoutedModelResponse:
    decision = assess_difficulty(prompt)
    if decision.tier == "fast":
        response = complete(prompt)
        return RoutedModelResponse(
            provider=response.provider,
            model=response.model,
            text=response.text,
            tier="fast",
            difficulty_score=decision.score,
            routing_reasons=decision.reasons,
            escalated=False,
        )

    reasoning_provider = os.environ.get("LLM_REASONING_PROVIDER", "vertex").strip().casefold() or "vertex"
    try:
        response = complete_with(reasoning_provider, prompt)
        return RoutedModelResponse(
            provider=response.provider,
            model=response.model,
            text=response.text,
            tier="reasoning",
            difficulty_score=decision.score,
            routing_reasons=decision.reasons,
            escalated=True,
        )
    except RuntimeError:
        response = complete(prompt)
        return RoutedModelResponse(
            provider=response.provider,
            model=response.model,
            text=response.text,
            tier="reasoning",
            difficulty_score=decision.score,
            routing_reasons=decision.reasons,
            escalated=True,
            escalation_fallback=True,
        )
