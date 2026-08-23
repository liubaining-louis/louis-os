#!/usr/bin/env python3
"""Read public counterparty evidence and reconcile accepted/queued/paid states."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.external_outcome_reconciliation import (
    apply_summary_to_ledger,
    github_comments_api_url,
    reconcile_receipts,
    wallet_settlement_view,
)

RESULTS = ROOT / "results"
RECEIPTS_PATH = RESULTS / "external_action_receipts.json"
LEDGER_PATH = RESULTS / "monetization.json"
STATE_PATH = RESULTS / "external_outcome_reconciliation.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def get_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "Louis-OS-External-Outcome-Reconciler/1.0",
        },
    )
    with urlopen(request, timeout=25) as response:  # nosec B310: URLs are constructed from strict allowlists
        return json.load(response)


def _balance(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("amount_rtc", "balance_rtc", "balance", "amount"):
        if payload.get(key) is None:
            continue
        try:
            return float(payload[key])
        except (TypeError, ValueError):
            continue
    return None


def main() -> int:
    checked_at = datetime.now(timezone.utc).isoformat()
    receipts = load_json(RECEIPTS_PATH, {"receipts": []})
    ledger = load_json(LEDGER_PATH, {})
    comments_by_target: dict[str, list[dict[str, Any]]] = {}
    balances: dict[str, float] = {}
    errors: list[str] = []

    targets = sorted(
        {
            str(row.get("target_url") or "")
            for row in receipts.get("receipts") or []
            if isinstance(row, dict) and github_comments_api_url(str(row.get("target_url") or ""))
        }
    )
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as pool:
        pending_comments = {
            pool.submit(get_json, api_url): target
            for target in targets
            if (api_url := github_comments_api_url(target))
        }
        for future in as_completed(pending_comments):
            target = pending_comments[future]
            try:
                payload = future.result()
                comments_by_target[target] = (
                    [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
                )
            except Exception as exc:
                errors.append(f"comments:{target}:{type(exc).__name__}:{exc}"[:500])

    wallets = sorted(
        {
            str(row.get("payout_wallet") or "").strip()
            for row in receipts.get("receipts") or []
            if isinstance(row, dict) and str(row.get("payout_wallet") or "").startswith("RTC")
        }
    )
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(wallets)))) as pool:
        pending_balances = {
            pool.submit(
                get_json,
                f"https://rustchain.org/wallet/balance?miner_id={quote(wallet, safe='')}",
            ): wallet
            for wallet in wallets
        }
        for future in as_completed(pending_balances):
            wallet = pending_balances[future]
            try:
                value = _balance(future.result())
                if value is not None:
                    balances[wallet] = value
            except Exception as exc:
                errors.append(f"wallet:{wallet}:{type(exc).__name__}:{exc}"[:500])

    errors.sort()

    # A transient wallet outage must not look like an economic transition.  If
    # the probe fails, retain the last authoritative balance until a new value
    # is observed successfully.
    previous_state = load_json(STATE_PATH, {})
    previous_semantic = (
        previous_state.get("semantic") if isinstance(previous_state.get("semantic"), dict) else {}
    )
    previous_balances = previous_semantic.get("wallet_balances_rtc")
    if isinstance(previous_balances, dict):
        for wallet, value in previous_balances.items():
            if wallet not in balances:
                try:
                    balances[str(wallet)] = float(value)
                except (TypeError, ValueError):
                    pass

    reconciled_receipts, summary = reconcile_receipts(
        receipts,
        comments_by_target=comments_by_target,
        wallet_balances_rtc=balances,
        checked_at=checked_at,
    )
    summary.update(wallet_settlement_view(ledger, summary))
    semantic = dict(summary)
    changed = semantic != previous_state.get("semantic")

    if changed:
        reconciled_receipts["updated_at"] = checked_at
        save_json(RECEIPTS_PATH, reconciled_receipts)
        save_json(LEDGER_PATH, apply_summary_to_ledger(ledger, summary, checked_at=checked_at))
        save_json(
            STATE_PATH,
            {
                "schema_version": "1.0",
                "changed_at": checked_at,
                "semantic": semantic,
                "errors_at_change": errors,
                "truth_policy": (
                    "Acceptance and queued payout are not payment. RTC is not EUR revenue without verified liquidity."
                ),
            },
        )

    output = {"changed": changed, **summary, "errors": errors, "checked_at": checked_at}
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
