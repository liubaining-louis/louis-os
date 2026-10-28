# Explicitly reserved software listings — 28 October 2026

## Evidence and reproduced defect

Pinned main: `3633c4964e633d6955bfa0c484d9907f704ca7e5`.
Market run: https://github.com/liubaining-louis/louis-os/actions/runs/40658928381.
The persisted source observation at 08:45:26 UTC contains the Freelancer listing
https://www.freelancer.com/projects/github/node-security-updates-github-fixes.
It explicitly restricts bidding to a freelancer already contacted by the buyer.
No new source request was made to reproduce this defect.

`assess_software_scope` nevertheless returned accepted=true, frontend_bug_fix,
four hours. The classification receipt recorded one accepted software scope.
The final router rejected the listing, so this did not authorize or cause a bid.
Scope acceptance is not client acceptance, eligibility, verified submission or money.

## Bounded decision

Recognize the explicit English restriction against bidding when the parties
have not previously talked/spoken, including case and straight/curly apostrophes.
Return `explicitly_unavailable_or_reserved` through the existing rejection path.
That path records a terminal rejection, disables capability-gap creation and
does not request human approval for a reserved listing.

Do not infer reservation from prior experience, experience requirements or a
request to contact the buyer. Other reservation wording is not claimed covered.
No platform, payment, terms, identity, effort, policy or account gate is relaxed.
No credentials, wallet, cloud billing, schedules or network retries are changed.

## Verification and effect

- Before correction: four regression assertions fail (real observation plus
  three explicit-language variants). Open-bidding counterexamples remain accepted.
- After correction: four new test methods cover the observed text, variants,
  false positives and the classification script with isolated temporary files.
- 79 targeted tests pass across software scope, source collection, dossiers,
  policy compatibility, router and operator handoff. Full exact-SHA CI is still
  mandatory before merge; local targeted tests are not a full-suite claim.
- Offline replay of the real observation now rejects it with the explicit reason.
  Integration fixture reports accepted_count=0, rejected_count=1, no capability gap
  and no human action. This is not a live post-merge market observation.

Expected economic effect is limited: avoid spending preparation/review effort on
an explicitly unavailable buyer task and avoid a misleading positive scope count.
No revenue increase, cost saving in currency, submission or payment is established.
Cost of Actions and total historical cost remain unknown. No purchase or paid API
call is introduced. Rollback is a revert of this isolated change.

## Next action

Review and merge only after all CI checks succeed on the exact PR head. Then
read the next existing market cycle, without dispatching a duplicate scan.
If the listing is still present, require its terminal rejection; if absent, do
not fabricate live confirmation. Continue only with an actually accessible,
qualified payer task. Existing DNS/403/429 failures and missing accesses remain.
