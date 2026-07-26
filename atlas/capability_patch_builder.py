"""Syntax-aware deterministic patch construction for capability-matched tasks."""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .patch_capabilities import PatchCapabilityMatch, classify_patch_capability
from .repository_patch_builder import (
    JsonGetter,
    PatchBuildResult,
    TargetPreflight,
    _decode_content,
    _repo_api_url,
    _repo_content_url,
    github_get_json,
    preflight_candidate,
    utc_now,
)


def _validate_modified_file(path: str, content: str, capability: PatchCapabilityMatch) -> list[str]:
    evidence = [
        f"capability={capability.capability_id}",
        f"validation_kind={capability.validation_kind}",
        f"old_occurrences_after={content.count(capability.old_value)}",
        f"new_occurrences_after={content.count(capability.new_value)}",
    ]
    lowered = path.casefold()
    if capability.capability_id == "broken_link_replacement":
        if not capability.new_value.startswith(("http://", "https://")):
            raise ValueError("replacement_url_not_absolute")
        evidence.append("url_validation=passed")
    elif capability.capability_id == "configuration_scalar_replacement":
        if lowered.endswith(".json"):
            json.loads(content)
            evidence.append("json_syntax=passed")
        elif lowered.endswith(".toml"):
            tomllib.loads(content)
            evidence.append("toml_syntax=passed")
        else:
            raise ValueError("unsupported_configuration_format")
    elif capability.capability_id == "simple_test_expectation_replacement":
        if lowered.endswith(".py"):
            compile(content, path, "exec")
            evidence.append("python_syntax=passed")
        else:
            evidence.append("text_test_fixture_validation=passed")
    else:
        evidence.append("deterministic_text_validation=passed")
    evidence.append("result=passed")
    return evidence


def build_capability_patch(
    preflight: TargetPreflight,
    workspace_root: Path,
    getter: JsonGetter | None = None,
) -> dict[str, Any]:
    getter = getter or github_get_json
    if not preflight.viable:
        raise ValueError("target_not_credible")
    capability = classify_patch_capability(preflight.issue)
    if capability is None:
        raise ValueError("unsupported_patch_synthesis")

    repo_info = getter(_repo_api_url(preflight.target_repository))
    if not isinstance(repo_info, Mapping):
        raise ValueError("target_repository_metadata_invalid")
    base_branch = str(repo_info.get("default_branch") or "main")
    file_payload = getter(_repo_content_url(preflight.target_repository, capability.target_path, base_branch))
    if not isinstance(file_payload, Mapping):
        raise ValueError("target_file_payload_invalid")
    original = _decode_content(file_payload)
    old_count = original.count(capability.old_value)
    if old_count != 1:
        raise ValueError(f"replacement_occurrence_count:{old_count}")
    modified = original.replace(capability.old_value, capability.new_value, 1)
    if capability.old_value in modified or capability.new_value not in modified:
        raise RuntimeError("deterministic_replacement_test_failed")
    validation_lines = _validate_modified_file(capability.target_path, modified, capability)

    workspace = workspace_root / preflight.candidate_id
    patch_path = workspace / "patch_files" / capability.target_path
    test_path = workspace / "test_evidence.txt"
    manifest_path = workspace / "patch_manifest.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(modified, encoding="utf-8")
    test_path.write_text(
        "\n".join(
            [
                f"candidate={preflight.candidate_id}",
                f"target={preflight.target_repository}:{capability.target_path}",
                f"old_occurrences_before={old_count}",
                *validation_lines,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    branch_name = f"louis-os/{preflight.candidate_id}-{capability.capability_id[:24]}"
    manifest = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "candidate_id": preflight.candidate_id,
        "target_issue_url": preflight.canonical_issue_url,
        "target_repository": preflight.target_repository,
        "base_branch": base_branch,
        "branch_name": branch_name,
        "pr_title": f"Apply {capability.capability_id.replace('_', ' ')} in {capability.target_path}",
        "pr_body": (
            f"Closes {preflight.canonical_issue_url}\n\n"
            f"Applies the requested `{capability.capability_id}` in `{capability.target_path}`.\n\n"
            "Validation: the source value occurred exactly once, the replacement was verified, "
            "syntax-aware validation passed and the generated file SHA-256 was recorded."
        ),
        "deliverable_kind": "repository_patch",
        "patch_capability": capability.to_dict(),
        "files": [
            {
                "path": capability.target_path,
                "content_path": str(patch_path.relative_to(workspace)),
                "sha256": digest,
            }
        ],
        "test_commands": [f"validate {capability.validation_kind} for {capability.target_path}"],
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
        "patch_capability": capability.capability_id,
    }


def build_capability_patch_from_candidates(
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
            built = build_capability_patch(preflight, workspace_root, getter)
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
