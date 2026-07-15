from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputValidation:
    valid: bool
    errors: list[str]


_NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def validate_output_contract(objective: str, answer: str) -> OutputValidation:
    """Validate explicit deliverables with deterministic, domain-neutral checks.

    The validator activates only when the objective explicitly requests structured
    deliverables. It intentionally checks evidence in the final answer rather than
    trusting a model-generated critic verdict.
    """

    objective_lower = objective.casefold()
    answer_lower = answer.casefold()
    errors: list[str] = []

    if not answer.strip():
        return OutputValidation(False, ["empty_answer"])

    structured_request = _contains_any(
        objective,
        ("livrables obligatoires", "livrables attendus", "must include", "required deliverables"),
    )
    if not structured_request:
        return OutputValidation(True, [])

    requested_table = "tableau" in objective_lower or "table" in objective_lower
    if requested_table:
        has_markdown_table = answer.count("|") >= 8 and "---" in answer
        has_multiple_numeric_lines = sum(bool(_NUMERIC_RE.search(line)) for line in answer.splitlines()) >= 4
        if not (has_markdown_table or has_multiple_numeric_lines):
            errors.append("missing_quantitative_table")

    if _contains_any(objective, ("marge", "margin")):
        required_margin_terms = ("marge brute", "marge/kg", "taux de marge")
        missing = [term for term in required_margin_terms if term not in answer_lower]
        if missing:
            errors.append("missing_margin_metrics:" + ",".join(missing))

    if _contains_any(objective, ("classement", "ranking", "score /10", "score/10")):
        has_ranking = _contains_any(answer, ("classement", "rang", "score", "/10"))
        numbered_rows = len(re.findall(r"(?m)^\s*\d+[.)]\s+", answer))
        if not has_ranking or numbered_rows < 3:
            errors.append("missing_ranked_results")

    if _contains_any(objective, ("90 jours", "90-day", "semaine par semaine")):
        week_mentions = len(re.findall(r"\bsemaine\s+\d+\b", answer_lower))
        if week_mentions < 4:
            errors.append("missing_90_day_weekly_plan")

    if _contains_any(objective, ("go / no-go", "go/no-go", "go sous conditions", "decision finale", "décision finale")):
        if not _contains_any(answer, ("go sous conditions", "no-go", "no go", "décision : go", "decision: go")):
            errors.append("missing_final_decision")

    if _contains_any(objective, ("calcul", "formula", "formule")):
        has_formula_signal = "=" in answer or _contains_any(answer, ("formule", "calcul", "coût par kg", "cost per kg"))
        if not has_formula_signal:
            errors.append("missing_explicit_calculation")

    if _contains_any(objective, ("questions à poser", "questions to ask")):
        question_count = answer.count("?")
        if question_count < 5:
            errors.append("missing_qualification_questions")

    if _contains_any(objective, ("séquence de 4", "sequence of 4")):
        contact_mentions = len(re.findall(r"(?i)contact\s*[1-4]|message\s*[1-4]|étape\s*[1-4]", answer))
        if contact_mentions < 4:
            errors.append("missing_four_touch_sequence")

    return OutputValidation(not errors, errors)
