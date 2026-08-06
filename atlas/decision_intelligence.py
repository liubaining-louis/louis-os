"""Deterministic decision-intelligence loop for Louis OS.

The loop turns reviewed decisions and observed outcomes into reusable lessons. It is
model-agnostic: LLMs may propose hypotheses, but promotion and blocking are controlled
by explicit evidence, counterexamples and regression rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    domain: str
    objective: str
    facts: Mapping[str, Any]
    proposed_action: str
    assumptions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.case_id.strip() or not self.domain.strip() or not self.objective.strip():
            raise ValueError("case_id, domain and objective are required")
        if not self.proposed_action.strip():
            raise ValueError("proposed_action is required")


@dataclass(frozen=True)
class Critique:
    contradictions: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    failure_modes: tuple[str, ...]
    irreversible_risks: tuple[str, ...]
    alternative_actions: tuple[str, ...]

    @property
    def severity(self) -> int:
        return (
            len(self.contradictions) * 2
            + len(self.missing_evidence)
            + len(self.failure_modes)
            + len(self.irreversible_risks) * 3
        )


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    pattern: str
    decision: str
    rationale: str
    evidence: tuple[str, ...]
    confidence: float
    occurrences: int = 1
    active: bool = True


@dataclass(frozen=True)
class DecisionResult:
    case_id: str
    decision: str
    confidence: float
    blockers: tuple[str, ...]
    critique: Critique
    applied_lessons: tuple[str, ...]
    next_action: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["critique"] = asdict(self.critique)
        return payload


class LessonRegistry:
    def __init__(self, lessons: Iterable[Lesson] = ()) -> None:
        self._lessons = {lesson.lesson_id: lesson for lesson in lessons if lesson.active}

    @staticmethod
    def lesson_id(pattern: str, decision: str) -> str:
        raw = f"{pattern.strip().casefold()}|{decision.strip().casefold()}"
        return "lesson-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def match(self, text: str) -> list[Lesson]:
        haystack = text.casefold()
        return [lesson for lesson in self._lessons.values() if lesson.pattern.casefold() in haystack]

    def promote(
        self,
        *,
        pattern: str,
        decision: str,
        rationale: str,
        evidence: Sequence[str],
        confidence: float,
    ) -> Lesson:
        if not evidence:
            raise ValueError("a lesson requires evidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        lesson_id = self.lesson_id(pattern, decision)
        previous = self._lessons.get(lesson_id)
        lesson = Lesson(
            lesson_id=lesson_id,
            pattern=pattern,
            decision=decision,
            rationale=rationale,
            evidence=tuple(dict.fromkeys(evidence)),
            confidence=max(confidence, previous.confidence if previous else 0.0),
            occurrences=(previous.occurrences + 1) if previous else 1,
        )
        self._lessons[lesson_id] = lesson
        return lesson

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lessons": [asdict(item) for item in sorted(self._lessons.values(), key=lambda x: x.lesson_id)],
        }


class DecisionIntelligence:
    """Planner/critic/revision gate backed by reusable evidence-based lessons."""

    TERMINAL_SIGNALS = {
        "captcha bypass": "platform_policy_blocked",
        "anti-bot bypass": "platform_policy_blocked",
        "proxy required": "platform_policy_blocked",
        "in-person": "physically_inaccessible",
        "already completed": "already_completed",
        "payment request": "not_an_open_opportunity",
        "seller offer": "commercial_offer_not_job",
        "buy my": "commercial_offer_not_job",
    }

    def __init__(self, lessons: LessonRegistry | None = None) -> None:
        self.lessons = lessons or LessonRegistry()

    def evaluate(self, case: DecisionCase) -> DecisionResult:
        case.validate()
        text = self._case_text(case)
        critique = self._critic(case, text)
        applied = self.lessons.match(text)

        blockers = list(critique.contradictions)
        blockers.extend(critique.irreversible_risks)
        for lesson in applied:
            if lesson.decision.startswith("block:") and lesson.confidence >= 0.70:
                blockers.append(lesson.decision.removeprefix("block:"))

        blockers = list(dict.fromkeys(blockers))
        missing = len(critique.missing_evidence)
        if blockers:
            decision = "reject"
            confidence = min(0.99, 0.70 + 0.04 * len(blockers))
            next_action = "preserve_evidence_learn_and_search_alternative"
        elif missing:
            decision = "verify_then_reconsider"
            confidence = max(0.20, 0.65 - 0.08 * missing)
            next_action = "collect_missing_evidence_and_rerun"
        elif critique.failure_modes:
            decision = "prepare_with_mitigation"
            confidence = max(0.40, 0.78 - 0.05 * len(critique.failure_modes))
            next_action = "add_mitigations_acceptance_tests_and_dry_run"
        else:
            decision = "proceed_reversibly"
            confidence = 0.88
            next_action = "execute_smallest_reversible_step_and_capture_receipt"

        return DecisionResult(
            case_id=case.case_id,
            decision=decision,
            confidence=round(confidence, 2),
            blockers=tuple(blockers),
            critique=critique,
            applied_lessons=tuple(lesson.lesson_id for lesson in applied),
            next_action=next_action,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def learn_from_outcome(
        self,
        case: DecisionCase,
        result: DecisionResult,
        *,
        outcome: str,
        evidence: Sequence[str],
    ) -> Lesson | None:
        if not evidence:
            raise ValueError("outcome learning requires evidence")
        normalized = outcome.strip().casefold()
        if normalized not in {"success", "failure", "false_positive", "false_negative"}:
            raise ValueError("unsupported outcome")

        pattern = self._dominant_pattern(case)
        if normalized in {"failure", "false_positive"}:
            decision = f"block:{result.blockers[0] if result.blockers else 'repeat_failure_pattern'}"
            confidence = 0.85
        elif normalized == "false_negative":
            decision = "review:overly_strict_gate"
            confidence = 0.70
        else:
            decision = "prefer:repeat_verified_reversible_pattern"
            confidence = 0.75

        return self.lessons.promote(
            pattern=pattern,
            decision=decision,
            rationale=f"Observed outcome={normalized} for case={case.case_id}",
            evidence=evidence,
            confidence=confidence,
        )

    def _critic(self, case: DecisionCase, text: str) -> Critique:
        contradictions: list[str] = []
        irreversible: list[str] = []
        missing: list[str] = []
        failure_modes: list[str] = []
        alternatives: list[str] = []

        for signal, blocker in self.TERMINAL_SIGNALS.items():
            if signal in text:
                contradictions.append(blocker)

        facts = case.facts
        if facts.get("listing_open") is not True:
            missing.append("fresh_open_status")
        if facts.get("buyer_seeking_worker") is not True:
            missing.append("buyer_intent")
        if facts.get("reward_verified") is not True:
            missing.append("verified_payment")
        if not facts.get("acceptance_criteria"):
            missing.append("acceptance_criteria")
        if facts.get("remote_eligible") is False:
            contradictions.append("geographically_ineligible")
        if facts.get("platform_compliant") is False:
            irreversible.append("platform_policy_blocked")
        if facts.get("estimated_hours", 0) and facts.get("reward_amount", 0):
            hourly = float(facts["reward_amount"]) / max(float(facts["estimated_hours"]), 0.01)
            if hourly < float(facts.get("minimum_hourly", 8.0)):
                contradictions.append("economically_unviable")
        if facts.get("external_action") and not facts.get("receipt_capture_planned"):
            failure_modes.append("external_action_without_receipt")
        if facts.get("irreversible_commitment"):
            irreversible.append("irreversible_commitment_requires_human_gate")

        if missing:
            alternatives.append("verify_source_before_scoring")
        if contradictions:
            alternatives.append("search_adjacent_lower_friction_opportunity")
        if failure_modes:
            alternatives.append("dry_run_and_add_receipt_capture")

        return Critique(
            contradictions=tuple(dict.fromkeys(contradictions)),
            missing_evidence=tuple(dict.fromkeys(missing)),
            failure_modes=tuple(dict.fromkeys(failure_modes)),
            irreversible_risks=tuple(dict.fromkeys(irreversible)),
            alternative_actions=tuple(dict.fromkeys(alternatives)),
        )

    @staticmethod
    def _case_text(case: DecisionCase) -> str:
        values = [case.domain, case.objective, case.proposed_action, *case.assumptions]
        values.extend(f"{key}={value}" for key, value in case.facts.items())
        return " ".join(str(value) for value in values).casefold()

    @staticmethod
    def _dominant_pattern(case: DecisionCase) -> str:
        for key in ("source_kind", "platform", "capability", "title"):
            value = case.facts.get(key)
            if value:
                return str(value)
        return case.domain
