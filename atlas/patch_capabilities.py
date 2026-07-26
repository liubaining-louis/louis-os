"""Deterministic patch capabilities used by both scouting and construction."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

CAPABILITY_QUERIES = (
    'is:issue is:open (bounty OR reward) ("replace" OR "change") (README OR docs) archived:false',
    'is:issue is:open (bounty OR reward) "broken link" (README OR documentation) archived:false',
    'is:issue is:open (bounty OR reward) ("expected value" OR "failing test") archived:false',
    'is:issue is:open (bounty OR reward) (config OR configuration) (JSON OR TOML) archived:false',
    'is:issue is:open commenter:algora-pbc (typo OR "broken link" OR configuration OR test) archived:false',
    'is:issue is:open in:comments "/claim #" (typo OR "broken link" OR configuration OR test) archived:false',
)

_FILE_RE = re.compile(
    r"(?:\bfile\b|\bin\b|\bpath\b)\s*[:：]?\s*[`'\"]?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]+)[`'\"]?",
    re.I,
)
_QUOTED_REPLACEMENT_RE = re.compile(
    r"(?:replace|change|fix|rename|update)\s*[`'\"]([^`'\"\n]{1,300})[`'\"]\s*(?:with|to)\s*[`'\"]([^`'\"\n]{1,300})[`'\"]",
    re.I,
)
_URL_REPLACEMENT_RE = re.compile(
    r"(?:replace|update|change|fix).{0,80}[`'\"]?(https?://[^\s`'\"]+)[`'\"]?.{0,80}(?:with|to)\s*[`'\"]?(https?://[^\s`'\"]+)[`'\"]?",
    re.I | re.S,
)
_CONFIG_RE = re.compile(
    r"(?:set|update|change)\s+(?:the\s+)?(?:key\s+)?[`'\"]?([A-Za-z0-9_.-]+)[`'\"]?\s+(?:from\s+)?[`'\"]([^`'\"\n]{1,160})[`'\"]\s+to\s+[`'\"]([^`'\"\n]{1,160})[`'\"]",
    re.I,
)
_TEST_TERMS_RE = re.compile(r"\b(test|tests|pytest|unittest|assert|expected value|failing test)\b", re.I)
_DOC_TERMS_RE = re.compile(r"\b(README|docs?|documentation|markdown|broken link)\b", re.I)
_CONFIG_EXTENSIONS = (".json", ".toml")
_TEST_PATH_RE = re.compile(r"(?:^|/)(?:tests?|test_[^/]+|[^/]+_test)\.(?:py|js|ts|tsx|jsx)$", re.I)


@dataclass(frozen=True)
class PatchCapabilityMatch:
    capability_id: str
    target_path: str
    old_value: str
    new_value: str
    validation_kind: str
    match_evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _file_path(text: str) -> str | None:
    match = _FILE_RE.search(text)
    return match.group(1) if match else None


def classify_patch_capability(issue: Mapping[str, Any]) -> PatchCapabilityMatch | None:
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
    path = _file_path(text)
    if not path:
        return None

    config = _CONFIG_RE.search(text)
    if config and path.casefold().endswith(_CONFIG_EXTENSIONS):
        key, old, new = config.groups()
        if old != new:
            return PatchCapabilityMatch(
                capability_id="configuration_scalar_replacement",
                target_path=path,
                old_value=old,
                new_value=new,
                validation_kind="config_syntax_and_single_replacement",
                match_evidence=f"key={key}; {old!r} -> {new!r}",
            )

    urls = _URL_REPLACEMENT_RE.search(text)
    if urls and (_DOC_TERMS_RE.search(text) or path.casefold().endswith((".md", ".rst", ".txt"))):
        old, new = urls.groups()
        if old != new:
            return PatchCapabilityMatch(
                capability_id="broken_link_replacement",
                target_path=path,
                old_value=old.rstrip(".,)"),
                new_value=new.rstrip(".,)"),
                validation_kind="url_and_single_replacement",
                match_evidence=f"{old!r} -> {new!r}",
            )

    replacement = _QUOTED_REPLACEMENT_RE.search(text)
    if not replacement:
        return None
    old, new = replacement.groups()
    if old == new:
        return None

    if _TEST_PATH_RE.search(path) or _TEST_TERMS_RE.search(text):
        return PatchCapabilityMatch(
            capability_id="simple_test_expectation_replacement",
            target_path=path,
            old_value=old,
            new_value=new,
            validation_kind="test_syntax_and_single_replacement",
            match_evidence=f"{old!r} -> {new!r}",
        )

    return PatchCapabilityMatch(
        capability_id="deterministic_text_replacement",
        target_path=path,
        old_value=old,
        new_value=new,
        validation_kind="single_replacement",
        match_evidence=f"{old!r} -> {new!r}",
    )


SUPPORTED_CAPABILITY_IDS = frozenset(
    {
        "deterministic_text_replacement",
        "broken_link_replacement",
        "simple_test_expectation_replacement",
        "configuration_scalar_replacement",
    }
)
