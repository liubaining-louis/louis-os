"""Reconcile submitted work with authoritative acceptance and payout evidence.

The state model deliberately keeps four different facts separate:

* submitted work;
* counterparty acceptance;
* a queued payout;
* a balance actually received.

No crypto amount is converted into EUR here.  Liquidity and an authoritative
exchange path must be verified separately before EUR revenue can be claimed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


_TRUSTED_RUSTCHAIN_AUTHORS = {"scottcjn"}
_QUEUED_RE = re.compile(r"\bpayouts?\s+queued\b", re.I)
_PAID_RE = re.compile(r"\b(?:payout|payment)\s+(?:is\s+|was\s+)?(?:confirmed|settled|paid)\b", re.I)
_VOIDED_RE = re.compile(r"\b(?:payout|pending(?:_id)?)\b.{0,60}\b(?:voided|cancelled|canceled)\b", re.I | re.S)
_AMOUNT_RE = re.compile(r"\b(?P<amount>[0-9]+(?:\.[0-9]+)?)\s*RTC\b", re.I)
_PENDING_RE = re.compile(r"\bpending_id\s+`?(?P<value>[0-9]+)`?", re.I)
_TX_RE = re.compile(r"\btx\s+`?(?P<value>[0-9a-f]{16,128})`?", re.I)
_CONFIRMATION_RE = re.compile(
    r"(?P<date>20[0-9]{2}-[0-9]{2}-[0-9]{2})\s+(?P<time>[0-9]{2}:[0-9]{2})\s*UTC",
    re.I,
)


def github_comments_api_url(target_url: str) -> str | None:
    """Translate one canonical RustChain issue URL into its public API URL."""

    parsed = urlparse(str(target_url or ""))
    match = re.fullmatch(r"/Scottcjn/rustchain-bounties/issues/(?P<number>[0-9]+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not match:
        return None
    return (
        "https://api.github.com/repos/Scottcjn/rustchain-bounties/issues/"
        f"{match.group('number')}/comments?per_page=100"
    )


def _identity_line(body: str, wallet: str) -> str:
    needles = tuple(
        value for value in (wallet.casefold(), "louis os", "liubaining-louis") if value
    )
    for line in body.splitlines():
        folded = line.casefold()
        if any(needle in folded for needle in needles):
            return line
    return ""


def _confirmation_at(body: str) -> str:
    match = _CONFIRMATION_RE.search(body)
    if not match:
        return ""
    parsed = datetime.strptime(
        f"{match.group('date')} {match.group('time')}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _counterparty_outcome(
    receipt: Mapping[str, Any], comments: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    wallet = str(receipt.get("payout_wallet") or "").strip()
    candidates: list[dict[str, Any]] = []
    for comment in comments:
        author = str((comment.get("user") or {}).get("login") or "").casefold()
        if author not in _TRUSTED_RUSTCHAIN_AUTHORS:
            continue
        body = str(comment.get("body") or "")
        identity_line = _identity_line(body, wallet)
        if not identity_line:
            continue
        status = ""
        # "unless voided" in a queued notice is not itself a void event.  A
        # later authoritative void can be stated outside the identity line, so
        # inspect the full body after removing that conditional phrase.
        body_without_conditional = re.sub(r"\bunless\s+voided\b", "", body, flags=re.I)
        if _VOIDED_RE.search(body_without_conditional):
            status = "voided"
        elif _PAID_RE.search(body):
            status = "paid"
        elif _QUEUED_RE.search(body):
            status = "queued"
        if not status:
            continue
        amount_match = _AMOUNT_RE.search(identity_line) or _AMOUNT_RE.search(body)
        pending_match = _PENDING_RE.search(identity_line)
        tx_match = _TX_RE.search(identity_line)
        candidates.append(
            {
                "status": status,
                "created_at": str(comment.get("created_at") or ""),
                "url": str(comment.get("html_url") or ""),
                "author": str((comment.get("user") or {}).get("login") or ""),
                "reward_rtc": float(amount_match.group("amount")) if amount_match else None,
                "pending_id": pending_match.group("value") if pending_match else "",
                "transaction_reference": tx_match.group("value") if tx_match else "",
                "expected_confirmation_at": _confirmation_at(body),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item["created_at"], item["url"]))
    return candidates[-1]


def reconcile_receipts(
    receipt_payload: Mapping[str, Any],
    *,
    comments_by_target: Mapping[str, Sequence[Mapping[str, Any]]],
    wallet_balances_rtc: Mapping[str, float | int],
    checked_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return updated receipts and a conservative aggregate outcome summary."""

    output = deepcopy(dict(receipt_payload))
    rows: list[dict[str, Any]] = []
    for raw in receipt_payload.get("receipts") or []:
        if not isinstance(raw, Mapping):
            continue
        receipt = deepcopy(dict(raw))
        target = str(receipt.get("target_url") or "")
        wallet = str(receipt.get("payout_wallet") or "").strip()
        comments = comments_by_target.get(target) or []
        outcome = _counterparty_outcome(receipt, comments)
        if outcome:
            evidence = list(receipt.get("counterparty_receipt_urls") or [])
            if outcome["url"] and outcome["url"] not in evidence:
                evidence.append(outcome["url"])
            receipt["counterparty_receipt_urls"] = evidence
            receipt["last_followup_check"] = checked_at
            receipt["accepted_verified"] = outcome["status"] in {"queued", "paid"}
            receipt["acceptance_evidence_url"] = outcome["url"]
            receipt["payout_status"] = outcome["status"]
            if outcome["status"] == "queued":
                receipt["counterparty_review_status"] = "accepted_payout_queued"
                receipt["reward_status"] = "accepted_payout_queued_not_paid"
            elif outcome["status"] == "paid":
                receipt["counterparty_review_status"] = "accepted_payout_paid"
                receipt["reward_status"] = "paid"
            elif outcome["status"] == "voided":
                receipt["counterparty_review_status"] = "payout_voided"
                receipt["reward_status"] = "payout_voided"
                receipt["accepted_verified"] = False
            for source, target_name in (
                ("pending_id", "payout_pending_id"),
                ("transaction_reference", "payout_transaction_reference"),
                ("expected_confirmation_at", "payout_expected_confirmation_at"),
            ):
                if outcome.get(source):
                    receipt[target_name] = outcome[source]
            reward = outcome.get("reward_rtc")
            if reward is None:
                reward = receipt.get("claimed_reward_rtc")
            if reward is not None and outcome["status"] in {"queued", "paid"}:
                receipt["accepted_reward_rtc"] = float(reward)
        if wallet and wallet in wallet_balances_rtc:
            receipt["wallet_balance_rtc"] = float(wallet_balances_rtc[wallet])
        rows.append(receipt)

    output["receipts"] = rows
    accepted = [row for row in rows if row.get("accepted_verified") is True]
    queued = [row for row in accepted if row.get("payout_status") == "queued"]
    paid = [row for row in accepted if row.get("payout_status") == "paid"]
    balances = {
        wallet: float(value)
        for wallet, value in wallet_balances_rtc.items()
        if str(wallet).strip()
    }
    summary = {
        "accepted_count": len(accepted),
        "accepted_receipt_ids": sorted(str(row.get("action_id") or "") for row in accepted),
        "payout_queued_count": len(queued),
        "payout_queued_receipt_ids": sorted(str(row.get("action_id") or "") for row in queued),
        "payout_paid_count": len(paid),
        "payout_paid_receipt_ids": sorted(str(row.get("action_id") or "") for row in paid),
        "payout_queued_rtc": round(
            sum(float(row.get("accepted_reward_rtc") or 0.0) for row in queued), 8
        ),
        "payout_paid_rtc": round(
            sum(float(row.get("accepted_reward_rtc") or 0.0) for row in paid), 8
        ),
        "wallet_balances_rtc": dict(sorted(balances.items())),
        "counterparty_evidence_urls": sorted(
            {
                str(row.get("acceptance_evidence_url") or "")
                for row in accepted
                if row.get("acceptance_evidence_url")
            }
        ),
    }
    summary["payout_expected_count"] = len(queued) + len(paid)
    summary["payout_expected_rtc"] = round(
        float(summary["payout_queued_rtc"]) + float(summary["payout_paid_rtc"]), 8
    )
    return output, summary


def wallet_settlement_view(
    ledger: Mapping[str, Any], summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Compute aggregate wallet settlement relative to the last known baseline."""

    balances = summary.get("wallet_balances_rtc")
    balances = balances if isinstance(balances, Mapping) else {}
    total_balance = round(sum(float(value or 0.0) for value in balances.values()), 8)
    historical_balance = ledger.get("last_external_wallet_balance_rtc")
    baseline = ledger.get("rustchain_wallet_baseline_rtc")
    if baseline is None:
        baseline = float(historical_balance or 0.0) if historical_balance is not None else total_balance
    baseline = float(baseline or 0.0)
    received = round(max(0.0, total_balance - baseline), 8)
    expected_count = int(
        summary.get("payout_expected_count")
        or int(summary.get("payout_queued_count") or 0)
        + int(summary.get("payout_paid_count") or 0)
    )
    expected_rtc = float(
        summary.get("payout_expected_rtc")
        or float(summary.get("payout_queued_rtc") or 0.0)
        + float(summary.get("payout_paid_rtc") or 0.0)
    )
    return {
        "wallet_balance_rtc_total": total_balance,
        "wallet_baseline_rtc": baseline,
        "wallet_received_rtc": received,
        "aggregate_wallet_settlement_verified": (
            expected_count > 0 and expected_rtc > 0 and received >= expected_rtc
        ),
    }


def apply_summary_to_ledger(
    ledger: Mapping[str, Any], summary: Mapping[str, Any], *, checked_at: str
) -> dict[str, Any]:
    """Apply verified transitions without ever manufacturing EUR revenue."""

    result = deepcopy(dict(ledger))
    accepted = int(summary.get("accepted_count") or 0)
    queued = int(summary.get("payout_queued_count") or 0)
    paid = int(summary.get("payout_paid_count") or 0)
    result["qualified_replies"] = max(int(result.get("qualified_replies") or 0), accepted)
    result["replies_verified"] = max(int(result.get("replies_verified") or 0), accepted)
    result["conversions"] = max(int(result.get("conversions") or 0), accepted)
    result["missions_won_verified"] = max(int(result.get("missions_won_verified") or 0), accepted)
    result["external_actions_accepted"] = max(int(result.get("external_actions_accepted") or 0), accepted)
    # These are current states, not lifetime maxima.  Keeping a stale queued
    # count after a paid or void transition would strand the root-cause engine
    # at the wrong funnel stage.
    result["payouts_queued"] = queued
    result["payout_queued_rtc"] = float(summary.get("payout_queued_rtc") or 0.0)
    result["payouts_paid_by_counterparty_receipt"] = paid
    result["payout_paid_rtc"] = float(summary.get("payout_paid_rtc") or 0.0)
    result["payout_expected_rtc"] = float(
        summary.get("payout_expected_rtc")
        or result["payout_queued_rtc"] + result["payout_paid_rtc"]
    )

    settlement = wallet_settlement_view(result, summary)
    total_balance = float(settlement["wallet_balance_rtc_total"])
    baseline = float(settlement["wallet_baseline_rtc"])
    result["rustchain_wallet_baseline_rtc"] = baseline
    result["rustchain_wallet_balance_rtc"] = total_balance
    result["rustchain_wallet_balance_verified_at"] = checked_at
    result["last_external_wallet_balance_rtc"] = total_balance
    received = float(settlement["wallet_received_rtc"])
    result["revenue_received_rtc"] = max(float(result.get("revenue_received_rtc") or 0.0), received)

    aggregate_settled = bool(settlement["aggregate_wallet_settlement_verified"])
    result["rustchain_aggregate_wallet_settlement_verified"] = aggregate_settled
    if aggregate_settled:
        result["payouts_received_verified"] = max(
            int(result.get("payouts_received_verified") or 0),
            int(summary.get("payout_expected_count") or queued + paid),
        )
        result["crypto_payment_verified"] = True
        result["submission_blocked_stage"] = "fiat_liquidity_and_next_payment"
        result["next_action"] = (
            "Preserve the verified RTC wallet receipt, verify a lawful liquid conversion path, and win one "
            "additional no-stake mission before claiming the first EUR."
        )
    elif queued or paid:
        result["crypto_payment_verified"] = bool(result.get("crypto_payment_verified"))
        result["submission_blocked_stage"] = (
            "payout_queued_waiting_wallet_confirmation"
            if queued
            else "counterparty_marked_paid_waiting_wallet_confirmation"
        )
        result["next_action"] = (
            "Monitor the authoritative RTC wallet until the accepted payout changes the balance; keep EUR revenue at zero."
        )

    # Explicit truth boundary: acceptance, a queue and a token balance are not
    # an independently verified EUR conversion.
    result["revenue_confirmed_eur"] = float(ledger.get("revenue_confirmed_eur") or 0.0)
    result["revenue_received"] = float(ledger.get("revenue_received") or 0.0)
    result["rtc_to_eur_counting_policy"] = (
        "Do not count RTC as EUR revenue without a verified liquid conversion path and receipt."
    )
    result["last_external_outcome_reconciliation"] = checked_at
    result["updated_at"] = checked_at
    return result
