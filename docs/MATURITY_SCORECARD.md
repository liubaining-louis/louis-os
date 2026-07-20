# Louis OS maturity scorecard

Louis OS maturity is measured by seven evidence-backed domains: architecture, autonomy, initiative, results, robustness, safety and memory. A score is not a reward for code volume. It records the strongest capability supported by the cited evidence class (`local`, `ci` or `production`).

Versioned assessments live in `docs/maturity/scorecards/`. Every assessment must contain all seven domains, a 0-10 integer score, a concise rationale and concrete evidence references.

## Promotion rule

`python -m atlas.maturity verify-history docs/maturity/scorecards` fails closed unless no domain decreases, at least one domain increases, each increase cites new evidence, and identifiers plus timestamps advance.

ATLAS CI requires a new scorecard in every pull request. The bootstrap PR adds the factual baseline and first candidate; later PRs must add exactly one assessment.

| Domain | Before | Candidate |
|---|---:|---:|
| Architecture | 8 | 8 |
| Autonomy | 7 | 7 |
| Initiative | 7 | 7 |
| Results | 4 | 4 |
| Robustness | 8 | 9 |
| Safety | 9 | 9 |
| Memory | 8 | 8 |

Overall maturity moves from `7.29` to `7.43`. The next prioritized weakness is **results**: demonstrate one repeated, externally verifiable outcome and feed its receipt into operational state without weakening safety.
