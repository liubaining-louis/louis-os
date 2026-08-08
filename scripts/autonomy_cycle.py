#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.autonomy_kernel import build_state, choose_next_action, update_learning
from atlas.runner import ROOT
from atlas.self_healing_monetization import run_self_healing_deliverable_cycle

RESULTS = ROOT / "results"
STATE_PATH = RESULTS / "autonomy_state.json"
DECISIONS_PATH = RESULTS / "autonomy_decisions.jsonl"
LAST_PATH = RESULTS / "autonomy_last_decision.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _run_script(relative: str, timeout: int = 240) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, relative], cwd=ROOT, text=True, capture_output=True, timeout=timeout
    )
    return {
        "status": "completed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "command": relative,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def execute(decision_action: str) -> dict[str, Any]:
    # Explicit GREEN allowlist. The autonomy kernel cannot widen its own
    # security, credential, legal or payment authority.
    if decision_action == "market_refresh":
        return _run_script("scripts/universal_market_cycle.py")
    if decision_action == "candidate_recovery":
        return _run_script("scripts/cash_first_recovery_cycle.py")
    if decision_action == "quality_review":
        return _run_script("scripts/multi_model_monetization_cycle.py")
    if decision_action == "execution_attempt":
        executor_outcome = dict(run_self_healing_deliverable_cycle(ROOT))
        return {"status": str(executor_outcome.get("status") or "failed"), "executor_outcome": executor_outcome}
    return {"status": "failed", "reason": f"action_not_allowlisted:{decision_action}"}


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    state_before = build_state(RESULTS)
    decision = choose_next_action(state_before)
    running = {**decision.to_dict(), "status": "running", "started_at": _now()}
    _save(LAST_PATH, running)

    try:
        outcome = execute(decision.action)
    except subprocess.TimeoutExpired as exc:
        outcome = {"status": "failed", "reason": "action_timeout", "command": str(exc.cmd)}
    except Exception as exc:
        outcome = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    state_after = build_state(RESULTS)
    measured_delta = {
        "opportunities_observed": int(state_after.get("opportunities_observed") or 0) - int(state_before.get("opportunities_observed") or 0),
        "candidates": int(state_after.get("candidates") or 0) - int(state_before.get("candidates") or 0),
        "executable_now": int(state_after.get("executable_now") or 0) - int(state_before.get("executable_now") or 0),
        "external_submissions_verified": int(state_after.get("external_submissions_verified") or 0) - int(state_before.get("external_submissions_verified") or 0),
        "revenue_verified": float(state_after.get("revenue_verified") or 0.0) - float(state_before.get("revenue_verified") or 0.0),
    }
    completed = {
        **decision.to_dict(),
        "status": str(outcome.get("status") or "failed"),
        "finished_at": _now(),
        "outcome": outcome,
        "state_after": state_after,
        "measured_delta": measured_delta,
    }
    with DECISIONS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(completed, ensure_ascii=False, default=str) + "\n")
    _save(LAST_PATH, completed)
    _save(STATE_PATH, state_after)
    update_learning(RESULTS, decision, {**outcome, "measured_delta": measured_delta})
    print(json.dumps({
        "status": completed["status"],
        "decision_id": decision.decision_id,
        "action": decision.action,
        "authority": decision.authority,
        "score": decision.score,
        "measured_delta": measured_delta,
        "next_cycle": state_after.get("cycle"),
    }, ensure_ascii=False))
    return 0 if completed["status"] in {"completed", "ok", "success", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
