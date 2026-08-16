from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH = Path("config/production_policy.json")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("production policy must be a JSON object")
    for key in ("external_actions_enabled", "kill_switch", "max_autonomous_effort_hours", "max_reward_usd_equivalent"):
        if key not in data:
            raise ValueError(f"production policy missing required field: {key}")
    return data


def preflight(policy: dict[str, Any]) -> PolicyDecision:
    if bool(policy.get("kill_switch")):
        return PolicyDecision(False, "global_kill_switch_active")
    if not bool(policy.get("external_actions_enabled")):
        return PolicyDecision(False, "external_actions_disabled")
    return PolicyDecision(True, "production_policy_allows_external_actions")


def evaluate_candidate(candidate: dict[str, Any], policy: dict[str, Any]) -> PolicyDecision:
    base = preflight(policy)
    if not base.allowed:
        return base

    text = " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "description", "requirements", "category", "family", "task_family")
    ).lower()
    for term in policy.get("blocked_terms") or []:
        if str(term).lower() in text:
            return PolicyDecision(False, f"blocked_term:{term}")

    effort = candidate.get("estimated_effort_hours", candidate.get("effort_hours"))
    if effort is not None:
        try:
            if float(effort) > float(policy["max_autonomous_effort_hours"]):
                return PolicyDecision(False, "effort_exceeds_quick_win_limit")
        except (TypeError, ValueError):
            return PolicyDecision(False, "invalid_effort_estimate")

    reward = candidate.get("reward_usd_equivalent")
    if reward is None:
        reward = candidate.get("reward_amount", candidate.get("budgetUsdc", candidate.get("budget_usdc")))
    if reward is not None:
        try:
            if float(reward) > float(policy["max_reward_usd_equivalent"]):
                return PolicyDecision(False, "reward_exceeds_quick_win_strategy_cap")
        except (TypeError, ValueError):
            return PolicyDecision(False, "invalid_reward_amount")

    family = str(candidate.get("family") or candidate.get("task_family") or "").strip()
    allowed_families = {str(x) for x in policy.get("allowed_families") or []}
    if family and allowed_families and family not in allowed_families:
        return PolicyDecision(False, "task_family_not_allowed_in_quick_win_mode")

    if policy.get("require_verified_payment_path"):
        verified = candidate.get("reward_verified")
        payment_path = candidate.get("payment_path") or candidate.get("paymentProvider") or candidate.get("payment_provider")
        if verified is False:
            return PolicyDecision(False, "payment_path_not_verified")
        if verified is None and not payment_path:
            return PolicyDecision(False, "payment_path_unknown")

    return PolicyDecision(True, "candidate_passes_global_production_policy")


def assert_external_action_allowed(candidate: dict[str, Any], policy: dict[str, Any]) -> None:
    decision = evaluate_candidate(candidate, policy)
    if not decision.allowed:
        raise RuntimeError(f"production_policy_blocked:{decision.reason}")
