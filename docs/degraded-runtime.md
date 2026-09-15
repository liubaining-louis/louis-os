# Louis OS without the VM

Active configuration: `config/degraded_runtime.json`.

This runtime executes on a standard GitHub Actions Linux runner using Python's
standard library and Louis OS's existing deterministic discovery and patch
modules. It needs neither GCP billing, Firestore, SSH, an LLM API nor a wallet.

The existing twice-daily Universal market workflow calls this runtime after its
market pass. It also runs on changes to its own code/configuration and supports
manual dispatch. No new cron is added. It is periodic, not an always-on server.

Each cycle monitors up to ten existing GitHub PR receipts, makes at most 70
discovery requests within 150 seconds, examines at most 30 issues, and prepares
at most one policy-compliant documentation/text/link patch. Provider evidence,
repository trust, competition, capability and production-policy gates remain.
Unsupported technical work remains available for tutor review; syntax checks
are not represented as project behavioral tests.

The current `submission_driver` is `connected_github_operator`: preparation and
monitoring continue, but this runtime cannot submit, even with a PAT. Each report
persists `results/degraded/operator-briefing.json` for the active conversation.
See [the operator runbook](github-operator-mode.md) for takeover and reconciliation.

With `submission_driver` explicitly set to `github_actions`, the prepare step
never receives the external write credential. Submission uses
an existing `LOUIS_GITHUB_PAT` or `ATLAS_EXTERNAL_GITHUB_TOKEN` repository secret
only when present, after a durable git checkpoint, fresh canonical revalidation,
blob comparison and manifest hash validation. The repository installation token
is never used as an external identity. Each opportunity can be attempted once;
an uncertain result is held for reconciliation instead of creating duplicates.
No new account, credit purchase, transfer, signature or paid dependency is used.

Results, heartbeat, discovery, manifests, intent and receipts live under
`results/degraded/`, with a downloadable artifact as a persistence fallback.
The canonical revenue ledger is not overwritten. A merged PR is not a payment;
this runtime cannot verify wallet settlement. Its zero new verified payments
does not erase historical revenue. See `results/degraded/report.md` and issue
#473 for operations. GitHub's artifact retention is 14 days; git state persists.

MoltJobs, TaskForce, AgentPact and Earn wallet state remain unavailable when their
credentials exist only on the VM. No secrets are copied out of that VM.

To suspend this mode, set `enabled` to false. To resume GCP deployment, first
restore billing and set `enabled` to false, then manually dispatch the existing
deployment workflow and verify a fresh VM heartbeat. Do not activate both
submission workers against the same opportunity without reconciling intents.
