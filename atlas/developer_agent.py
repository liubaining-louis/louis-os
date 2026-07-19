"""Turn an approved improvement proposal into an executable engineering dossier.

The v2 developer agent performs the first autonomous execution handoff: it validates
an Evolution Engine proposal, creates a deterministic implementation specification,
and persists a claimable work item. GitHub side effects are deliberately delegated to
the workflow so credentials remain outside application code.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "improvement"


def validate_proposal(proposal: Mapping[str, Any]) -> None:
    required = ("proposal_id", "capability", "title", "rationale", "acceptance_criteria")
    missing = [key for key in required if not proposal.get(key)]
    if missing:
        raise ValueError(f"proposal missing required fields: {', '.join(missing)}")
    criteria = proposal.get("acceptance_criteria")
    if not isinstance(criteria, list) or not all(isinstance(item, str) and item.strip() for item in criteria):
        raise ValueError("acceptance_criteria must be a non-empty list of strings")


def build_dossier(proposal: Mapping[str, Any]) -> dict[str, Any]:
    validate_proposal(proposal)
    proposal_id = str(proposal["proposal_id"])
    capability = str(proposal["capability"])
    branch = f"atlas/improve-{_slug(capability)}-{proposal_id[:8]}"
    return {
        "schema_version": 1,
        "created_at": _now(),
        "agent": "louis-developer-agent-v2",
        "proposal_id": proposal_id,
        "status": "ready_for_implementation",
        "branch": branch,
        "title": str(proposal["title"]),
        "capability": capability,
        "problem_statement": str(proposal["rationale"]),
        "acceptance_criteria": list(proposal["acceptance_criteria"]),
        "implementation_protocol": [
            "Inspect the current implementation and tests before editing",
            "Make the smallest reversible change satisfying the acceptance criteria",
            "Add or update deterministic tests",
            "Run the complete relevant test suite",
            "Record benchmark or behavioral evidence before requesting promotion",
            "Open a pull request; never mutate main directly",
        ],
        "required_evidence": [
            "test command and result",
            "before/after metric or deterministic behavioral proof",
            "changed file list",
            "rollback instructions",
        ],
        "promotion_gate": {
            "tests_pass": True,
            "benchmark_no_regression": True,
            "review_required": True,
            "direct_main_push_forbidden": True,
            "automatic_merge": False,
        },
    }


def dossier_markdown(dossier: Mapping[str, Any]) -> str:
    criteria = "\n".join(f"- [ ] {item}" for item in dossier["acceptance_criteria"])
    protocol = "\n".join(f"{index}. {item}" for index, item in enumerate(dossier["implementation_protocol"], 1))
    evidence = "\n".join(f"- [ ] {item}" for item in dossier["required_evidence"])
    return f"""## Autonomous improvement dossier

**Proposal:** `{dossier['proposal_id']}`  
**Capability:** `{dossier['capability']}`  
**Planned branch:** `{dossier['branch']}`  
**Agent state:** `{dossier['status']}`

### Problem
{dossier['problem_statement']}

### Acceptance criteria
{criteria}

### Implementation protocol
{protocol}

### Required evidence
{evidence}

### Promotion rules
- Tests and benchmark evidence are mandatory.
- No direct mutation of `main`.
- Review is mandatory and automatic merge is disabled.

<!-- louis-proposal-id:{dossier['proposal_id']} -->
"""


def persist_local(dossier: Mapping[str, Any]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    target = RESULTS / "developer_dossier_latest.json"
    target.write_text(json.dumps(dict(dossier), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def persist_firestore(dossier: Mapping[str, Any], project_id: str) -> None:
    from google.cloud import firestore

    client = firestore.Client(project=project_id)
    proposal_id = str(dossier["proposal_id"])
    client.collection("louis_improvement_queue").document(proposal_id).set(
        {
            "status": dossier["status"],
            "developer_dossier": dict(dossier),
            "developer_claimed_at": dossier["created_at"],
        },
        merge=True,
    )
    client.collection("louis_developer_runtime").document("current").set(
        {
            "last_dossier_at": dossier["created_at"],
            "proposal_id": proposal_id,
            "status": dossier["status"],
            "branch": dossier["branch"],
        },
        merge=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", default=str(RESULTS / "evolution_cycle_latest.json"))
    parser.add_argument("--project-id")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    cycle = json.loads(Path(args.cycle).read_text(encoding="utf-8"))
    proposal = cycle.get("selected_improvement")
    if not proposal:
        print("No selected improvement; developer agent has nothing to claim")
        return 0

    dossier = build_dossier(proposal)
    target = persist_local(dossier)
    if args.project_id:
        persist_firestore(dossier, args.project_id)

    if args.github_output:
        print(f"proposal_id={dossier['proposal_id']}")
        print(f"issue_title=[ATLAS] {dossier['title']}")
        print(f"branch={dossier['branch']}")
        print(f"dossier_path={target}")
    else:
        print(json.dumps(dossier, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
