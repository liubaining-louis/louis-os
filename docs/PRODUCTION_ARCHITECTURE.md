# Louis OS production architecture

## Design rule

Louis OS uses shared orchestration lanes and marketplace/source adapters. A new marketplace or experiment should not create a new scheduled workflow unless it introduces a genuinely different trust boundary or execution cadence.

## Eight production lanes

1. **Discover** — collect public/authorized opportunity signals into normalized candidates.
2. **Qualify** — verify freshness, payment authority, competition, policy and capability fit.
3. **Build** — produce bounded deliverables or repository patches under the canonical production policy.
4. **Submit** — execute an authorized external action and persist a verifiable receipt.
5. **Follow up** — observe acceptance, rejection, feedback and requested revisions.
6. **Payment** — independently verify selection and receipt before booking revenue.
7. **Learn** — update empirical response/win/payment rates and capability performance.
8. **Ops** — CI, runtime hardening, health, kill switch and incident response.

Marketplace-specific code belongs under adapters/scripts and should feed one of these lanes. Diagnostic probes should normally be scripts or manual workflows, not scheduled production workflows.

## Policy authority

`config/production_policy.json` is the canonical owner strategy for maintained economic paths. `atlas/production_policy.py` is the shared enforcement implementation.

A downstream action may be stricter than the canonical policy but must never be looser. No local marketplace score can override the kill switch, forbidden actions, effort cap, reward cap or owner task-family strategy.

## Runtime boundary

Repository code may be copied to the VM only for bounded execution. Marketplace code runs as the non-login `louis-os` account. Root is reserved for explicit administrative bootstrap steps such as creating the runtime account or setting file ownership.

Secret access is per-file and allow-listed. The runtime identity must not receive blanket read access to the secret directory.

## State boundary

Git is the durable audit trail for code, policy and meaningful economic evidence; it is not the high-frequency runtime database. High-frequency state stays on the VM / Firestore. A workflow may persist a result snapshot only when its economically meaningful state changes. Timestamps alone must not create commits.

## Economic truth

The pipeline hierarchy is:

`PAID > ACCEPTED/WON > VERIFIED SUBMITTED > QUALIFIED REPLY > CANDIDATE`

Potential rewards and simulations are not revenue. Net profit is unknown until all material operating-cost components are known.

## Workflow governance

- Reuse an existing production lane before adding a workflow.
- Remove or manualize superseded one-off workflows.
- Scheduled external-action workflows must pass the global production policy.
- Production workflows should pin third-party GitHub Actions to immutable commit SHAs.
- Workflows with GCP/wallet/credential reach require least privilege and fail-closed behavior.
- Duplicate workflow names or overlapping schedules for the same economic stage are defects.

## GitHub administrative controls

The desired repository configuration is: protected `main`, required ATLAS CI, restricted direct pushes for production-impacting files, and protected `production` environment. These settings are repository-admin controls and must be verified independently of application code because they are not enforceable by the Louis OS runtime itself.
