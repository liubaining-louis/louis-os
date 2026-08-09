from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


DEFAULT_ALLOWED_HOSTS = {
    "app.manic.trade",
    "manic.trade",
    "polymarket.com",
    "www.polymarket.com",
    "superteam.fun",
    "www.superteam.fun",
}


def _allowed_hosts() -> set[str]:
    raw = os.getenv("LOUIS_BROWSER_ALLOWED_HOSTS", "")
    extra = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return DEFAULT_ALLOWED_HOSTS | extra


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in _allowed_hosts():
        raise ValueError(f"browser_url_not_allowed:{host or 'missing-host'}")
    return url


def _bounded(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _capture(page, *, screenshot_path: Path, timeout_ms: int) -> dict[str, Any]:
    title = _bounded(page.title(), 500)
    final_url = _bounded(page.url, 2_000)
    body_text = _bounded(page.locator("body").inner_text(timeout=timeout_ms), 30_000)
    page.screenshot(path=str(screenshot_path), full_page=False)
    return {
        "title": title,
        "final_url": final_url,
        "body_text": body_text,
        "screenshot": str(screenshot_path),
    }


def _find_search_input(page):
    selectors = [
        'input[type="search"]',
        'input[placeholder*="Search" i]',
        'input[aria-label*="Search" i]',
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            return locator.first
    return None


def _run_manic_market_repro(page, *, context: dict[str, Any], evidence_dir: Path, command_id: str, timeout_ms: int) -> dict[str, Any]:
    target_url = _validate_url(str(context.get("url") or "https://app.manic.trade/pm"))
    targets = context.get("targets") if isinstance(context.get("targets"), list) else []
    if not targets:
        targets = ["EPL: 2027 Champion", "UEFA Champions League: 2027 Champion"]
    attempts = max(1, min(int(context.get("attempts") or 2), 3))

    observations: list[dict[str, Any]] = []
    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(min(2500, timeout_ms // 4))

    for target in [str(item) for item in targets]:
        for attempt in range(1, attempts + 1):
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            search = _find_search_input(page)
            search_used = False
            if search is not None:
                try:
                    search.fill(target, timeout=timeout_ms)
                    search.press("Enter", timeout=timeout_ms)
                    search_used = True
                    page.wait_for_timeout(1800)
                except Exception:
                    search_used = False

            body_before_click = _bounded(page.locator("body").inner_text(timeout=timeout_ms), 30_000)
            target_visible = target.lower() in body_before_click.lower()
            detail_opened = False
            if target_visible:
                try:
                    exact = page.get_by_text(target, exact=True)
                    if exact.count() > 0:
                        exact.first.click(timeout=min(timeout_ms, 8000))
                        page.wait_for_timeout(1500)
                        detail_opened = True
                except Exception:
                    detail_opened = False

            screenshot_path = evidence_dir / f"{command_id}-{attempt}-{abs(hash(target)) % 100000}.png"
            captured = _capture(page, screenshot_path=screenshot_path, timeout_ms=timeout_ms)
            body = captured["body_text"]
            generic_labels = ("Team A" in body and "Team B" in body)
            zero_prob = "0%" in body
            observations.append({
                "target": target,
                "attempt": attempt,
                "search_used": search_used,
                "target_visible": target_visible,
                "detail_opened": detail_opened,
                "generic_labels": generic_labels,
                "zero_probability_present": zero_prob,
                **captured,
            })

    per_target: dict[str, dict[str, Any]] = {}
    for target in [str(item) for item in targets]:
        rows = [row for row in observations if row["target"] == target]
        bad = [row for row in rows if row["generic_labels"] or row["zero_probability_present"]]
        found = [row for row in rows if row["target_visible"]]
        per_target[target] = {
            "attempts": len(rows),
            "found_attempts": len(found),
            "anomalous_attempts": len(bad),
            "reproduced_2_of_2": len(rows) >= 2 and len(bad) >= 2,
        }

    if any(item["reproduced_2_of_2"] for item in per_target.values()):
        verdict = "BUG_CONFIRMED"
    elif all(item["found_attempts"] == 0 for item in per_target.values()):
        verdict = "TARGET_NOT_FOUND"
    else:
        verdict = "NOT_REPRODUCED"

    return {
        "status": "completed",
        "execution_mode": "persistent_read_only_browser",
        "reason": "manic_market_repro_completed",
        "diagnosis": {"blocked_stage": None, "next_action": "prepare_submission_if_bug_confirmed" if verdict == "BUG_CONFIRMED" else "inspect_observations_or_pivot"},
        "result": {"verdict": verdict, "targets": per_target, "observations": observations},
        "evidence": [row["screenshot"] for row in observations],
    }


def run_browser_command(
    root: Path,
    *,
    command_id: str,
    order: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute bounded read-only browser tasks with a persistent Chromium profile."""

    context = dict(context or {})
    if order not in {"browser_snapshot", "browser_current", "manic_market_repro"}:
        raise ValueError(f"unsupported_browser_order:{order}")

    results = root / "results"
    profile_dir = results / "browser-profile"
    evidence_dir = results / "browser_evidence"
    profile_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    target_url = str(context.get("url") or "https://app.manic.trade/pm")
    if order in {"browser_snapshot", "manic_market_repro"}:
        target_url = _validate_url(target_url)

    timeout_ms = max(5_000, min(int(context.get("timeout_ms") or 30_000), 60_000))
    screenshot_path = evidence_dir / f"{command_id}.png"
    metadata_path = evidence_dir / f"{command_id}.json"

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        return {
            "status": "failed",
            "execution_mode": "persistent_read_only_browser",
            "reason": f"playwright_unavailable:{type(exc).__name__}",
            "diagnosis": {"blocked_stage": "browser_runtime", "next_action": "deploy_image_with_playwright_chromium"},
            "evidence": [],
        }

    with sync_playwright() as p:
        context_browser = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        try:
            page = context_browser.pages[0] if context_browser.pages else context_browser.new_page()
            if order == "manic_market_repro":
                outcome = _run_manic_market_repro(
                    page,
                    context=context,
                    evidence_dir=evidence_dir,
                    command_id=command_id,
                    timeout_ms=timeout_ms,
                )
                metadata_path.write_text(json.dumps(outcome, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
                outcome["evidence"] = [str(metadata_path), *outcome.get("evidence", [])]
                return outcome

            if order == "browser_snapshot":
                response = page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                http_status = response.status if response is not None else None
            else:
                http_status = None
                if page.url == "about:blank":
                    page.goto(_validate_url(target_url), wait_until="domcontentloaded", timeout=timeout_ms)

            page.wait_for_timeout(min(2_500, timeout_ms // 4))
            captured = _capture(page, screenshot_path=screenshot_path, timeout_ms=timeout_ms)
            payload = {
                "command_id": command_id,
                "order": order,
                "requested_url": target_url,
                "http_status": http_status,
                "profile_dir": str(profile_dir),
                **captured,
            }
            metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            return {
                "status": "completed",
                "execution_mode": "persistent_read_only_browser",
                "reason": "browser_snapshot_completed",
                "diagnosis": {"blocked_stage": None, "next_action": "inspect_snapshot_or_queue_next_read_only_browser_command"},
                "result": payload,
                "evidence": [str(metadata_path), str(screenshot_path)],
            }
        finally:
            context_browser.close()
