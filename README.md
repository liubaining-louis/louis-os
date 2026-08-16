# Louis OS / ATLAS

Louis OS is an autonomous, evidence-driven agent runtime for discovering, qualifying, executing and following bounded digital work. The repository contains the ATLAS decision core, deterministic evaluators, marketplace adapters, production workflows, VM bridges, economic ledgers and safety controls.

## Production objective

The current owner strategy is **quick-win cash-first**: prioritize short, legally automatable writing, research, product-feedback, lead-research, data and light-technical tasks. The economic truth order is:

`PAID > ACCEPTED/WON > VERIFIED SUBMITTED > QUALIFIED REPLY > CANDIDATE`

Detected opportunities, simulated revenue and potential rewards are never booked as revenue.

## Global production policy

`config/production_policy.json` is the machine-readable production authority. All maintained external-action paths must fail closed when:

- `kill_switch` is active;
- external actions are disabled;
- the candidate violates the current quick-win effort/reward strategy;
- the task matches a prohibited family or blocked term;
- the payment path is unverified/unknown where verification is required.

`atlas/production_policy.py` implements the shared policy gate. The repository-visible kill switch is intentionally simple so the owner can stop outbound economic actions with one reviewed change.

## Runtime security

Production marketplace workers run through a dedicated non-login Linux identity (`louis-os`) and the `louis-runtime` group. Secret access is allow-listed by file; runtime workers do not receive blanket access to `/var/lib/louis-os/secrets`.

High-risk actions remain gated. Louis OS must not autonomously perform payments, purchases, contract signatures, credential changes, KYC/CAPTCHA bypass, mandatory staking, gambling/speculation, deceptive engagement or unauthorized security testing.

## Core validation

ATLAS uses deterministic tests and benchmark evidence. Typical local validation:

```bash
python -m unittest discover -s tests -v
python -m atlas.maturity verify-history docs/maturity/scorecards
python -m atlas.cli run-all
python -m atlas.cli report
```

The project requires Python 3.10+ and currently uses external dependencies including Firestore, Google GenAI, Playwright and `eth-account`; see `pyproject.toml`.

## Repository structure

- `atlas/` — orchestration, policy, memory, evaluators and runtime core.
- `scripts/` — bounded execution, marketplace and operational entry points.
- `.github/workflows/` — CI and scheduled production orchestration.
- `config/` — versioned production policy and configuration.
- `benchmarks/` — deterministic business benchmark cases.
- `tests/` — unit and regression tests.
- `results/` — generated evidence/state snapshots that are explicitly persisted when required.
- `docs/maturity/` — versioned maturity assessments and remediation evidence.

## Revenue and cost accounting

`results/monetization.json` distinguishes confirmed revenue from potential rewards. Net profit is reported only when all material cost components are known. Otherwise `net_profit_eur` is `null` and the missing cost components are listed explicitly.

## Contributions and bounty clarification

**An issue in this repository is not a paid bounty.** A contribution is payable only if the repository owner explicitly marks the issue as a paid bounty and states the reward, payment terms and acceptance conditions. Words such as “bounty”, “reward” or “cash” inside internal ATLAS issues do not create a payment obligation.

See `CONTRIBUTING.md` and `SECURITY.md` before submitting external changes.
