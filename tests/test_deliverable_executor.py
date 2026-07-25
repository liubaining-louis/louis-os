import hashlib
import json
from pathlib import Path

import pytest

from atlas.deliverable_executor import execute_candidate, infer_deliverable_type, validate_candidate


def candidate(**overrides):
    value = {
        "id": "abc123",
        "title": "Paid Python API documentation bounty",
        "body": "Create a Python API guide and submit a pull request.",
        "url": "https://github.com/example/project/issues/1",
        "readiness_status": "executable_now",
        "external_prerequisites_cleared": True,
        "requires_user_validation": False,
        "authenticity_verified": True,
    }
    value.update(overrides)
    return value


def test_infers_documentation_before_script():
    assert infer_deliverable_type(candidate()) == "documentation"


def test_execute_creates_hashed_artifact_and_receipt(tmp_path: Path):
    receipt = execute_candidate(candidate(), tmp_path)
    artifact = Path(receipt.artifact_path)
    manifest = json.loads(Path(receipt.manifest_path).read_text(encoding="utf-8"))

    assert receipt.status == "deliverable_created"
    assert receipt.externally_submitted is False
    assert artifact.exists()
    assert receipt.artifact_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert manifest["status"] == "deliverable_created"
    assert manifest["externally_submitted"] is False
    assert manifest["external_receipt"] is None
    assert (artifact.parent / "execution_receipt.json").exists()
    assert (artifact.parent / "SCOPE.md").exists()


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"readiness_status": "gated"}, "candidate_not_executable_now"),
        ({"external_prerequisites_cleared": False}, "external_prerequisites_not_cleared"),
        ({"requires_user_validation": True}, "candidate_requires_user_validation"),
        ({"authenticity_verified": False, "authenticity_status": "blocked"}, "candidate_authenticity_not_verified"),
    ],
)
def test_rejects_ineligible_candidates(changes, reason):
    with pytest.raises(ValueError, match=reason):
        validate_candidate(candidate(**changes))


def test_script_artifact_is_concrete_scaffold(tmp_path: Path):
    receipt = execute_candidate(
        candidate(title="Paid Python automation script", body="Implement a Python CLI automation."),
        tmp_path,
    )
    artifact = Path(receipt.artifact_path)
    source = artifact.read_text(encoding="utf-8")
    assert artifact.name == "solution.py"
    assert "def solve(payload: dict) -> dict:" in source
    assert "Not submitted" not in source
    assert receipt.artifact_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
