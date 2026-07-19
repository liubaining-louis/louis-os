"""Safe public web search and fetch helpers for Louis OS.

Only public HTTPS resources are allowed. Private, loopback, link-local and metadata
addresses are blocked to reduce SSRF risk. Responses are size and time limited.
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "Louis-OS-Web-Gateway/1.0"
MAX_BYTES = 600_000
TIMEOUT = 15


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def _public_https_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only public HTTPS URLs are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".internal"):
        raise ValueError("Blocked host")
    for info in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("Blocked non-public address")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def fetch_public_page(url: str) -> dict[str, Any]:
    safe_url = _public_https_url(url)
    req = urllib.request.Request(
        safe_url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        final_url = _public_https_url(response.geturl())
        content_type = response.headers.get_content_type()
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Response too large")
        charset = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")

    if content_type == "application/json":
        try:
            parsed = json.loads(text)
            clean = json.dumps(parsed, ensure_ascii=False)[:20000]
        except json.JSONDecodeError:
            clean = text[:20000]
    else:
        parser = _TextParser()
        parser.feed(text)
        clean = "\n".join(parser.parts)
        clean = re.sub(r"\n{3,}", "\n\n", clean)[:20000]

    return {
        "url": final_url,
        "content_type": content_type,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": clean,
    }


def search_web(query: str, limit: int = 5) -> list[dict[str, str]]:
    query = query.strip()[:500]
    if not query:
        return []
    limit = max(1, min(limit, 8))
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES)
    page = raw.decode("utf-8", errors="replace")

    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    results: list[dict[str, str]] = []
    for href, title_html in pattern.findall(page):
        title = re.sub(r"<[^>]+>", "", title_html)
        title = html.unescape(" ".join(title.split()))
        target = html.unescape(href)
        parsed = urllib.parse.urlparse(target)
        if parsed.netloc.endswith("duckduckgo.com"):
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("uddg", [target])[0]
        try:
            target = _public_https_url(target)
        except Exception:
            continue
        results.append({"title": title, "url": target})
        if len(results) >= limit:
            break
    return results


def research(query: str, limit: int = 5, fetch_top: int = 3) -> dict[str, Any]:
    results = search_web(query, limit=limit)
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in results[: max(0, min(fetch_top, 3))]:
        try:
            page = fetch_public_page(item["url"])
            pages.append({"title": item["title"], **page})
        except Exception as exc:
            errors.append(f"{item['url']}: {type(exc).__name__}: {exc}")
    return {
        "query": query,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "pages": pages,
        "errors": errors,
    }
