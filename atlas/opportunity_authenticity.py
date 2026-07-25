"""Fail-closed authenticity checks for public monetization opportunities.

A money amount appearing in an issue is not sufficient evidence of a funded reward.
This module requires an authoritative issue source, explicit reward language tied to
an amount, and an official deliverable/submission path. Negative funding or closure
language always rejects the opportunity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping
from urllib.parse import urlparse


@dataclass(frozen=True)
class OpportunityAuthenticity:
    status: str
    verified: bool
    reward_amount: float
    currency: str
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_MONEY_RE = re.compile(
    r"(?:[$€£]\s?([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s?(USD|EUR|GBP))",
    re.I,
)
_REWARD_TERMS = re.compile(
    r"\b(bounty|reward|prize|stipend|compensation|paid|payment|grant|funded)\b",
    re.I,
)
_SUBMISSION_TERMS = re.compile(
    r"\b(submit|submission|pull request|\bPR\b|patch|implementation|solution|deliverable|acceptance criteria|winner)\b",
    re.I,
)
_NEGATIVE_TERMS = (
    ("explicitly_unfunded", re.compile(r"\b(unfunded|not funded|no funding|without funding)\b", re.I)),
    ("explicitly_unpaid", re.compile(r"\b(unpaid|not paid|never paid|prize was not paid|reward was not paid)\b", re.I)),
    ("reward_withdrawn", re.compile(r"\b(reward|bounty|prize).{0,40}\b(withdrawn|cancelled|canceled|removed)\b", re.I | re.S)),
    ("opportunity_closed", re.compile(r"\b(closed bounty|already claimed|winner selected|award granted|expired bounty|no longer available)\b", re.I)),
    ("explicit_no_bounty", re.compile(r"\b(no bounty|not a bounty|no reward|not a paid task)\b", re.I)),
)
_MISLEADING_CONTEXT = re.compile(
    r"\b(msrp|retail price|phone costs?|product price|market cap|valuation|article|news release|publication list|worth\s+[$€£])\b",
    re.I,
)


def _github_issue_identity(item: Mapping[str, Any]) -> tuple[bool, str]:
    html_url = str(item.get("html_url") or item.get("url") or "")
    parsed = urlparse(html_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        return False, "source_is_not_github_issue"
    if len(parts) != 4 or parts[2] != "issues" or not parts[3].isdigit():
        return False, "source_is_not_canonical_issue_url"
    if item.get("pull_request"):
        return False, "source_is_pull_request_not_issue"

    repository_url = str(item.get("repository_url") or "")
    if repository_url:
        repo_parts = [part for part in urlparse(repository_url).path.split("/") if part]
        if len(repo_parts) >= 3 and repo_parts[-2:] != parts[:2]:
            return False, "repository_identity_mismatch"
    return True, html_url


def _reward_near_amount(text: str) -> tuple[float, str, str] | None:
    for match in _MONEY_RE.finditer(text):
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 120)
        context = text[start:end]
        if not _REWARD_TERMS.search(context):
            continue
        raw = (match.group(1) or match.group(2) or "0").replace(",", "")
        currency = (
            match.group(3)
            or ("USD" if "$" in match.group(0) else "EUR" if "€" in match.group(0) else "GBP")
        ).upper()
        try:
            amount = float(raw)
        except ValueError:
            continue
        if amount <= 0:
            continue
        return amount, currency, context.strip()[:240]
    return None


def assess_opportunity_authenticity(item: Mapping[str, Any]) -> OpportunityAuthenticity:
    """Verify that a public issue contains a credible, directly actionable reward.

    The decision is intentionally fail-closed. Uncertain opportunities remain
    discoverable but cannot enter autonomous execution ranking.
    """
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    text = f"{title}\n{body}"
    reasons: list[str] = []
    evidence: list[str] = []

    source_ok, source_evidence = _github_issue_identity(item)
    if not source_ok:
        reasons.append(source_evidence)
    else:
        evidence.append(source_evidence)

    state = str(item.get("state") or "open").casefold()
    if state != "open":
        reasons.append("issue_not_open")

    for reason, pattern in _NEGATIVE_TERMS:
        match = pattern.search(text)
        if match:
            reasons.append(reason)
            evidence.append(match.group(0).strip()[:160])

    if _MISLEADING_CONTEXT.search(text) and not _SUBMISSION_TERMS.search(text):
        reasons.append("money_appears_in_non_reward_context")

    reward = _reward_near_amount(text)
    amount = 0.0
    currency = "unknown"
    if reward is None:
        reasons.append("no_explicit_reward_amount_binding")
    else:
        amount, currency, reward_evidence = reward
        evidence.append(reward_evidence)

    submission = _SUBMISSION_TERMS.search(text)
    if not submission:
        reasons.append("no_official_submission_or_deliverable_path")
    else:
        evidence.append(submission.group(0).strip()[:160])

    rejected_reasons = {
        "explicitly_unfunded",
        "explicitly_unpaid",
        "reward_withdrawn",
        "opportunity_closed",
        "explicit_no_bounty",
        "money_appears_in_non_reward_context",
        "issue_not_open",
    }
    if rejected_reasons.intersection(reasons):
        status = "rejected_misleading_or_unfunded"
    elif reasons:
        status = "unverified_reward_claim"
    else:
        status = "verified_authoritative_reward"

    return OpportunityAuthenticity(
        status=status,
        verified=status == "verified_authoritative_reward",
        reward_amount=amount,
        currency=currency,
        reasons=tuple(dict.fromkeys(reasons)),
        evidence=tuple(dict.fromkeys(evidence)),
    )
