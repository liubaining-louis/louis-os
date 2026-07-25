"""Evidence-first internal deliverable execution for verified opportunities.

This module deliberately stops before any external submission. It converts an
authentic, executable candidate into a reproducible workspace containing a
scope, implementation plan, draft deliverable and machine-readable receipt.
No state may advance without a concrete file and its SHA-256 digest.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_DELIVERABLE_TYPES = {"documentation", "analysis", "script", "data", "proposal"}


@dataclass(frozen=True)
class ExecutionReceipt:
    candidate_id: str
    status: str
    deliverable_type: str
    workspace: str
    artifact_path: str
    artifact_sha256: str
    manifest_path: str
    created_at: str
    externally_submitted: bool = False
    external_receipt: str | None = None


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return cleaned[:80] or "candidate"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_deliverable_type(candidate: dict[str, Any]) -> str:
    text = f"{candidate.get('title', '')}\n{candidate.get('body', '')}".lower()
    if any(term in text for term in ("documentation", "readme", "guide", "tutorial")):
        return "documentation"
    if any(term in text for term in ("csv", "dataset", "annotation", "data analysis")):
        return "data"
    if any(term in text for term in ("python", "script", "cli", "api", "automation")):
        return "script"
    if any(term in text for term in ("proposal", "request for proposal", "rfp", "tender")):
        return "proposal"
    return "analysis"


def validate_candidate(candidate: dict[str, Any]) -> None:
    required = ("id", "title", "url")
    missing = [key for key in required if not candidate.get(key)]
    if missing:
        raise ValueError(f"candidate_missing_fields:{','.join(missing)}")
    if candidate.get("readiness_status") != "executable_now":
        raise ValueError("candidate_not_executable_now")
    if not candidate.get("external_prerequisites_cleared", False):
        raise ValueError("external_prerequisites_not_cleared")
    if candidate.get("requires_user_validation", False):
        raise ValueError("candidate_requires_user_validation")
    if candidate.get("authenticity_status") not in (None, "verified") and not candidate.get("authenticity_verified", False):
        raise ValueError("candidate_authenticity_not_verified")


def build_scope(candidate: dict[str, Any], deliverable_type: str) -> str:
    return "\n".join(
        [
            f"# Execution scope — {candidate['title']}",
            "",
            f"Source: {candidate['url']}",
            f"Candidate ID: {candidate['id']}",
            f"Deliverable type: {deliverable_type}",
            "",
            "## Objective",
            "Produce a reviewable internal draft that addresses the public opportunity without performing an external submission.",
            "",
            "## Acceptance checks",
            "- the source URL and candidate ID are preserved;",
            "- the deliverable is a concrete file, not only a recommendation;",
            "- the artifact hash is recorded;",
            "- external submission remains false until an external receipt exists.",
        ]
    ) + "\n"


def build_artifact(candidate: dict[str, Any], deliverable_type: str) -> tuple[str, str]:
    title = candidate["title"]
    source = candidate["url"]
    if deliverable_type == "script":
        filename = "solution.py"
        content = (
            '"""Draft solution scaffold generated from a verified public opportunity.\n'
            f"Source: {source}\n"
            'This file is intentionally internal and has not been submitted externally.\n"""\n\n'
            "from __future__ import annotations\n\n"
            "def solve(payload: dict) -> dict:\n"
            "    \"\"\"Return a deterministic draft result ready for opportunity-specific refinement.\"\"\"\n"
            "    if not isinstance(payload, dict):\n"
            "        raise TypeError('payload must be a dict')\n"
            "    return {'status': 'draft', 'input_keys': sorted(payload)}\n"
        )
        return filename, content
    filename = "deliverable.md"
    content = "\n".join(
        [
            f"# Draft deliverable — {title}",
            "",
            f"Source: {source}",
            "",
            "## Problem understanding",
            "This draft records the concrete starting point for the verified opportunity and is intended for iterative refinement against its acceptance criteria.",
            "",
            "## Proposed deliverable",
            f"A structured {deliverable_type} deliverable with assumptions, method, validation steps and submission-ready evidence.",
            "",
            "## Validation plan",
            "1. Re-read the authoritative source and contribution rules.",
            "2. Replace every assumption with source-backed requirements.",
            "3. Add tests, examples or references appropriate to the requested output.",
            "4. Keep external submission disabled until a verifiable receipt is produced.",
            "",
            "## Submission state",
            "Not submitted externally.",
        ]
    ) + "\n"
    return filename, content


def execute_candidate(candidate: dict[str, Any], root: Path) -> ExecutionReceipt:
    validate_candidate(candidate)
    deliverable_type = infer_deliverable_type(candidate)
    if deliverable_type not in SAFE_DELIVERABLE_TYPES:
        raise ValueError("unsupported_deliverable_type")

    workspace = root / _slug(str(candidate["id"]))
    workspace.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    scope_path = workspace / "SCOPE.md"
    scope_path.write_text(build_scope(candidate, deliverable_type), encoding="utf-8")

    artifact_name, artifact_content = build_artifact(candidate, deliverable_type)
    artifact_path = workspace / artifact_name
    artifact_path.write_text(artifact_content, encoding="utf-8")
    artifact_hash = _sha256(artifact_path)

    manifest = {
        "candidate_id": candidate["id"],
        "source_url": candidate["url"],
        "title": candidate["title"],
        "status": "deliverable_created",
        "deliverable_type": deliverable_type,
        "artifact": artifact_name,
        "artifact_sha256": artifact_hash,
        "scope": scope_path.name,
        "created_at": now,
        "externally_submitted": False,
        "external_receipt": None,
    }
    manifest_path = workspace / "execution_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    receipt = ExecutionReceipt(
        candidate_id=str(candidate["id"]),
        status="deliverable_created",
        deliverable_type=deliverable_type,
        workspace=str(workspace),
        artifact_path=str(artifact_path),
        artifact_sha256=artifact_hash,
        manifest_path=str(manifest_path),
        created_at=now,
    )
    receipt_path = workspace / "execution_receipt.json"
    receipt_path.write_text(json.dumps(asdict(receipt), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt
