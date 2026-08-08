from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .superteam_agent import create_submission, live_listings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _metadata_token() -> str:
    req = Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urlopen(req, timeout=5) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str(payload.get("access_token") or "")


def _secret_manager_value(secret_name: str) -> str:
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814").strip()
    if not project:
        return ""
    try:
        token = _metadata_token()
        if not token:
            return ""
        url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets/{secret_name}/versions/latest:access"
        req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        encoded = str(((payload.get("payload") or {}).get("data")) or "")
        return base64.b64decode(encoded).decode("utf-8").strip() if encoded else ""
    except Exception:
        return ""


def _api_key() -> str:
    return os.getenv("SUPERTEAM_API_KEY", "").strip() or _secret_manager_value(
        os.getenv("SUPERTEAM_API_SECRET_NAME", "superteam-api-key")
    )


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("listings", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _rank(item: dict[str, Any]) -> tuple[float, float, str]:
    access = str(item.get("agentAccess") or item.get("agent_access") or "")
    eligible = 1.0 if access in {"AGENT_ALLOWED", "AGENT_ONLY"} else 0.0
    reward = item.get("rewardAmount", item.get("reward", item.get("amount", 0)))
    try:
        reward_f = float(reward or 0)
    except (TypeError, ValueError):
        reward_f = 0.0
    return (-eligible, -reward_f, str(item.get("id") or item.get("slug") or ""))


def run_superteam_crypto_cycle(root: Path) -> dict[str, Any]:
    results = root / "results"
    candidates_path = results / "superteam_candidates.json"
    package_path = results / "superteam_submission_package.json"
    receipt_path = results / "superteam_submission_receipt.json"
    ledger_path = results / "monetization.json"
    api_key = _api_key()
    if not api_key:
        return {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "superteam_api_key_missing",
            "diagnosis": {"blocked_stage": "platform_auth", "next_action": "bootstrap_superteam_agent_secret"},
            "evidence": [],
        }

    payload = live_listings(api_key, take=50)
    items = _items(payload)
    eligible = [x for x in items if str(x.get("agentAccess") or x.get("agent_access") or "") in {"AGENT_ALLOWED", "AGENT_ONLY"}]
    eligible.sort(key=_rank)
    _save(candidates_path, {"updated_at": _now(), "count": len(eligible), "candidates": eligible})
    if not eligible:
        return {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "blocked_no_eligible_bounty",
            "diagnosis": {"blocked_stage": "opportunity_discovery", "next_action": "refresh_superteam_agent_listings"},
            "evidence": [str(candidates_path.relative_to(root))],
        }

    selected = eligible[0]
    selected_id = str(selected.get("id") or selected.get("listingId") or "")
    package = _load(package_path, {})
    package_matches = isinstance(package, dict) and str(package.get("listingId") or "") == selected_id
    if not package_matches:
        return {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "prepare_then_gate",
            "result": {"selected": selected, "required_package_path": str(package_path.relative_to(root))},
            "diagnosis": {"blocked_stage": "deliverable_package", "next_action": "build_superteam_submission_package_for_selected_listing"},
            "evidence": [str(candidates_path.relative_to(root))],
        }

    link = str(package.get("link") or "").strip()
    other_info = str(package.get("otherInfo") or "").strip()
    if not link and len(other_info) < 80:
        return {
            "status": "blocked",
            "execution_mode": "deterministic_superteam_executor",
            "reason": "prepare_then_gate",
            "diagnosis": {"blocked_stage": "deliverable_package", "next_action": "add_valid_link_or_detailed_otherInfo"},
            "evidence": [str(candidates_path.relative_to(root)), str(package_path.relative_to(root))],
        }

    receipt = create_submission(
        api_key,
        listing_id=selected_id,
        link=link,
        other_info=other_info,
        eligibility_answers=package.get("eligibilityAnswers") if isinstance(package.get("eligibilityAnswers"), list) else [],
        ask=package.get("ask"),
        telegram=str(package.get("telegram") or "").strip() or None,
        tweet=str(package.get("tweet") or ""),
    )
    _save(receipt_path, {"submitted_at": _now(), "listingId": selected_id, "receipt": receipt})
    ledger = _load(ledger_path, {})
    if not isinstance(ledger, dict):
        ledger = {}
    ledger["external_actions_submitted"] = int(ledger.get("external_actions_submitted") or 0) + 1
    ledger["internet_actions_submitted"] = int(ledger.get("internet_actions_submitted") or 0) + 1
    ledger["last_verified_external_submission"] = {"platform": "superteam", "listingId": selected_id, "receipt": receipt, "submitted_at": _now()}
    ledger["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    _save(ledger_path, ledger)
    return {
        "status": "completed",
        "execution_mode": "deterministic_superteam_executor",
        "result": "verified_external_submission",
        "evidence": [str(candidates_path.relative_to(root)), str(package_path.relative_to(root)), str(receipt_path.relative_to(root)), str(ledger_path.relative_to(root))],
        "external_actions_submitted": ledger["external_actions_submitted"],
        "revenue_confirmed_eur": ledger["revenue_confirmed_eur"],
    }
