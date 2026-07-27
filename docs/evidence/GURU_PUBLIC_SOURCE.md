# Guru public source evidence

Checked on 2026-07-27.

## Discovery surface

- Public jobs directory: `https://www.guru.com/d/jobs/`
- Pagination: `https://www.guru.com/d/jobs/pg/2/`
- Public cards expose title, job URL, fixed/hourly budget, quote count, send-before date, scope excerpt, employer spend and payment percentage.

## Payment protection and withdrawal

- SafePay: `https://www.guru.com/safepay/`
- Freelancer workflow: `https://www.guru.com/how-it-works-freelancer/`
- Official guidance says the employer can fund SafePay before work begins and lists PayPal, Payoneer, wire transfer and Direct Deposit where supported as withdrawal methods.

## Fail-closed policy

The adapter rejects jobs without a bounded public rate, future deadline, low quote count and strong public employer payment history. It also rejects physical/location-bound work, sensitive verification, manual-only restrictions, unsafe requests, tax/accounting/legal work, cold calling, commission-only work and long-term staffing.

No account, quote, agreement, KYC, payout setup, submission or revenue is created by public discovery.