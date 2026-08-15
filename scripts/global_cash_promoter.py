#!/usr/bin/env python3
"""Promote worldwide discovery hits into a small, evidence-backed cash shortlist.

Discovery is intentionally broad; promotion is deliberately strict. This worker does
not claim, apply, create accounts, accept terms, spend, sign, or submit work. It only
selects low-friction candidates for the existing execution / Mission Bridge path.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "global_cash_shortlist.json"
OUT.parent.mkdir(exist_ok=True)
TOKEN = os.getenv("GITHUB_TOKEN", "")
UA = "Louis-OS-Global-Cash-Promoter/1.0"
TARGET = 8
MAX_ATTEMPTS = 5
MAX_REWARD_USD = 100.0
MIN_REWARD_USD = 1.0
MAX_PER_REPO = 2

QUERIES = [
    'is:issue is:open (bounty OR reward) (python OR script OR api OR test OR documentation) archived:false',
    'is:issue is:open (bounty OR reward) (javascript OR typescript OR go OR csv OR json) archived:false',
    'is:issue is:open ("/bounty $" OR "/opire try") archived:false',
    'is:issue is:open "paid on merge" archived:false',
    'repo:auscaster/frantic-board is:issue is:open "Worker price:" "Funding receipt:"',
]

MONEY_RE = re.compile(r"(?:\$|US\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(USD|USDC|EUR|GBP)", re.I)
ATTEMPT_RE = re.compile(r"(?:/attempt\b|/opire\s+try\b|\bclaim(?:ing|ed)?\b|\bi(?:'d| would|’d) like to work\b|\btaking this\b)", re.I)
CAPABILITY_RE = re.compile(r"\b(python|bash|shell|script|api|json|csv|typescript|javascript|\bgo\b|documentation|docs|readme|test|testing|ci|translation|locali[sz]ation|bug fix|data)\b", re.I)
HUMAN_GATE_RE = re.compile(r"\b(kyc|identity verification|verify identity|passport|government id|create an account|register an account|sign up|wallet signature|sign a message|star the repo|star this repository|aibtc identity|btc address|stx address|video interview|phone verification)\b", re.I)
FAST_REJECT_RE = re.compile(r"\b(exploit|zero[- ]day|rce|phishing|malware|credential|double[- ]spend|fund theft|security audit|penetration|red team|smart contract exploit)\b", re.I)
STALE_RE = re.compile(r"\b(closed|cancelled|canceled|withdrawn|winner selected|already paid|completed)\b", re.I)


def gh(url: str) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
        return json.load(r)


def money_values(text: str) -> list[float]:
    out: list[float] = []
    for m in MONEY_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "0").replace(",", "")
        cur = (m.group(3) or "USD").upper()
        try:
            value = float(raw)
        except ValueError:
            continue
        # Conservative near-parity normalization for shortlist ranking only.
        if cur == "GBP": value *= 1.25
        elif cur == "EUR": value *= 1.1
        out.append(value)
    return out


def repo_and_number(item: dict[str, Any]) -> tuple[str, int] | None:
    api = str(item.get("repository_url") or "")
    m = re.search(r"/repos/([^/]+/[^/]+)$", api)
    if not m:
        m = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", str(item.get("html_url") or ""))
        return (m.group(1), int(m.group(2))) if m else None
    return m.group(1), int(item.get("number") or 0)


def payment_evidence(repo: str, body: str, comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Recognized provider comments. Never infer payment merely from issue prose.
    evidences: list[dict[str, Any]] = []
    for c in comments:
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        login = str(user.get("login") or "").casefold().replace("[bot]", "")
        text = str(c.get("body") or "")
        vals = money_values(text)
        if not vals:
            continue
        if login == "algora-pbc" and "💎" in text and "/attempt" in text and "/claim" in text:
            evidences.append({"provider": "algora", "amount_usd_hint": max(vals), "evidence_url": c.get("html_url")})
        elif "opire" in login and re.search(r"\b(try|claim|bounty|reward)\b", text, re.I):
            evidences.append({"provider": "opire", "amount_usd_hint": max(vals), "evidence_url": c.get("html_url")})
    if evidences:
        # Prefer a qualifying micro-bounty amount, not a giant aggregate/table amount.
        eligible = [e for e in evidences if MIN_REWARD_USD <= float(e["amount_usd_hint"]) <= MAX_REWARD_USD]
        if eligible:
            return max(eligible, key=lambda e: float(e["amount_usd_hint"]))

    # Frantic mirrors carry both an explicit funding receipt and source-of-truth claim URL.
    if repo.casefold() == "auscaster/frantic-board" and "Funding receipt:" in body and "Worker price:" in body and re.search(r"Status:\s*Available", body, re.I):
        vals = money_values(body)
        if vals:
            return {"provider": "frantic", "amount_usd_hint": min(vals), "evidence_url": re.search(r"Funding receipt:\s*(https?://\S+)", body).group(1).rstrip(')') if re.search(r"Funding receipt:\s*(https?://\S+)", body) else ""}
    return None


def unique_attempts(comments: list[dict[str, Any]]) -> list[str]:
    people: set[str] = set()
    for c in comments:
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        login = str(user.get("login") or "")
        if not login or login.endswith("[bot]"):
            continue
        if ATTEMPT_RE.search(str(c.get("body") or "")):
            people.add(login.casefold())
    return sorted(people)


def candidate_score(amount: float, attempts: int, text: str, repo: str) -> float:
    score = 55.0
    score += min(20.0, amount / 5.0)
    score += 12.0 if CAPABILITY_RE.search(text) else 0.0
    score += max(0.0, 15.0 - attempts * 3.0)
    if repo.casefold().startswith("scottcjn/"): score -= 8.0  # favor global source diversity
    return round(max(0.0, min(100.0, score)), 1)


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    inspected = 0

    for query in QUERIES:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 30})
        try:
            payload = gh(url)
        except Exception as exc:
            errors.append(f"search:{type(exc).__name__}:{exc}")
            continue
        for item in payload.get("items", []):
            key = str(item.get("html_url") or "")
            if key:
                found[key] = item

    selected_pool: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for url, item in found.items():
        inspected += 1
        parsed = repo_and_number(item)
        if not parsed or parsed[1] <= 0:
            continue
        repo, number = parsed
        if repo.casefold() == "liubaining-louis/louis-os":
            continue
        title = str(item.get("title") or "")
        body = str(item.get("body") or "")
        text = f"{title}\n{body}"
        base = {"id": hashlib.sha256(url.encode()).hexdigest()[:16], "repo": repo, "issue": number, "title": title, "url": url}

        if STALE_RE.search(title):
            rejected.append({**base, "reason": "stale_title_signal"}); continue
        if FAST_REJECT_RE.search(text):
            rejected.append({**base, "reason": "outside_fast_cash_lane"}); continue
        if not CAPABILITY_RE.search(text):
            rejected.append({**base, "reason": "no_validated_capability_match"}); continue

        try:
            comments = gh(f"https://api.github.com/repos/{repo}/issues/{number}/comments?per_page=100")
            if not isinstance(comments, list): comments = []
        except Exception as exc:
            errors.append(f"comments:{repo}#{number}:{type(exc).__name__}:{exc}")
            continue

        evidence = payment_evidence(repo, body, comments)
        attempts = unique_attempts(comments)
        human_gate = bool(HUMAN_GATE_RE.search(text))
        if evidence is None:
            backlog.append({**base, "reason": "authoritative_payment_evidence_missing", "attempts_detected": len(attempts)}); continue
        amount = float(evidence["amount_usd_hint"])
        if not (MIN_REWARD_USD <= amount <= MAX_REWARD_USD):
            rejected.append({**base, "reason": "reward_outside_fast_cash_band", "reward_usd_hint": amount}); continue
        if len(attempts) > MAX_ATTEMPTS:
            rejected.append({**base, "reason": "saturated", "attempts_detected": len(attempts), "reward_usd_hint": amount}); continue
        if human_gate:
            backlog.append({**base, "reason": "human_or_account_gate", "attempts_detected": len(attempts), "reward_usd_hint": amount, "payment": evidence}); continue

        selected_pool.append({
            **base,
            "reward_usd_hint": amount,
            "payment": evidence,
            "attempts_detected": len(attempts),
            "attempt_handles": attempts,
            "status": "ready_to_prepare",
            "execution_authorized": False,
            "score": candidate_score(amount, len(attempts), text, repo),
        })

    selected_pool.sort(key=lambda x: (-x["score"], x["attempts_detected"], -x["reward_usd_hint"], x["repo"]))
    repo_counts: defaultdict[str, int] = defaultdict(int)
    selected: list[dict[str, Any]] = []
    for item in selected_pool:
        if repo_counts[item["repo"]] >= MAX_PER_REPO:
            continue
        repo_counts[item["repo"]] += 1
        selected.append(item)
        if len(selected) >= TARGET:
            break

    payload = {
        "schema_version": 1,
        "generated_at": now,
        "mode": "worldwide_authoritative_cash_promotion",
        "target_active_slots": TARGET,
        "inspected_unique_issues": inspected,
        "authoritative_candidates_before_capacity": len(selected_pool),
        "selected_count": len(selected),
        "selected": selected,
        "human_or_unverified_backlog": sorted(backlog, key=lambda x: x.get("reward_usd_hint", 0), reverse=True)[:30],
        "rejected_count": len(rejected),
        "rejected_reason_counts": {r: sum(1 for x in rejected if x.get("reason") == r) for r in sorted({x.get("reason") for x in rejected})},
        "rules": {
            "reward_usd_band": [MIN_REWARD_USD, MAX_REWARD_USD],
            "max_detected_attempts": MAX_ATTEMPTS,
            "max_per_repository": MAX_PER_REPO,
            "payment_evidence_required": True,
            "human_gate_allowed_in_selected": False,
            "discovery_is_not_submission": True,
            "selected_is_not_revenue": True,
        },
        "errors": errors[:30],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "inspected": inspected, "verified_pool": len(selected_pool), "selected": len(selected), "rejected": len(rejected), "backlog": len(backlog), "top": selected[:5]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
