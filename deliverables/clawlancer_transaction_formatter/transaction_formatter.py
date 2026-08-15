"""Human-readable Markdown formatter for blockchain transaction histories."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any


def _short(value: Any, *, head: int = 6, tail: int = 4) -> str:
    """Shorten long identifiers while preserving compact values."""
    if value is None or value == "":
        return "—"
    text = str(value)
    if len(text) <= head + tail + 3:
        return text
    return f"{text[:head]}…{text[-tail:]}"


def _escape(value: Any) -> str:
    """Escape Markdown table separators/newlines."""
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _timestamp(value: Any) -> str:
    """Normalize unix timestamps or ISO strings to readable UTC text."""
    if value in (None, ""):
        return "—"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return _escape(text)


def _amount(tx: Mapping[str, Any]) -> str:
    """Render a value and optional currency/token symbol."""
    value = tx.get("value", tx.get("amount"))
    if value in (None, ""):
        return "—"
    symbol = tx.get("symbol") or tx.get("token") or tx.get("currency") or ""
    rendered = _escape(value)
    return f"{rendered} {_escape(symbol)}".strip()


def format_transactions(transactions: Iterable[Mapping[str, Any]]) -> str:
    """Format blockchain transactions as a deterministic Markdown table.

    Supported common aliases:
    - hash: ``hash`` / ``tx_hash`` / ``transaction_hash``
    - from: ``from`` / ``from_address`` / ``sender``
    - to: ``to`` / ``to_address`` / ``recipient``
    - value: ``value`` / ``amount`` with optional ``symbol``/``token``/``currency``
    - timestamp: ``timestamp`` / ``time`` / ``created_at``
    - status: ``status`` (defaults to ``unknown``)

    The input is never mutated.
    """
    rows = list(transactions)
    if not rows:
        return "_No transactions._"
    if any(not isinstance(tx, Mapping) for tx in rows):
        raise TypeError("each transaction must be a mapping")

    header = "| # | Transaction | From | To | Amount | Status | Time |"
    separator = "|---:|---|---|---|---:|---|---|"
    output = [header, separator]

    for index, tx in enumerate(rows, start=1):
        tx_hash = tx.get("hash", tx.get("tx_hash", tx.get("transaction_hash")))
        sender = tx.get("from", tx.get("from_address", tx.get("sender")))
        recipient = tx.get("to", tx.get("to_address", tx.get("recipient")))
        status = tx.get("status", "unknown")
        when = tx.get("timestamp", tx.get("time", tx.get("created_at")))
        output.append(
            "| {index} | `{tx_hash}` | `{sender}` | `{recipient}` | {amount} | {status} | {when} |".format(
                index=index,
                tx_hash=_escape(_short(tx_hash)),
                sender=_escape(_short(sender)),
                recipient=_escape(_short(recipient)),
                amount=_amount(tx),
                status=_escape(status),
                when=_timestamp(when),
            )
        )

    return "\n".join(output)
