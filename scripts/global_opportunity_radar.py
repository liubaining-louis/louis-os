#!/usr/bin/env python3
"""Worldwide open-web opportunity discovery for Louis OS.

This is a DISCOVERY layer, not an execution authority. It intentionally searches much
more broadly than the existing GitHub-only scout, but it never treats a web mention as
payment proof and never performs applications, claims, account creation, KYC, spending,
or submissions.

Sources are deliberately heterogeneous:
- global GitHub issue search with multilingual paid-work queries;
- Hacker News Algolia search for recent freelance/bounty/contract posts;
- public marketplace / bounty / OSS-funding seed pages;
- a directory-of-directories pass (OSS.Fund) used to discover additional domains;
- bounded one-hop link expansion from relevant public pages.

Every hit is normalized into a common discovery record, deduplicated, safety-filtered,
and ranked for later authoritative verification by Louis OS's existing gates.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
OUT = RESULTS / "global_opportunity_radar.json"

UA = "Louis-OS-Global-Opportunity-Radar/1.0 (+public opportunity discovery; bounded requests)"
MAX_BYTES = 1_500_000
MAX_DISCOVERED_DOMAINS = 80
MAX_EXPANDED_PAGES = 45
MAX_RECORDS = 120

# Directly relevant sources plus broad global freelance/job surfaces. Account-bound sites
# are discovery-only and will be marked as human-gated later.
SEED_URLS = [
    "https://www.task-bounty.com/for-agents",
    "https://agentbounties.app/",
    "https://www.oss.fund/directory/",
    "https://algora.io/bounties",
    "https://opire.dev/",
    "https://gitcoin.co/",
    "https://bepro.network/",
    "https://issuehunt.io/",
    "https://gitpay.me/",
    "https://hackenproof.com/programs",
    "https://hackerone.com/bug-bounty-programs",
    "https://bugcrowd.com/engagements/",
    "https://www.freelancer.com/jobs/",
    "https://www.peopleperhour.com/freelance-jobs",
    "https://www.guru.com/d/jobs/",
    "https://www.workana.com/jobs",
    "https://contra.com/opportunities",
    "https://www.codementor.io/freelance-jobs",
    "https://remoteok.com/remote-freelance-jobs",
    "https://weworkremotely.com/categories/remote-programming-jobs",
    "https://www.malt.fr/projects",
    "https://www.twago.com/",
    "https://www.truelancer.com/freelance-jobs",
    "https://www.lancers.jp/work/search",
    "https://crowdworks.jp/public/jobs",
    "https://www.zbj.com/",
]

GITHUB_QUERIES = [
    'is:issue is:open (bounty OR reward OR paid OR stipend) archived:false',
    'is:issue is:open ("good first issue" OR beginner) (bounty OR reward) archived:false',
    'is:issue is:open (documentation OR python OR javascript OR typescript OR api) (bounty OR reward OR paid) archived:false',
    'is:issue is:open (prime OR recompensa OR remunerado OR pago) archived:false',
    'is:issue is:open (récompense OR rémunéré OR payé OR prime) archived:false',
    'is:issue is:open (belohnung OR bezahlt OR prämie) archived:false',
    'is:issue is:open (報酬 OR 有償 OR 懸賞) archived:false',
    'is:issue is:open (赏金 OR 有偿 OR 报酬) archived:false',
]

HN_QUERIES = [
    "paid bounty", "freelance developer", "contract developer", "microtask",
    "paid open source", "bug bounty", "research bounty", "AI agent bounty",
]

OPPORTUNITY_TERMS = (
    "bounty", "reward", "paid", "payout", "freelance", "contract", "gig", "microtask",
    "commission", "prize", "stipend", "grant", "earn", "usdc", "usd", "eur", "btc", "eth",
    "récompense", "rémunéré", "payé", "mission", "prime", "recompensa", "remunerado", "pago",
    "belohnung", "bezahlt", "prämie", "報酬", "有償", "懸賞", "赏金", "有偿", "报酬",
)

AGENT_FRIENDLY_TERMS = (
    "for agents", "ai agent", "agent operator", "api", "cli", "github issue", "pull request",
    "open source", "programmatic", "mcp", "x402", "usdc", "crypto", "sandbox", "automated test",
)

HUMAN_GATE_TERMS = (
    "kyc", "identity verification", "verify identity", "passport", "government id", "background check",
    "phone verification", "video interview", "in-person", "onsite", "physical delivery", "accept terms",
    "freelancer profile", "seller profile", "connect stripe", "tax form",
)

UNSAFE_TERMS = (
    "fake review", "buy reviews", "account takeover", "credential stuffing", "phishing", "spam campaign",
    "social media manipulation", "mass dm", "referral fraud", "self referral", "captcha bypass", "bypass kyc",
    "malware", "ransomware", "steal credentials", "doxx", "weapon", "firearm", "drug trafficking",
)

MONEY_RE = re.compile(
    r"(?:(?:US\$|CA\$|AU\$|[$€£¥])\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|USDC|EUR|GBP|ETH|BTC|JPY|CNY|RMB))",
    re.I,
)
LINK_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.I | re.S)
WS_RE = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_get(url: str, *, timeout: int = 18, accept: str = "text/html,application/json;q=0.9,*/*;q=0.5") -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        ctype = response.headers.get("Content-Type", "")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            data = data[:MAX_BYTES]
        return data, ctype


def decode(data: bytes, ctype: str = "") -> str:
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    if m:
        charset = m.group(1)
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    raw = SCRIPT_RE.sub(" ", raw)
    raw = TAG_RE.sub(" ", raw)
    return WS_RE.sub(" ", html.unescape(raw)).strip()


def normalized_url(base: str, href: str) -> str | None:
    try:
        url = urllib.parse.urljoin(base, html.unescape(href.strip()))
        p = urllib.parse.urlsplit(url)
    except Exception:
        return None
    if p.scheme not in {"http", "https"} or not p.netloc:
        return None
    if any(p.path.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".zip", ".pdf")):
        return None
    # Remove common tracking parameters while preserving useful query parameters.
    qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    qs = [(k, v) for k, v in qs if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source"}]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", urllib.parse.urlencode(qs), ""))


def domain(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def stable_id(url: str, title: str = "") -> str:
    return hashlib.sha256((url + "\n" + title).encode()).hexdigest()[:18]


def contains_any(text: str, terms: Iterable[str]) -> bool:
    low = text.casefold()
    return any(term.casefold() in low for term in terms)


def score_record(title: str, text: str, source_kind: str) -> tuple[float, list[str], bool, bool]:
    blob = f"{title} {text}"[:12000]
    low = blob.casefold()
    reasons: list[str] = []
    score = 15.0
    money = bool(MONEY_RE.search(blob))
    if money:
        score += 24
        reasons.append("explicit_money_signal")
    paid_terms = sum(1 for t in OPPORTUNITY_TERMS if t.casefold() in low)
    score += min(20, paid_terms * 3)
    if paid_terms:
        reasons.append("paid_work_language")
    agent_terms = sum(1 for t in AGENT_FRIENDLY_TERMS if t in low)
    score += min(24, agent_terms * 4)
    if agent_terms:
        reasons.append("agent_or_programmatic_fit")
    human_gate = contains_any(blob, HUMAN_GATE_TERMS)
    if human_gate:
        score -= 18
        reasons.append("possible_human_gate")
    unsafe = contains_any(blob, UNSAFE_TERMS)
    if unsafe:
        score = 0
        reasons.append("unsafe_or_disallowed_signal")
    if source_kind in {"github", "bounty_platform", "oss_directory", "agent_marketplace"}:
        score += 8
    if any(t in low for t in ("documentation", "data", "research", "translation", "python", "javascript", "typescript", "api", "automation", "spreadsheet", "csv", "json")):
        score += 8
        reasons.append("louis_capability_match")
    return round(max(0.0, min(100.0, score)), 1), reasons, human_gate, unsafe


def classify_source(url: str) -> str:
    d = domain(url)
    if d in {"task-bounty.com", "agentbounties.app", "moltjobs.io", "taskmarket.dev", "clawlancer.ai"}:
        return "agent_marketplace"
    if d in {"algora.io", "opire.dev", "gitcoin.co", "bepro.network", "issuehunt.io", "gitpay.me", "hackenproof.com", "hackerone.com", "bugcrowd.com"}:
        return "bounty_platform"
    if d == "oss.fund":
        return "oss_directory"
    if d == "github.com":
        return "github"
    return "open_web"


def add_record(records: dict[str, dict[str, Any]], *, url: str, title: str, text: str, source: str, discovered_via: str, updated_at: str | None = None) -> None:
    title = WS_RE.sub(" ", title).strip()[:300]
    text = WS_RE.sub(" ", text).strip()[:5000]
    if not title:
        title = text[:140] or url
    if not contains_any(f"{title} {text}", OPPORTUNITY_TERMS) and not MONEY_RE.search(f"{title} {text}"):
        return
    source_kind = classify_source(url) if source == "open_web" else source
    score, reasons, human_gate, unsafe = score_record(title, text, source_kind)
    if unsafe or score < 22:
        return
    key = normalized_url(url, url) or url
    candidate = {
        "id": stable_id(key, title),
        "title": title,
        "url": key,
        "domain": domain(key),
        "source_kind": source_kind,
        "discovered_via": discovered_via,
        "updated_at": updated_at,
        "discovery_score": score,
        "money_signal": MONEY_RE.search(f"{title} {text}").group(0) if MONEY_RE.search(f"{title} {text}") else None,
        "possible_human_gate": human_gate,
        "requires_authoritative_payment_verification": True,
        "execution_authorized": False,
        "reasons": reasons,
        "excerpt": text[:900],
    }
    old = records.get(key)
    if old is None or candidate["discovery_score"] > old.get("discovery_score", 0):
        records[key] = candidate


def github_search(records: dict[str, dict[str, Any]], errors: list[str]) -> int:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    inspected = 0
    for query in GITHUB_QUERIES:
        url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": 30})
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.load(r)
        except Exception as exc:
            errors.append(f"github:{query}:{type(exc).__name__}:{exc}")
            continue
        for item in payload.get("items", []):
            inspected += 1
            add_record(
                records,
                url=str(item.get("html_url") or ""),
                title=str(item.get("title") or ""),
                text=str(item.get("body") or ""),
                source="github",
                discovered_via=f"github_query:{query}",
                updated_at=item.get("updated_at"),
            )
    return inspected


def hn_search(records: dict[str, dict[str, Any]], errors: list[str]) -> int:
    inspected = 0
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp())
    for q in HN_QUERIES:
        url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({"query": q, "tags": "story", "numericFilters": f"created_at_i>{cutoff}", "hitsPerPage": 40})
        try:
            data, ctype = safe_get(url, accept="application/json")
            payload = json.loads(decode(data, ctype))
        except Exception as exc:
            errors.append(f"hn:{q}:{type(exc).__name__}:{exc}")
            continue
        for hit in payload.get("hits", []):
            inspected += 1
            target = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            text = " ".join(str(hit.get(k) or "") for k in ("story_text", "comment_text", "title"))
            add_record(records, url=str(target), title=str(hit.get("title") or q), text=text, source="open_web", discovered_via=f"hn_algolia:{q}", updated_at=hit.get("created_at"))
    return inspected


def crawl_page(url: str, records: dict[str, dict[str, Any]], errors: list[str], *, via: str) -> tuple[list[str], str]:
    try:
        data, ctype = safe_get(url)
        raw = decode(data, ctype)
    except Exception as exc:
        errors.append(f"crawl:{url}:{type(exc).__name__}:{exc}")
        return [], ""
    text = clean_text(raw)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    title = clean_text(title_match.group(1)) if title_match else domain(url)
    add_record(records, url=url, title=title, text=text, source="open_web", discovered_via=via)
    links: list[str] = []
    for href in LINK_RE.findall(raw):
        u = normalized_url(url, href)
        if not u:
            continue
        anchor_context = href.casefold()
        if contains_any(anchor_context, OPPORTUNITY_TERMS) or domain(u) != domain(url):
            links.append(u)
    return list(dict.fromkeys(links)), text


def web_discovery(records: dict[str, dict[str, Any]], errors: list[str]) -> tuple[int, int]:
    inspected = 0
    discovered_domains: list[str] = []
    expansion_queue: list[str] = []
    for seed in SEED_URLS:
        links, _ = crawl_page(seed, records, errors, via="seed")
        inspected += 1
        for u in links:
            d = domain(u)
            if d and d not in discovered_domains and d not in {domain(seed)}:
                discovered_domains.append(d)
                if len(discovered_domains) <= MAX_DISCOVERED_DOMAINS:
                    expansion_queue.append(u)

    # Bounded one-hop expansion. Prefer links whose URL itself suggests paid work.
    expansion_queue.sort(key=lambda u: (not contains_any(u, OPPORTUNITY_TERMS), len(u)))
    seen: set[str] = set(SEED_URLS)
    expanded = 0
    for u in expansion_queue:
        if expanded >= MAX_EXPANDED_PAGES:
            break
        if u in seen:
            continue
        seen.add(u)
        crawl_page(u, records, errors, via="directory_or_seed_expansion")
        inspected += 1
        expanded += 1
        time.sleep(0.05)
    return inspected, len(discovered_domains)


def fingerprint(records: list[dict[str, Any]]) -> str:
    material = [
        (r.get("url"), r.get("title"), r.get("discovery_score"), r.get("money_signal"), r.get("possible_human_gate"))
        for r in records[:80]
    ]
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main() -> int:
    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    inspected = 0

    inspected += github_search(records, errors)
    inspected += hn_search(records, errors)
    web_count, domain_count = web_discovery(records, errors)
    inspected += web_count

    ranked = sorted(records.values(), key=lambda r: (-float(r.get("discovery_score", 0)), bool(r.get("possible_human_gate")), r.get("domain", ""), r.get("title", "")))[:MAX_RECORDS]
    fp = fingerprint(ranked)
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    payload = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "mode": "worldwide_open_web_discovery_only",
        "inspected_items_or_pages": inspected,
        "domains_discovered_from_web_graph": domain_count,
        "candidate_count": len(ranked),
        "candidate_fingerprint": fp,
        "meaningful_change": previous.get("candidate_fingerprint") != fp,
        "execution_policy": {
            "web_hit_is_payment_proof": False,
            "auto_apply_from_discovery_layer": False,
            "auto_spend": False,
            "auto_kyc": False,
            "next_gate": "authoritative payment + live status + agent eligibility + submission-path verification",
        },
        "source_families": ["github_global_multilingual", "hackernews_algolia", "bounty_and_agent_marketplaces", "oss_directory_expansion", "global_freelance_surfaces", "bounded_open_web_link_expansion"],
        "candidates": ranked,
        "errors": errors[:80],
    }

    # Avoid timestamp-only repo churn: only persist a new file when the frontier changed.
    if payload["meaningful_change"] or not OUT.exists():
        OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print(json.dumps({"status": "no_meaningful_frontier_change", "candidate_count": len(ranked), "inspected": inspected, "domains": domain_count, "errors": len(errors)}, ensure_ascii=False))
        return 0

    print(json.dumps({"status": "frontier_updated", "candidate_count": len(ranked), "inspected": inspected, "domains": domain_count, "top": ranked[:8], "errors": len(errors)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
