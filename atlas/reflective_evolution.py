"""Evidence-based reflective evolution for Louis OS.

This module provides disciplined introspection, not consciousness. It converts cycle
metrics into a principal weakness, root-cause hypothesis, balanced corrective plan,
and measurable re-evaluation contract.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class WeaknessDiagnosis:
    weakness_id: str
    weakness_class: str
    principal_weakness: str
    evidence: tuple[str, ...]
    root_cause_hypothesis: str
    confidence: float
    uncertainty: str
    local_impact: str
    systemic_impact: str
    strategic_impact: str
    global_impact: str
    corrective_action: str
    effort: str
    regression_risk: str
    balancing_counter_risk: str
    success_metric: str
    reevaluate_at: str
    higher_order_lesson: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _n(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key, 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def diagnose(metrics: Mapping[str, Any], *, now: datetime | None = None) -> WeaknessDiagnosis:
    now = now or datetime.now(timezone.utc)
    observed = _n(metrics, "opportunities_observed")
    eligible = _n(metrics, "opportunities_eligible")
    prepared = _n(metrics, "dossiers_prepared")
    submitted = _n(metrics, "external_submissions_verified")
    replies = _n(metrics, "replies_verified")
    wins = _n(metrics, "missions_won_verified")
    revenue = _n(metrics, "revenue_verified_eur")
    source_count = _n(metrics, "sources_total")
    rejected = _n(metrics, "opportunities_rejected")

    reevaluate = (now + timedelta(hours=24)).isoformat()

    if observed >= 50 and eligible == 0:
        return WeaknessDiagnosis(
            "qualification-collapse", "strategic",
            "Discovery produces volume but no eligible opportunities.",
            (f"observed={int(observed)}", f"eligible={int(eligible)}", f"rejected={int(rejected)}"),
            "Search allocation or qualification policy is mismatched with executable capabilities and market reality.",
            0.85, "Source quality and filter contribution require per-source decomposition.",
            "No current candidate advances.", "Discovery resources are consumed without conversion.",
            "The system may optimize activity instead of payable work.",
            "Autonomy does not improve because observation is disconnected from action.",
            "Reduce low-yield source weight, expand product-matched queries, and run one bounded source-allocation experiment.",
            "medium", "Over-correction may narrow exploration too aggressively.",
            "Preserve at least 10% exploration allocation.",
            "At least one eligible opportunity from the next 50 observations.", reevaluate,
            "More searching is not more intelligence when the search space is poorly aligned."
        )

    if prepared >= 10 and submitted == 0:
        return WeaknessDiagnosis(
            "preparation-without-action", "operational",
            "The system prepares dossiers but does not cross the submission boundary.",
            (f"prepared={int(prepared)}", f"submitted={int(submitted)}"),
            "Submission dependencies, authorization gates, account access, or dossier quality are not converted into minimal final actions.",
            0.9, "The dominant blocker must be confirmed from receipts.",
            "Prepared work remains unused.", "The execution pipeline terminates before external action.",
            "The system confuses readiness with progress.", "Commercial learning cannot begin without real market contact.",
            "Classify every blocked dossier by one concrete final dependency and automatically surface the smallest resolvable submission action.",
            "low", "Unsafe or unauthorized submission could be triggered.",
            "Require canonical URL, authorization and immutable receipt before submission.",
            "At least one verified submission or a fully evidenced external blocker within 24 hours.", reevaluate,
            "The final meter often matters more than another kilometer of preparation."
        )

    if submitted >= 5 and replies == 0:
        return WeaknessDiagnosis(
            "market-message-mismatch", "commercial",
            "Verified submissions are not generating replies.",
            (f"submitted={int(submitted)}", f"replies={int(replies)}"),
            "Targeting, timing, proof, pricing or proposal framing is failing to create enough relevance and trust.",
            0.8, "Platform visibility and client inactivity may also contribute.",
            "Current proposals do not open conversations.", "The feedback loop receives no customer signal.",
            "Repeated submission without adaptation wastes scarce opportunities.", "The system cannot learn commercial fit from silence alone.",
            "Run a controlled proposal-variant test with stronger problem framing and a bounded proof artifact.",
            "medium", "Changing several variables at once would destroy attribution.",
            "Change one proposal dimension per cohort and retain a control variant.",
            "A verified reply rate above 0% in the next five comparable submissions.", reevaluate,
            "When the world remains silent, change the signal before increasing the volume."
        )

    if wins > 0 and revenue == 0:
        return WeaknessDiagnosis(
            "delivery-to-cash-gap", "commercial",
            "Won missions are not becoming verified revenue.",
            (f"wins={int(wins)}", f"revenue_eur={revenue:.2f}"),
            "Payment terms, acceptance criteria, invoicing, delivery evidence or collection steps are incomplete.",
            0.9, "Payment timing may still be contractually normal.",
            "Completed value is not monetized.", "The revenue ledger cannot close the loop.",
            "Winning work without collection undermines the cash-first objective.", "Economic autonomy remains unproven.",
            "Create an acceptance-to-payment checklist and track the next payment event with evidence.",
            "low", "Aggressive collection could harm the customer relationship.",
            "Respect agreed terms and use proportionate reminders.",
            "A verified acceptance, invoice, payment date or payment receipt for every won mission.", reevaluate,
            "Value is not economically complete until delivery, acceptance and payment align."
        )

    if source_count < 3:
        return WeaknessDiagnosis(
            "source-concentration", "strategic",
            "The learning and opportunity system depends on too few independent sources.",
            (f"sources_total={int(source_count)}",),
            "Source diversity is insufficient for robust market perception and cross-validation.",
            0.75, "Some high-quality narrow sources may still outperform broad coverage.",
            "Local observations may be biased.", "Failures or policy changes in one source affect the whole system.",
            "The system risks mistaking one platform for the market.", "Global vision remains narrow.",
            "Add one independent primary or marketplace source and compare yield rather than merely increasing volume.",
            "medium", "New sources may introduce noise and maintenance cost.",
            "Admit sources through a measured trial with explicit noise and quality thresholds.",
            "At least three independent sources with per-source yield metrics.", reevaluate,
            "Height of vision comes from triangulation, not from staring harder at one point."
        )

    return WeaknessDiagnosis(
        "insufficient-outcome-evidence", "evidence quality",
        "The system lacks enough verified outcomes to identify a stronger weakness confidently.",
        tuple(f"{key}={metrics.get(key)}" for key in sorted(metrics) if key in {
            "opportunities_observed", "dossiers_prepared", "external_submissions_verified",
            "replies_verified", "missions_won_verified", "revenue_verified_eur"
        }),
        "The experience loop is still data-poor or key transitions are not instrumented.",
        0.65, "A hidden operational weakness may exist but cannot yet be separated from missing evidence.",
        "Diagnosis remains broad.", "Learning cannot reliably update strategy.",
        "Premature optimization may encode false lessons.", "Global development is limited by weak observation.",
        "Instrument the next missing verified transition and avoid adding unrelated complexity.",
        "low", "Excessive instrumentation can become bureaucracy.",
        "Capture only evidence needed for the next decision.",
        "One additional verified funnel transition or explicit blocker in the next cycle.", reevaluate,
        "Before correcting the path, improve the quality of seeing."
    )


def review_previous(previous: Mapping[str, Any] | None, current_metrics: Mapping[str, Any]) -> dict[str, Any]:
    if not previous:
        return {"status": "no_previous_action", "improved": None, "reason": "no prior diagnosis available"}
    metric = str(previous.get("success_metric") or "")
    weakness_id = str(previous.get("weakness_id") or "")
    improved = False
    if weakness_id == "qualification-collapse":
        improved = _n(current_metrics, "opportunities_eligible") > 0
    elif weakness_id == "preparation-without-action":
        improved = _n(current_metrics, "external_submissions_verified") > 0
    elif weakness_id == "market-message-mismatch":
        improved = _n(current_metrics, "replies_verified") > 0
    elif weakness_id == "delivery-to-cash-gap":
        improved = _n(current_metrics, "revenue_verified_eur") > 0
    elif weakness_id == "source-concentration":
        improved = _n(current_metrics, "sources_total") >= 3
    return {"status": "reviewed", "improved": improved, "metric_contract": metric}
