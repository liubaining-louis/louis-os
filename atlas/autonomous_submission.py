"""Evidence-gated autonomous GitHub pull-request submission.

The executor can use an existing authorized GitHub identity, create or reuse a
fork, create an isolated branch, upload a tested patch and open a pull request.
It fails closed for generic drafts, missing tests, legal attestations, account
creation, payment, KYC or unverifiable evidence.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from atlas.external_github_auth import external_github_token


@dataclass(frozen=True)
class SubmissionDiagnosis:
    status: str
    blocked_stage: str
    direct_cause: str
    root_cause: str
    resolution_class: str
    next_action: str
    human_intervention_minimal: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubmissionReceipt:
    status: str
    candidate_id: str
    target_repository: str
    target_issue_url: str
    authorization_mode: str
    repository_mode: str
    source_repository: str
    source_branch: str
    pull_request_url: str
    pull_request_number: int
    commit_receipts: tuple[dict[str, Any], ...]
    created_at: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_issue(value: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        raise ValueError("target_issue_not_github")
    if len(parts) != 4 or parts[2] != "issues" or not parts[3].isdigit():
        raise ValueError("target_issue_not_canonical")
    return parts[0], parts[1], int(parts[3])


def validate_patch_manifest(manifest: Mapping[str, Any], workspace: Path) -> list[dict[str, Any]]:
    required = (
        "candidate_id",
        "target_issue_url",
        "target_repository",
        "base_branch",
        "branch_name",
        "pr_title",
        "pr_body",
        "files",
        "test_commands",
        "test_evidence",
    )
    missing = [key for key in required if not manifest.get(key)]
    if missing:
        raise ValueError(f"submission_manifest_missing:{','.join(missing)}")

    owner, repo, _ = _canonical_issue(str(manifest["target_issue_url"]))
    if str(manifest["target_repository"]) != f"{owner}/{repo}":
        raise ValueError("target_repository_issue_mismatch")
    if manifest.get("deliverable_kind") != "repository_patch":
        raise ValueError("generic_deliverable_not_submittable")
    if manifest.get("tests_passed") is not True:
        raise ValueError("tests_not_proven_passed")
    if manifest.get("requires_cla") is True or manifest.get("requires_dco") is True:
        raise ValueError("legal_attestation_required")
    if manifest.get("requires_new_account") is True:
        raise ValueError("new_account_required")
    if manifest.get("requires_payment_or_fee") is True:
        raise ValueError("payment_or_fee_required")
    if manifest.get("requires_kyc") is True:
        raise ValueError("kyc_required")

    tests = manifest.get("test_commands")
    evidence = manifest.get("test_evidence")
    if not isinstance(tests, list) or not tests or not all(isinstance(item, str) and item.strip() for item in tests):
        raise ValueError("test_commands_missing")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("test_evidence_missing")
    for relative in evidence:
        path = workspace / str(relative)
        if not path.is_file():
            raise ValueError(f"test_evidence_file_missing:{relative}")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("patch_files_missing")
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping):
            raise ValueError("invalid_patch_file_entry")
        target_path = str(item.get("path") or "").strip().lstrip("/")
        content_path = str(item.get("content_path") or "").strip()
        expected_hash = str(item.get("sha256") or "").strip()
        if not target_path or not content_path or not expected_hash:
            raise ValueError("patch_file_fields_missing")
        if target_path in seen or ".." in Path(target_path).parts:
            raise ValueError("unsafe_or_duplicate_patch_path")
        seen.add(target_path)
        source = workspace / content_path
        if not source.is_file():
            raise ValueError(f"patch_content_missing:{content_path}")
        actual = _sha256(source)
        if actual != expected_hash:
            raise ValueError(f"patch_sha256_mismatch:{target_path}")
        verified.append({"path": target_path, "source": source, "sha256": actual})
    return verified


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        # External mutations must never fall back to the GitHub Actions App token.
        # A caller may inject a PAT explicitly; otherwise use the central PAT policy.
        self.token = token.strip() if token and token.strip() else external_github_token()

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        url = path if path.startswith("https://") else f"https://api.github.com{path}"
        data = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "louis-os-autonomous-pr-submitter",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"github_http_{exc.code}:{detail[:500]}") from exc

    def current_user(self) -> str:
        return str(self.request("GET", "/user")["login"])

    def repository(self, full_name: str) -> dict[str, Any]:
        return dict(self.request("GET", f"/repos/{full_name}"))

    def ref_sha(self, full_name: str, branch: str) -> str:
        value = self.request("GET", f"/repos/{full_name}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        return str(value["object"]["sha"])

    def ensure_fork(self, upstream: str, login: str) -> str:
        upstream_repo = upstream.split("/", 1)[1]
        fork_name = f"{login}/{upstream_repo}"
        try:
            self.repository(fork_name)
            return fork_name
        except RuntimeError as exc:
            if "github_http_404" not in str(exc):
                raise
        self.request("POST", f"/repos/{upstream}/forks", {})
        for _ in range(12):
            time.sleep(5)
            try:
                self.repository(fork_name)
                return fork_name
            except RuntimeError as exc:
                if "github_http_404" not in str(exc):
                    raise
        raise RuntimeError("fork_creation_timeout")

    def ensure_branch(self, full_name: str, branch: str, base_sha: str) -> None:
        try:
            self.ref_sha(full_name, branch)
            return
        except RuntimeError as exc:
            if "github_http_404" not in str(exc):
                raise
        self.request("POST", f"/repos/{full_name}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha})

    def put_file(self, full_name: str, branch: str, target_path: str, source: Path, message: str) -> dict[str, Any]:
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in target_path.split("/"))
        existing_sha: str | None = None
        try:
            current = self.request("GET", f"/repos/{full_name}/contents/{encoded_path}?ref={urllib.parse.quote(branch, safe='')}")
            if isinstance(current, Mapping):
                existing_sha = str(current.get("sha") or "") or None
        except RuntimeError as exc:
            if "github_http_404" not in str(exc):
                raise
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(source.read_bytes()).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha
        result = self.request("PUT", f"/repos/{full_name}/contents/{encoded_path}", payload)
        return {
            "path": target_path,
            "commit_sha": result.get("commit", {}).get("sha"),
            "content_sha": result.get("content", {}).get("sha"),
        }

    def create_pull_request(self, upstream: str, head: str, base: str, title: str, body: str) -> dict[str, Any]:
        return dict(self.request("POST", f"/repos/{upstream}/pulls", {"title": title, "body": body, "head": head, "base": base}))

    def comment_issue(self, upstream: str, issue_number: int, body: str) -> dict[str, Any]:
        return dict(self.request("POST", f"/repos/{upstream}/issues/{issue_number}/comments", {"body": body}))


def submit_patch(manifest_path: Path, workspace: Path, client: GitHubClient | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = validate_patch_manifest(manifest, workspace)
    api = client or GitHubClient()
    login = api.current_user()
    upstream = str(manifest["target_repository"])
    repo = api.repository(upstream)
    permissions = repo.get("permissions") or {}
    direct_push = permissions.get("push") is True
    source_repo = upstream if direct_push else api.ensure_fork(upstream, login)
    repository_mode = "direct_push" if direct_push else "fork"
    base_branch = str(manifest["base_branch"])
    branch = str(manifest["branch_name"])
    upstream_sha = api.ref_sha(upstream, base_branch)
    if source_repo != upstream:
        source_repo_info = api.repository(source_repo)
        source_default = str(source_repo_info.get("default_branch") or base_branch)
        source_sha = api.ref_sha(source_repo, source_default)
    else:
        source_sha = upstream_sha
    api.ensure_branch(source_repo, branch, source_sha)

    commits: list[dict[str, Any]] = []
    for item in files:
        commits.append(
            api.put_file(
                source_repo,
                branch,
                str(item["path"]),
                Path(item["source"]),
                f"ATLAS: {manifest['candidate_id']} — {item['path']}",
            )
        )
    head = branch if source_repo == upstream else f"{login}:{branch}"
    pr = api.create_pull_request(
        upstream,
        head,
        base_branch,
        str(manifest["pr_title"]),
        str(manifest["pr_body"]),
    )
    pr_url = str(pr.get("html_url") or "")
    pr_number = int(pr.get("number") or 0)
    if not pr_url or not pr_number:
        raise RuntimeError("pull_request_receipt_missing")

    _, _, issue_number = _canonical_issue(str(manifest["target_issue_url"]))
    comment = api.comment_issue(
        upstream,
        issue_number,
        f"Implemented in {pr_url}. Tests and patch evidence are included in the pull request description.",
    )
    receipt = SubmissionReceipt(
        status="submitted",
        candidate_id=str(manifest["candidate_id"]),
        target_repository=upstream,
        target_issue_url=str(manifest["target_issue_url"]),
        authorization_mode="existing_authorized_github_identity",
        repository_mode=repository_mode,
        source_repository=source_repo,
        source_branch=branch,
        pull_request_url=pr_url,
        pull_request_number=pr_number,
        commit_receipts=tuple(commits),
        created_at=datetime.now(timezone.utc).isoformat(),
        verified=bool(comment.get("html_url") and all(item.get("commit_sha") for item in commits)),
    )
    return receipt.to_dict()


def diagnose_submission_failure(exc: Exception) -> SubmissionDiagnosis:
    message = f"{type(exc).__name__}: {exc}"
    if "generic_deliverable_not_submittable" in message:
        return SubmissionDiagnosis(
            status="blocked",
            blocked_stage="patch_creation",
            direct_cause="The current artifact is a generic draft, not a repository patch.",
            root_cause="No tested file-level implementation exists for the target repository.",
            resolution_class="AUTO_RESOLVABLE",
            next_action="inspect_target_repository_and_build_tested_patch_manifest",
        )
    if "external_github_pat_missing" in message:
        return SubmissionDiagnosis(
            status="blocked",
            blocked_stage="submission_capability",
            direct_cause="No user-owned PAT is configured for external GitHub writes.",
            root_cause=(
                "The GitHub Actions installation token cannot write to unrelated repositories; "
                "external submission requires LOUIS_GITHUB_PAT or the legacy external PAT secret."
            ),
            resolution_class="CAPABILITY_REQUIRED",
            next_action="use_documented_email_fallback_or_configure_LOUIS_GITHUB_PAT",
            human_intervention_minimal="configure one least-privilege GitHub PAT repository secret if direct public attribution is desired",
        )
    if any(code in message for code in ("github_http_401", "github_http_403")):
        return SubmissionDiagnosis(
            status="blocked",
            blocked_stage="submission_capability",
            direct_cause=message,
            root_cause="The configured external GitHub identity is missing permission or is no longer valid.",
            resolution_class="CAPABILITY_REQUIRED",
            next_action="use_documented_email_fallback_or_rotate_LOUIS_GITHUB_PAT",
            human_intervention_minimal="rotate or re-scope the external PAT only if direct GitHub submission is required",
        )
    if any(code in message for code in ("legal_attestation_required", "kyc_required", "payment_or_fee_required", "new_account_required")):
        return SubmissionDiagnosis(
            status="blocked",
            blocked_stage="legal_identity_or_financial_gate",
            direct_cause=message,
            root_cause="The opportunity requires a legal, identity or financial action outside the autonomous mandate.",
            resolution_class="LEGAL_OR_IDENTITY_GATE",
            next_action="pivot_to_alternative_executable_opportunity",
            human_intervention_minimal="only the exact legal, identity or financial gate if this opportunity remains economically preferable",
        )
    return SubmissionDiagnosis(
        status="failed",
        blocked_stage="github_submission",
        direct_cause=message,
        root_cause="The deterministic GitHub submission path encountered a technical or permission failure.",
        resolution_class="AUTO_RESOLVABLE",
        next_action="reproduce_classify_repair_and_retry_same_submission_idempotently",
    )
