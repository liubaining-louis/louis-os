"""Fail-closed adapters for authoritative payable-opportunity evidence.

Issue text is never payment proof. Evidence must come from a recognized provider bot
or from a repository maintainer comment that links to an allowlisted payment platform,
contains an objective amount and explicitly describes a bounty/reward/claim.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

_MONEY_RE = re.compile(
    r"(?:([$€£])\s*([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(USD|EUR|GBP))",
    re.I,
)
_PROVIDER_URL_RE = re.compile(
    r"https://(?:www\.)?(algora\.io|opire\.dev|gitcoin\.co|polar\.sh|bountysource\.com)/[^\s)]+",
    re.I,
)
_PROVIDER_TERMS_RE = re.compile(r"\b(bounty|reward|claim|payout|payment)\b", re.I)
_STRUCK_RE = re.compile(r"~~\s*##\s*💎|bounty (?:is )?(?:cancelled|canceled|withdrawn|closed)", re.I)
_MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


@dataclass(frozen=True)
class PaymentEvidence:
    provider: str
    reward_amount: float
    currency: str
    evidence_type: str
    evidence_url: str
    provider_url: str
    evidence_author: str
    evidence_excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _money(text: str) -> tuple[float, str] | None:
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    raw = (match.group(2) or match.group(3) or "0").replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None
    if amount <= 0:
        return None
    currency = (match.group(4) or {"$": "USD", "€": "EUR", "£": "GBP"}.get(match.group(1) or "", "unknown")).upper()
    return amount, currency


def _provider_from_domain(domain: str) -> str:
    normalized = domain.casefold()
    return {
        "algora.io": "algora",
        "opire.dev": "opire",
        "gitcoin.co": "gitcoin",
        "polar.sh": "polar",
        "bountysource.com": "bountysource",
    }[normalized]


def detect_payment_evidence(comments: Sequence[Mapping[str, Any]]) -> PaymentEvidence | None:
    """Return the first authoritative payment signal, otherwise ``None``."""
    for comment in comments:
        user = comment.get("user") if isinstance(comment.get("user"), Mapping) else {}
        login = str(user.get("login") or "").casefold()
        normalized = login.removesuffix("[bot]")
        body = str(comment.get("body") or "")
        if not body or _STRUCK_RE.search(body):
            continue
        amount = _money(body)
        if amount is None:
            continue
        reward_amount, currency = amount
        evidence_url = str(comment.get("html_url") or "")
        excerpt = re.sub(r"\s+", " ", body).strip()[:360]

        if normalized == "algora-pbc" and "💎" in body and "/attempt" in body and "/claim" in body:
            return PaymentEvidence(
                provider="algora",
                reward_amount=reward_amount,
                currency=currency,
                evidence_type="recognized_provider_bot",
                evidence_url=evidence_url,
                provider_url="https://algora.io/",
                evidence_author=login,
                evidence_excerpt=excerpt,
            )
        if "opire" in normalized and _PROVIDER_TERMS_RE.search(body) and re.search(r"\bclaim\b", body, re.I):
            return PaymentEvidence(
                provider="opire",
                reward_amount=reward_amount,
                currency=currency,
                evidence_type="recognized_provider_bot",
                evidence_url=evidence_url,
                provider_url="https://opire.dev/",
                evidence_author=login,
                evidence_excerpt=excerpt,
            )

        association = str(comment.get("author_association") or "").upper()
        platform = _PROVIDER_URL_RE.search(body)
        if association not in _MAINTAINER_ASSOCIATIONS or not platform or not _PROVIDER_TERMS_RE.search(body):
            continue
        provider_url = platform.group(0).rstrip(".,")
        return PaymentEvidence(
            provider=_provider_from_domain(platform.group(1)),
            reward_amount=reward_amount,
            currency=currency,
            evidence_type="maintainer_attested_platform_link",
            evidence_url=evidence_url,
            provider_url=provider_url,
            evidence_author=login,
            evidence_excerpt=excerpt,
        )
    return None


def compatibility_comment(evidence: PaymentEvidence, issue_number: int) -> dict[str, Any]:
    """Create an internal compatibility payload for the legacy qualifier.

    The returned record is never persisted as external evidence; candidate fields are
    overwritten with the original adapter evidence immediately after qualification.
    """
    return {
        "html_url": evidence.evidence_url,
        "user": {"login": "algora-pbc[bot]"},
        "body": (
            f"## 💎 ${evidence.reward_amount:g} bounty\n"
            f"Comment `/attempt #{issue_number}` and include `/claim #{issue_number}` in the PR. "
            "Receive payment after acceptance."
        ),
    }
