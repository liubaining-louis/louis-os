# GitHub admin hardening target

These controls live in GitHub's repository administration plane and are intentionally separate from Louis OS runtime code.

## Main branch

Target a branch ruleset for `main` with:

- deletion and force-push blocked;
- pull request required for production-impacting changes;
- ATLAS CI required before merge;
- required conversation resolution;
- Code Owner review required for files covered by `.github/CODEOWNERS` when human-reviewed governance is desired;
- bypass restricted to explicit emergency administration only.

Because Louis OS also writes economically meaningful result snapshots to `main`, automation-only result paths should be handled with a narrowly scoped exception rather than granting broad workflow bypass over source, policy or workflow files.

## Production environment

Target the `production` environment with:

- deployment branches restricted to `main` / protected branches;
- no arbitrary feature branch access to production OIDC/secrets;
- environment secrets scoped only to workflows that genuinely need them;
- optional required reviewer only if it does not disable intended unattended H24 read/scan workflows.

## Current audit status

Application-level controls cannot substitute for these settings. The audit remains incomplete until GitHub reports an active ruleset / branch protection and a non-null production deployment branch policy.
