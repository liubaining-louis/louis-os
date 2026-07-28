"""Verified operational state exposed to the Louis OS chat.

GitHub is the preferred live source for workflows and versioned result artefacts.
Firestore supplies worker runtime state. Local files are an explicit fallback only.
Missing evidence is reported instead of guessed.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
GITHUB_REPOSITORY = os.getenv("LOUIS_GITHUB_REPOSITORY", "liubaining-louis/louis-os")
GITHUB_BRANCH = os.getenv("LOUIS_GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.getenv("LOUIS_GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", ""))
GITHUB_TIMEOUT = int(os.getenv("LOUIS_GITHUB_TIMEOUT", "12"))

RESULT_FILES = (
    "monetization.json",
    "paid_mission_apprenticeship.json",
    "mission_intelligence.json",
    "reflective_evolution.json",
    "github_runtime_preflight.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _count_jsonl(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _github_request(path: str) -> Any:
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/{path.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-live-state",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_content(path: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(path, safe="/")
    payload = _github_request(f"contents/{encoded}?ref={urllib.parse.quote(GITHUB_BRANCH)}")
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        return {}
    try:
        raw = base64.b64decode(str(payload.get("content", ""))).decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _github_state() -> dict[str, Any]:
    checked_at = _now()
    if not GITHUB_TOKEN:
        return {
            "available": False,
            "authenticated": False,
            "checked_at": checked_at,
            "error": "missing_louis_github_token",
            "repository": GITHUB_REPOSITORY,
            "branch": GITHUB_BRANCH,
            "results": {},
            "workflows": [],
        }
    try:
        repository = _github_request("")
        commit = _github_request(f"commits/{urllib.parse.quote(GITHUB_BRANCH)}")
        runs_payload = _github_request("actions/runs?per_page=30")
        runs = runs_payload.get("workflow_runs", []) if isinstance(runs_payload, dict) else []
        workflows = []
        for run in runs[:15]:
            workflows.append({
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "event": run.get("event"),
                "head_sha": run.get("head_sha"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "html_url": run.get("html_url"),
                "run_number": run.get("run_number"),
            })
        remote_results = {name: _github_content(f"results/{name}") for name in RESULT_FILES}
        return {
            "available": True,
            "authenticated": True,
            "checked_at": checked_at,
            "error": None,
            "repository": repository.get("full_name", GITHUB_REPOSITORY),
            "branch": GITHUB_BRANCH,
            "default_branch": repository.get("default_branch"),
            "latest_commit": {
                "sha": commit.get("sha"),
                "message": ((commit.get("commit") or {}).get("message")),
                "committed_at": (((commit.get("commit") or {}).get("committer") or {}).get("date")),
                "html_url": commit.get("html_url"),
            },
            "results": remote_results,
            "workflows": workflows,
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "authenticated": bool(GITHUB_TOKEN),
            "checked_at": checked_at,
            "error": type(exc).__name__,
            "repository": GITHUB_REPOSITORY,
            "branch": GITHUB_BRANCH,
            "results": {},
            "workflows": [],
        }


def _runtime_state() -> dict[str, Any]:
    try:
        snap = firestore.Client(project=PROJECT_ID).collection("louis_runtime").document("current").get()
        return snap.to_dict() if snap.exists else {}
    except Exception as exc:
        return {"worker_status": "unknown", "runtime_read_error": type(exc).__name__}


def _response_policy() -> dict[str, Any]:
    return {
        "mode": "initiative_first_result_driven",
        "default_behavior": [
            "use live GitHub state before local artefacts when available",
            "state the source, timestamp and freshness of operational claims",
            "infer and start the best low-risk reversible next step",
            "report actions with evidence and distinguish attempted, prepared and verified outcomes",
        ],
        "human_confirmation_only_for": [
            "money movement or paid purchase", "contract or binding commitment",
            "account creation, identity verification or KYC", "privileged credential escalation",
            "destructive, irreversible or privacy-sensitive action",
        ],
        "response_contract": {
            "must_include": ["decision", "next concrete step", "evidence status", "data freshness"],
            "must_not_claim": "a successful workflow, external submission or payment without a receipt",
        },
    }


def _latest_workflow_by_name(workflows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in workflows:
        name = str(run.get("name") or "unknown")
        if name not in latest:
            latest[name] = run
    return latest


def snapshot() -> dict[str, Any]:
    github = _github_state()
    remote = github.get("results", {}) if github.get("available") else {}
    local_money = _read_json(RESULTS / "monetization.json")
    money = remote.get("monetization.json") or local_money
    apprenticeship = remote.get("paid_mission_apprenticeship.json") or _read_json(RESULTS / "paid_mission_apprenticeship.json")
    intelligence = remote.get("mission_intelligence.json") or _read_json(RESULTS / "mission_intelligence.json")
    reflection = remote.get("reflective_evolution.json") or _read_json(RESULTS / "reflective_evolution.json")
    preflight = remote.get("github_runtime_preflight.json") or _read_json(RESULTS / "github_runtime_preflight.json")
    experiments = _count_jsonl(RESULTS / "monetization_experiments.jsonl")
    evidence = _count_jsonl(RESULTS / "evidence.jsonl")
    runtime = _runtime_state()
    workflow_latest = _latest_workflow_by_name(github.get("workflows", []))

    worker_verified = bool(runtime.get("worker_verified"))
    external_actions = int(runtime.get("external_actions_submitted", runtime.get("actions_submitted", 0)) or 0)
    verified_receipts = int(runtime.get("external_receipts_verified", 0) or 0)
    selected_mission = apprenticeship.get("mission") if apprenticeship.get("selected") else None
    coaching = apprenticeship.get("coaching") or {}

    source_mode = "github_live" if github.get("available") else "local_fallback"
    freshest = max(
        [str(x) for x in (
            github.get("checked_at"),
            apprenticeship.get("generated_at"), intelligence.get("generated_at"),
            reflection.get("generated_at"), money.get("updated_at"), runtime.get("last_cycle_at"),
        ) if x],
        default=None,
    )

    return {
        "identity": "Louis OS / ATLAS",
        "project": PROJECT_ID,
        "master_mission": {"issue": 77, "objective": "Obtenir des revenus réels hors charbon par des expériences légales, mesurées et prouvées."},
        "response_policy": _response_policy(),
        "data_freshness": {
            "mode": source_mode,
            "checked_at": github.get("checked_at"),
            "freshest_known_at": freshest,
            "github_available": github.get("available", False),
            "github_authenticated": github.get("authenticated", False),
            "github_error": github.get("error"),
            "local_fallback_used": not github.get("available", False),
        },
        "github": {
            "repository": github.get("repository"),
            "branch": github.get("branch"),
            "latest_commit": github.get("latest_commit"),
            "runtime_preflight": preflight,
            "latest_workflows": workflow_latest,
        },
        "autonomous_worker": {
            "status": runtime.get("worker_status", "not_verified"),
            "verified": worker_verified,
            "last_cycle_at": runtime.get("last_cycle_at", runtime.get("synced_at")),
            "last_cycle_status": runtime.get("last_cycle_status", runtime.get("execution_status")),
            "sources_checked": runtime.get("sources_checked", 0),
            "opportunities_qualified": runtime.get("opportunities_qualified", 0),
            "actions_submitted": external_actions,
            "external_receipts_verified": verified_receipts,
            "next_action": runtime.get("next_action") or coaching.get("next_action") or "Refresh narrow capability-matched sources.",
            "runtime_read_error": runtime.get("runtime_read_error"),
        },
        "current_mission": {
            "selected": bool(selected_mission),
            "mission": selected_mission,
            "stage": coaching.get("stage", "none"),
            "next_action": coaching.get("next_action"),
            "human_action_required": bool((apprenticeship.get("human_action_packet") or {}).get("required")),
            "rejection": apprenticeship.get("rejected_candidate"),
        },
        "monetization": {
            "revenue_received_eur": runtime.get("revenue_confirmed_eur", money.get("revenue_verified_eur", money.get("revenue_received", 0))),
            "weighted_pipeline_eur": money.get("weighted_pipeline", 0),
            "external_submissions_verified": money.get("external_submissions_verified", external_actions),
            "outreach_sent": money.get("outreach_sent", 0),
            "qualified_replies": money.get("qualified_replies", 0),
            "conversions": money.get("conversions", 0),
            "updated_at": money.get("generated_at", money.get("updated_at")),
            "note": money.get("note", "Aucune note disponible"),
            "recorded_experiments_local": experiments,
            "recorded_evidence_items_local": evidence,
        },
        "learning": {
            "mission_intelligence": intelligence,
            "reflective_evolution": reflection,
        },
        "truth": {
            "workflow_success_requires_github_conclusion_success": True,
            "submission_requires_external_receipt": True,
            "payment_requires_external_receipt": True,
            "local_files_may_be_stale": not github.get("available", False),
        },
    }


def prompt_context() -> str:
    return json.dumps(snapshot(), ensure_ascii=False, indent=2, default=str)
