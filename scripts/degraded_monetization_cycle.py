#!/usr/bin/env python3
"""Git-backed, bounded income runtime. No VM, cloud credentials, LLM or wallet.

Prepare persists an intent BEFORE submit is allowed. Uncertain submissions are
never automatically repeated. Existing receipts are monitored independently.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.autonomous_submission import GitHubClient, submit_patch, validate_patch_manifest
from atlas.capability_first_payable_scout import discover_capability_first_registry
from atlas.capability_patch_builder import build_capability_patch_from_candidates
from atlas.production_policy import evaluate_candidate, load_policy, preflight

STATE = ROOT / "results" / "degraded"
CONFIG = ROOT / "config" / "degraded_runtime.json"
POLICY = ROOT / "config" / "production_policy.json"
WRITE_KEYS = ("LOUIS_GITHUB_PAT", "ATLAS_EXTERNAL_GITHUB_TOKEN")


def submission_driver(cfg):
    driver = cfg.get("submission_driver", "github_actions")
    if driver not in {"github_actions", "connected_github_operator"}:
        raise ValueError("unknown_submission_driver")
    return driver


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default):
    if not path.exists():
        return default
    # Corrupt persisted state must never silently reset the submission ledger.
    return json.loads(path.read_text())


def save(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    for key in (*WRITE_KEYS, "GITHUB_TOKEN", "GH_TOKEN"):
        secret = os.getenv(key, "")
        if len(secret) >= 12 and secret in content:
            raise ValueError("credential_detected_in_output")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    tmp.replace(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected_github_redirect")


class BoundedGitHub:
    def __init__(self, max_requests=70, seconds=150):
        self.remaining = max_requests
        self.deadline = time.monotonic() + seconds
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValueError("non_github_source_rejected")
        if self.remaining <= 0 or time.monotonic() >= self.deadline:
            raise RuntimeError("discovery_budget_exhausted")
        self.remaining -= 1
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "louis-os-degraded"}
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = "Bearer " + token
        with self.opener.open(urllib.request.Request(url, headers=headers),
                              timeout=max(.1, min(10, self.deadline - time.monotonic()))) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("github_response_too_large")
        return json.loads(raw)


def candidate_allowed(candidate, policy):
    context = dict(candidate, reward_verified=candidate.get("opportunity_authenticity_verified") is True,
                   payment_path=candidate.get("payment_provider"), family="light_technical")
    # Existing handlers validate replacements/syntax; they do not execute a
    # project's tests. Limit automatic delivery to documented text/link fixes.
    if candidate.get("patch_handler") not in {"broken_link_replacement", "deterministic_text_replacement"}:
        return False
    target = str((candidate.get("capability_match") or {}).get("target_path", ""))
    if not target.lower().endswith((".md", ".rst", ".txt")):
        return False
    return evaluate_candidate(context, policy).allowed


def monitor(receipts, getter):
    observations = []
    for receipt in receipts[-10:]:
        url = receipt.get("pull_request_url", "")
        parsed = urllib.parse.urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        if parsed.netloc != "github.com" or len(parts) != 4 or parts[2] != "pull" or not parts[3].isdigit():
            continue
        try:
            pr = getter(f"https://api.github.com/repos/{parts[0]}/{parts[1]}/pulls/{parts[3]}")
            status = "merged_payment_unverified" if pr.get("merged_at") else pr.get("state", "unknown")
            observations.append({"url": url, "status": status, "checked_at": now(), "paid": False})
        except Exception as exc:
            observations.append({"url": url, "status": "unavailable", "error_type": type(exc).__name__})
    return observations


def prepare(root=ROOT, state=STATE, getter=None):
    cfg = read(root / "config/degraded_runtime.json", {})
    driver = submission_driver(cfg)
    policy = load_policy(root / "config/production_policy.json")
    prior = read(state / "status.json", {})
    intents = read(state / "intents.json", {"items": []})
    local_receipts = read(state / "receipts.json", {"receipts": []})
    historical = read(root / "results/submission_receipts.json", {"receipts": []})
    receipts = {r.get("pull_request_url"): r for r in historical["receipts"] + local_receipts["receipts"]}
    getter = getter or BoundedGitHub(cfg["max_requests"], cfg["discovery_seconds"])
    run_id = os.getenv("GITHUB_RUN_ID", "local") + ":" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    status = {"schema_version": "1.0", "mode": "github_actions_without_vm", "started_at": now(),
              "run_id": run_id, "cycle": int(prior.get("cycle", 0)) + 1,
              "runtime_status": "running", "cycle_outcome": "starting", "vm_required": False,
              "cloud_required": False, "submission_driver": driver,
              "paid_verified_this_cycle": 0, "submitted_this_cycle": 0,
              "external_credential_present": os.getenv("LOUIS_EXTERNAL_CREDENTIAL_PRESENT") == "true",
              "unavailable_lanes": {name: "credentials_and_state_remain_on_vm" for name in
                                    ["MoltJobs", "TaskForce", "AgentPact", "Earn wallet"]}}
    save(state / "status.json", status)
    # A new cycle cannot consume yesterday's package.
    (state / "ready.json").unlink(missing_ok=True)
    if not cfg.get("enabled") or not preflight(policy).allowed:
        status.update(runtime_status="disabled", cycle_outcome="policy_disabled", finished_at=now())
        save(state / "status.json", status)
        return status
    save(state / "monitor.json", {"observations": monitor(list(receipts.values()), getter)})
    outcome = discover_capability_first_registry(getter=getter, max_inspected=cfg["max_inspected"],
                                                max_candidates=cfg["max_candidates"])
    save(state / "discovery.json", outcome.to_dict())
    attempted = {x["candidate_id"] for x in intents["items"]}
    attempted.update(r.get("candidate_id") for r in receipts.values())
    candidates = [c for c in outcome.registry["candidates"]
                  if c["id"] not in attempted and candidate_allowed(c, policy)]
    status.update(inspected=outcome.inspected, qualified=len(candidates), discovery_errors=len(outcome.errors),
                  rejections=dict(Counter(x.get("reason", "unknown") for x in outcome.rejected)),
                  cycle_outcome="no_eligible_candidate", next_action="refresh_on_next_market_cycle")
    if candidates:
        built = build_capability_patch_from_candidates(candidates[:1], state / "workspaces", getter=getter)
        save(state / "build.json", built.to_dict())
        status["cycle_outcome"] = built.status
        if built.status == "patch_built":
            workspace = Path(built.workspace)
            manifest = read(Path(built.manifest_path), {})
            validate_patch_manifest(manifest, workspace)
            candidate = next(c for c in candidates if c["id"] == built.candidate_id)
            # Pin the upstream blobs inspected immediately after construction.
            base_blobs = {}
            for entry in manifest["files"]:
                path = urllib.parse.quote(entry["path"], safe="/")
                url = f"https://api.github.com/repos/{manifest['target_repository']}/contents/{path}?ref={manifest['base_branch']}"
                upstream = getter(url)
                original = base64.b64decode(upstream["content"]).decode("utf-8")
                capability = manifest["patch_capability"]
                expected = original.replace(capability["old_value"], capability["new_value"], 1)
                generated = (workspace / entry["content_path"]).read_text()
                if original.count(capability["old_value"]) != 1 or expected != generated:
                    raise ValueError("upstream_changed_during_preparation")
                base_blobs[entry["path"]] = upstream["sha"]
            ready = {"candidate": candidate, "run_id": run_id, "workspace": str(workspace.relative_to(state)),
                     "manifest_path": str(Path(built.manifest_path).relative_to(state)), "base_blobs": base_blobs,
                     "manifest_sha256": hashlib.sha256(Path(built.manifest_path).read_bytes()).hexdigest()}
            save(state / "ready.json", ready)
            if driver == "connected_github_operator":
                status.update(cycle_outcome="prepared_for_connected_operator",
                              next_action="operator_pin_commit_revalidate_and_checkpoint_intent")
            elif status["external_credential_present"]:
                intents["items"].append({"candidate_id": built.candidate_id, "run_id": run_id,
                                         "status": "prepared", "created_at": now()})
                save(state / "intents.json", intents)
                status.update(cycle_outcome="prepared_for_submission", next_action="persist_then_submit")
            else:
                status.update(cycle_outcome="prepared_external_credential_missing",
                              next_action="tutor_can_submit_reviewable_package_with_existing_connector")
    qualification_errors = sum(x.get("reason") == "capability_first_qualification_error" for x in outcome.rejected)
    status.update(runtime_status="partial" if outcome.errors or qualification_errors else "healthy", finished_at=now())
    save(state / "status.json", status)
    return status


def submit(root=ROOT, state=STATE, getter=None, client=None):
    cfg = read(root / "config/degraded_runtime.json", {})
    # A package prepared before takeover must not be sent by a later runner.
    if submission_driver(cfg) == "connected_github_operator":
        return {"status": "delegated_to_connected_operator"}
    policy = load_policy(root / "config/production_policy.json")
    status = read(state / "status.json", {})
    if not cfg.get("enabled") or cfg.get("max_submissions_per_cycle") != 1 or not preflight(policy).allowed:
        return {"status": "policy_disabled"}
    if status.get("cycle_outcome") != "prepared_for_submission":
        return {"status": "no_current_package_to_submit"}
    ready = read(state / "ready.json", {})
    run_id = os.getenv("GITHUB_RUN_ID", "local") + ":" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if ready.get("run_id") != run_id:
        raise ValueError("stale_submission_package")
    if os.getenv("LOUIS_DEGRADED_CHECKPOINT") != run_id:
        raise ValueError("submission_intent_not_remotely_checkpointed")
    intents = read(state / "intents.json", {"items": []})
    intent = next(x for x in intents["items"] if x["candidate_id"] == ready["candidate"]["id"])
    if intent["status"] != "prepared" or intent["run_id"] != run_id:
        return {"status": "already_attempted_requires_reconciliation"}
    manifest_path = (state / ready["manifest_path"]).resolve()
    workspace = (state / ready["workspace"]).resolve()
    manifest_path.relative_to(state.resolve())
    workspace.relative_to(state.resolve())
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != ready["manifest_sha256"]:
        raise ValueError("prepared_manifest_changed")
    getter = getter or BoundedGitHub(25, 80)
    candidate = ready["candidate"]
    parts = urllib.parse.urlsplit(candidate["url"]).path.strip("/").split("/")
    canonical = getter(f"https://api.github.com/repos/{parts[0]}/{parts[1]}/issues/{parts[3]}")
    refresh = discover_capability_first_registry(
        getter=lambda url: {"items": [canonical]} if "/search/issues?" in url else getter(url),
        queries=("exact-target-revalidation",), max_inspected=1, max_candidates=1)
    fresh = next((c for c in refresh.registry["candidates"] if c["id"] == candidate["id"]), None)
    if not fresh or not candidate_allowed(fresh, policy):
        raise ValueError("candidate_no_longer_eligible")
    if fresh.get("capability_match") != candidate.get("capability_match"):
        raise ValueError("requirements_changed_rebuild_required")
    manifest = read(manifest_path, {})
    for path, sha in ready["base_blobs"].items():
        url = f"https://api.github.com/repos/{manifest['target_repository']}/contents/{urllib.parse.quote(path, safe='/')}?ref={manifest['base_branch']}"
        if getter(url).get("sha") != sha:
            raise ValueError("upstream_changed_rebuild_required")
    intent.update(status="attempted_requires_reconciliation", attempted_at=now())
    save(state / "intents.json", intents)
    try:
        receipt = submit_patch(manifest_path, workspace, client=client)
        records = read(state / "receipts.json", {"receipts": []})
        if not any(x.get("pull_request_url") == receipt["pull_request_url"] for x in records["receipts"]):
            records["receipts"].append(receipt)
        save(state / "receipts.json", records)
        intent.update(status="submitted", receipt=receipt["pull_request_url"])
        status.update(cycle_outcome="submitted" if receipt.get("verified") else "submitted_unverified",
                      submitted_this_cycle=int(bool(receipt.get("verified"))), next_action="monitor_existing_submission")
    except Exception as exc:
        status.update(cycle_outcome="submission_uncertain", error_type=type(exc).__name__,
                      next_action="reconcile_existing_branch_and_pr_before_retry")
    save(state / "intents.json", intents)
    status["finished_at"] = now()
    save(state / "status.json", status)
    return status


def operator_briefing(state=STATE, root=ROOT):
    """Read-only handoff; a source commit must be pinned by the live operator."""
    cfg = read(root / "config/degraded_runtime.json", {})
    status = read(state / "status.json", {})
    ready = read(state / "ready.json", {})
    intents = read(state / "intents.json", {"items": []})["items"]
    candidate = ready.get("candidate", {})
    current = (cfg.get("enabled") is True
               and submission_driver(cfg) == "connected_github_operator"
               and preflight(load_policy(root / "config/production_policy.json")).allowed
               and status.get("runtime_status") in {"healthy", "partial"}
               and status.get("cycle_outcome") == "prepared_for_connected_operator"
               and ready.get("run_id") == status.get("run_id")
               and bool(candidate.get("id")))
    reserved = any(x.get("candidate_id") == candidate.get("id") for x in intents)
    return {
        "schema_version": "1.0", "generated_at": now(),
        "submission_driver": submission_driver(cfg),
        "execution": "interactive_conversation_only", "continuous_operator": False,
        "tracking_issue": cfg.get("tracking_issue", 473),
        "last_cycle": status.get("run_id"), "last_cycle_at": status.get("finished_at"),
        "candidate_id": candidate.get("id") if current else None,
        "candidate_url": candidate.get("url") if current else None,
        "package_path": "results/degraded/ready.json" if current else None,
        "package_available_for_review": bool(current and not reserved),
        "submission_authorized": False,
        "reconciliation_required": [x for x in intents if x.get("status") != "submitted"],
        "next_action": ("revalidate_package_and_reserve_candidate" if current and not reserved
                        else "reconcile_intents" if intents and any(x.get("status") != "submitted" for x in intents)
                        else "review_tracking_issue_and_wait_for_qualified_candidate"),
        "runbook": "docs/github-operator-mode.md",
        "handoff": "docs/github-operator-handoff.md",
    }


def report(state=STATE, root=ROOT):
    data = read(state / "status.json", {})
    briefing = operator_briefing(state, root)
    state.mkdir(parents=True, exist_ok=True)
    save(state / "operator-briefing.json", briefing)
    lines = ["## Louis OS — mode dégradé sans VM", "",
             f"- Runtime : {data.get('runtime_status', 'unknown')}",
             f"- Dernier cycle : {data.get('finished_at', data.get('started_at'))}",
             f"- Résultat : {data.get('cycle_outcome')}",
             f"- Missions inspectées : {data.get('inspected', 0)} ; éligibles : {data.get('qualified', 0)}",
             f"- Soumissions vérifiées dans ce cycle : {data.get('submitted_this_cycle', 0)}",
             "- Paiements nouveaux vérifiés : 0 (aucun accès wallet dans ce mode)",
             f"- Suite : {data.get('next_action')}", "",
             f"- Pilote des soumissions : {briefing['submission_driver']}",
             f"- Paquet disponible pour revue : {briefing['package_available_for_review']}",
             "- Relais conversationnel : results/degraded/operator-briefing.json ; docs/github-operator-handoff.md",
             "- Le pilote connecté agit pendant une conversation active ; aucun réveil automatique.", "",
             "État durable : results/degraded/. Les services et wallets restés sur la VM sont indisponibles.",
             "Les limites, contrôles de paiement et garde-fous de production restent applicables."]
    (state / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    phase = argparse.ArgumentParser()
    phase.add_argument("phase", choices=["prepare", "submit", "report"])
    args = phase.parse_args()
    try:
        if args.phase == "report":
            report()
        else:
            print(json.dumps(prepare() if args.phase == "prepare" else submit()))
    except Exception as exc:
        save(STATE / "failure.json", {"phase": args.phase, "error_type": type(exc).__name__, "at": now()})
        current = read(STATE / "status.json", {})
        current.update(runtime_status="failed", cycle_outcome=f"{args.phase}_failed",
                       error_type=type(exc).__name__, finished_at=now())
        save(STATE / "status.json", current)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
