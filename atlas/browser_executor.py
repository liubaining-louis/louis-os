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
    text = str(value or "")
    return text[:limit]


def run_browser_command(
    root: Path,
    *,
    command_id: str,
    order: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a deliberately read-only browser task using a persistent Chromium profile.

    Supported orders:
      - browser_snapshot: navigate to an allowed HTTPS URL, capture page text + screenshot.
      - browser_current: open the persistent profile and capture its current/initial page.

    This executor intentionally does not expose click, form fill, wallet, auth, upload,
    download, JavaScript evaluation, or transaction primitives.
    """

    context = dict(context or {})
    if order not in {"browser_snapshot", "browser_current"}:
        raise ValueError(f"unsupported_browser_order:{order}")

    results = root / "results"
    profile_dir = results / "browser-profile"
    evidence_dir = results / "browser_evidence"
    profile_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    target_url = str(context.get("url") or "https://app.manic.trade/pm")
    if order == "browser_snapshot":
        target_url = _validate_url(target_url)

    timeout_ms = max(5_000, min(int(context.get("timeout_ms") or 30_000), 60_000))
    screenshot_path = evidence_dir / f"{command_id}.png"
    metadata_path = evidence_dir / f"{command_id}.json"

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - deployment dependency check
        return {
            "status": "failed",
            "execution_mode": "persistent_read_only_browser",
            "reason": f"playwright_unavailable:{type(exc).__name__}",
            "diagnosis": {
                "blocked_stage": "browser_runtime",
                "next_action": "deploy_image_with_playwright_chromium",
            },
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
            if order == "browser_snapshot":
                response = page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                http_status = response.status if response is not None else None
            else:
                http_status = None
                if page.url == "about:blank":
                    page.goto(_validate_url(target_url), wait_until="domcontentloaded", timeout=timeout_ms)

            page.wait_for_timeout(min(2_500, timeout_ms // 4))
            title = _bounded(page.title(), 500)
            final_url = _bounded(page.url, 2_000)
            body_text = _bounded(page.locator("body").inner_text(timeout=timeout_ms), 20_000)
            page.screenshot(path=str(screenshot_path), full_page=False)

            payload = {
                "command_id": command_id,
                "order": order,
                "requested_url": target_url,
                "final_url": final_url,
                "title": title,
                "http_status": http_status,
                "body_text": body_text,
                "profile_dir": str(profile_dir),
                "screenshot": str(screenshot_path),
            }
            metadata_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return {
                "status": "completed",
                "execution_mode": "persistent_read_only_browser",
                "reason": "browser_snapshot_completed",
                "diagnosis": {
                    "blocked_stage": None,
                    "next_action": "inspect_snapshot_or_queue_next_read_only_browser_command",
                },
                "result": payload,
                "evidence": [str(metadata_path), str(screenshot_path)],
            }
        finally:
            context_browser.close()
