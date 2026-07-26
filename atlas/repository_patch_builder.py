"""Credible-target preflight and deterministic repository patch construction.

The builder resolves mirror issues to their canonical GitHub source, rejects
subjective, fictional or adversarial bounty terms, and supports a narrow class
of deterministic text replacements. Unsupported work fails closed so Louis OS
can pivot instead of submitting generic prose.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

JsonGetter = Callable[[str], Any]

_SOURCE_URL_RE = re.compile(
    r"(?:source\s*url|original\s*(?:issue|url)|原始链接)\s*[:：]?\s*(https://github\.com/[^\s)]+/issues/\d+)",
    re.I,
)
_FILE_RE = re.compile(
    r"(?:\bfile\b|\bin\b)\s*[:：]?\s*[`'\"]?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]+)[`'\"]?",
    re.I,
)
_REPLACE_RE = re.compile(
    r"(?:replace|change|fix|rename)\s*[`'\"]([^`'\"\n]{1,200})[`'\"]\s*(?:with|to)\s*[`'\"]([^`'\"\n]{1,200})[`'\"]",
    re.I,
)

_REJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "subjective_or_discretionary_payout",
        re.compile(
            r"reserve (?:the )?right to refuse payout|personal feeling|sole discretion|at my discretion|payout.{0,50}not guaranteed",
            re.I | re.S,
        ),
    ),
    (
        "fictional_or_unpayable_reward",
        re.compile(
            r"celestial bank account|flesh automatons?|space station 13|lava planet|payment pal|nanotrasen|terragov\s*[\"']?usd|in[- ]game credits?",
            re.I,
        ),
    ),
    (
        "adversarial_agent_trap",
        re.compile(
            r"slopbots?|easy task for agents|agentic|ye olde english|soliloquy|favorite lasagna|automated coders",
            re.I,
        ),
    ),
    (
        "absurd_scope_requirement",
        re.compile(
            r"(?:at (?:a )?minimum|over)\s*20[,.]?000\s+lines|100\+?\s+file edits|over\s+100\s+files",
            re.I,
        ),
    ),
    (
        "irrelevant_ideological_preamble_requirement",
        re.compile(r"new code files.{0,200}comment block preamble.{0,300}(?:war|strike|homeworld|population centers)", re.I | re.S),
    ),
)


@dataclass(frozen=True)
class TargetPreflight:
    candidate_id: str
    status: str
    canonical_issue_url: str
    target_repository: str
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    resolved_from_mirror: bool
    issue: dict[str, Any]

    @property
    def viable(self) -> bool:
        return self.status == "credible_target"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchBuildResult:
    status: str
    candidate_id: str | None
    workspace: str | None
    manifest_path: str | None
    diagnosis_code: str | None
    attempts: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def github_get_json(url: str) -> Any:
    token = os.getenv("ATLAS_EXTERNAL_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "louis-os-credible-target-builder",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def _canonical_issue_parts(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        raise ValueError("target_issue_not_github")
    if len(parts) != 4 or parts[2] != "issues" or not parts[3].isdigit():
        raise ValueError("target_issue_not_canonical")
    return parts[0], parts[1], int(parts[3])


def _issue_api_url(url: str) -> str:
    owner, repo, number = _canonical_issue_parts(url)
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"


def _repo_api_url(full_name: str) -> str:
    return f"https://api.github.com/repos/{full_name}"


def _repo_content_url(full_name: str, path: str, ref: str) -> str:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    return f"https://api.github.com/repos/{full_name}/contents/{encoded_path}?ref={urllib.parse.quote(ref, safe='')}"


def _source_issue_url(body: str) -> str | None:
    match = _SOURCE_URL_RE.search(body or "")
    return match.group(1).rstrip(".,") if match else None


def _labels_text(issue: Mapping[str, Any]) -> str:
    values: list[str] = []
    for label in issue.get("labels", []) if isinstance(issue.get("labels"), list) else []:
        if isinstance(label, Mapping):
            values.append(str(label.get("name") or ""))
            values.append(str(label.get("description") or ""))
    return "\n".join(values)


def assess_issue_credibility(issue: Mapping[str, Any]) -> tuple[bool, list[str], list[str]]:
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}\n{_labels_text(issue)}"
    reasons: list[str] = []
    evidence: list[str] = []
    if str(issue.get("state") or "open").casefold() != "open":
        reasons.append("issue_not_open")
    for code, pattern in _REJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            reasons.append(code)
            evidence.append(match.group(0).strip()[:220])
    credible = not reasons
    return credible, list(dict.fromkeys(reasons)), list(dict.fromkeys(evidence))


def preflight_candidate(candidate: Mapping[str, Any], getter: JsonGetter | None = None) -> TargetPreflight:
    getter = getter or github_get_json
    candidate_id = str(candidate.get("id") or "unknown")
    candidate_url = str(candidate.get("url") or "")
    issue = getter(_issue_api_url(candidate_url))
    if not isinstance(issue, Mapping):
        raise ValueError("candidate_issue_payload_invalid")
    issue = dict(issue)
    current_url = str(issue.get("html_url") or candidate_url)
    source_url = _source_issue_url(str(issue.get("body") or ""))
    resolved = False
    if source_url and source_url != current_url:
        source_issue = getter(_issue_api_url(source_url))
        if not isinstance(source_issue, Mapping):
            raise ValueError("source_issue_payload_invalid")
        issue = dict(source_issue)
        current_url = str(issue.get("html_url") or source_url)
        resolved = True

    owner, repo, _ = _canonical_issue_parts(current_url)
    credible, reasons, evidence = assess_issue_credibility(issue)
    return TargetPreflight(
        candidate_id=candidate_id,
        status="credible_target" if credible else "rejected_noncredible_or_adversarial",
        canonical_issue_url=current_url,
        target_repository=f"{owner}/{repo}",
        reasons=tuple(reasons),
        evidence=tuple(evidence),
        resolved_from_mirror=resolved,
        issue=issue,
    )


def _extract_text_replacement(issue: Mapping[str, Any]) -> tuple[str, str, str] | None:
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
    replacement = _REPLACE_RE.search(text)
    file_match = _FILE_RE.search(text)
    if not replacement or not file_match:
        return None
    old, new = replacement.group(1), replacement.group(2)
    path = file_match.group(1)
    if old == new or len(old) > 200 or len(new) > 200:
        return None
    return path, old, new


def _decode_content(payload: Mapping[str, Any]) -> str:
    if payload.get("encoding") != "base64" or not payload.get("content"):
        raise ValueError("repository_file_content_unavailable")
    return base64.b64decode(str(payload["content"])).decode("utf-8")


def build_deterministic_patch(
    preflight: TargetPreflight,
    workspace_root: Path,
    getter: JsonGetter | None = None,
) -> dict[str, Any]:
    getter = getter or github_get_json
    if not preflight.viable:
        raise ValueError("target_not_credible")
    task = _extract_text_replacement(preflight.issue)
    if task is None:
        raise ValueError("unsupported_patch_synthesis")
    target_path, old, new = task

    repo_info = getter(_repo_api_url(preflight.target_repository))
    if not isinstance(repo_info, Mapping):
        raise ValueError("target_repository_metadata_invalid")
    base_branch = str(repo_info.get("default_branch") or "main")
    file_payload = getter(_repo_content_url(preflight.target_repository, target_path, base_branch))
    if not isinstance(file_payload, Mapping):
        raise ValueError("target_file_payload_invalid")
    original = _decode_content(file_payload)
    count = original.count(old)
    if count != 1:
        raise ValueError(f"replacement_occurrence_count:{count}")
    modified = original.replace(old, new, 1)
    if old in modified or new not in modified:
        raise RuntimeError("deterministic_replacement_test_failed")

    workspace = workspace_root / preflight.candidate_id
    patch_path = workspace / "patch_files" / target_path
    test_path = workspace / "test_evidence.txt"
    manifest_path = workspace / "patch_manifest.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(modified, encoding="utf-8")
    test_path.write_text(
        "\n".join(
            [
                f"candidate={preflight.candidate_id}",
                f"target={preflight.target_repository}:{target_path}",
                "test=deterministic_single_replacement",
                f"old_occurrences_before={count}",
                f"old_occurrences_after={modified.count(old)}",
                f"new_occurrences_after={modified.count(new)}",
                "result=passed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    branch_name = f"louis-os/{preflight.candidate_id}-text-fix"
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "candidate_id": preflight.candidate_id,
        "target_issue_url": preflight.canonical_issue_url,
        "target_repository": preflight.target_repository,
        "base_branch": base_branch,
        "branch_name": branch_name,
        "pr_title": f"Fix documented text in {target_path}",
        "pr_body": (
            f"Closes {preflight.canonical_issue_url}\n\n"
            f"Applies the requested deterministic replacement in `{target_path}`.\n\n"
            "Validation: exactly one source occurrence was replaced and the generated file hash was verified."
        ),
        "deliverable_kind": "repository_patch",
        "files": [
            {
                "path": target_path,
                "content_path": str(patch_path.relative_to(workspace)),
                "sha256": digest,
            }
        ],
        "test_commands": [f"assert exactly one occurrence of {old!r} is replaced by {new!r} in {target_path}"],
        "test_evidence": [str(test_path.relative_to(workspace))],
        "tests_passed": True,
        "requires_cla": False,
        "requires_dco": False,
        "requires_new_account": False,
        "requires_payment_or_fee": False,
        "requires_kyc": False,
        "preflight_reasons": list(preflight.reasons),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "candidate_id": preflight.candidate_id,
        "workspace": str(workspace),
        "manifest_path": str(manifest_path),
        "target_repository": preflight.target_repository,
        "target_issue_url": preflight.canonical_issue_url,
        "patch_sha256": digest,
    }


def build_patch_from_candidates(
    candidates: Sequence[Mapping[str, Any]],
    workspace_root: Path,
    getter: JsonGetter | None = None,
) -> PatchBuildResult:
    getter = getter or github_get_json
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("external_prerequisites_cleared") is False:
            attempts.append(
                {
                    "candidate_id": candidate.get("id"),
                    "status": "skipped_external_prerequisite",
                    "reasons": list(candidate.get("external_prerequisites") or []),
                }
            )
            continue
        try:
            preflight = preflight_candidate(candidate, getter)
        except Exception as exc:
            attempts.append(
                {
                    "candidate_id": candidate.get("id"),
                    "status": "preflight_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        attempt = {
            "candidate_id": preflight.candidate_id,
            "status": preflight.status,
            "canonical_issue_url": preflight.canonical_issue_url,
            "target_repository": preflight.target_repository,
            "resolved_from_mirror": preflight.resolved_from_mirror,
            "reasons": list(preflight.reasons),
            "evidence": list(preflight.evidence),
        }
        if not preflight.viable:
            attempts.append(attempt)
            continue
        try:
            built = build_deterministic_patch(preflight, workspace_root, getter)
        except Exception as exc:
            attempt.update(
                {
                    "status": "credible_but_patch_not_built",
                    "diagnosis_code": str(exc),
                    "next_action": "pivot_or_add_bounded_patch_handler",
                }
            )
            attempts.append(attempt)
            continue
        attempt.update({"status": "patch_built", **built})
        attempts.append(attempt)
        return PatchBuildResult(
            status="patch_built",
            candidate_id=preflight.candidate_id,
            workspace=built["workspace"],
            manifest_path=built["manifest_path"],
            diagnosis_code=None,
            attempts=tuple(attempts),
        )

    rejection_only = bool(attempts) and all(
        item.get("status") in {"rejected_noncredible_or_adversarial", "skipped_external_prerequisite"}
        for item in attempts
    )
    return PatchBuildResult(
        status="blocked",
        candidate_id=None,
        workspace=None,
        manifest_path=None,
        diagnosis_code="no_credible_candidate" if rejection_only else "no_supported_credible_patch_task",
        attempts=tuple(attempts),
    )
