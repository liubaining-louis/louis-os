# Global Cash Promoter Service

This service implements the Global Cash Promoter functionality as a standalone module that can be called by existing workflows.

## Functionality

- Searches fresh open GitHub bounty/reward issues globally
- Inspects authoritative provider evidence in comments (Algora/Opire or documented funded receipt)
- Extracts reward amount and active attempt count where available
- Rejects saturated (>5 active attempts), stale, unsafe, KYC/spend/signature-gated, or unverifiable payout tasks
- Favors $1–$100 bounded Python/JS/TS/Go/docs/data/research tasks
- Maintains target shortlist of 8, max 10
- Outputs results to `results/global_cash_shortlist.json`

## Dependencies

- Python 3.11+
- PyGithub>=1.59.0
- requests>=2.31.0

## Usage

```bash
python services/global_cash_promoter/service.py
```

## Integration

This service is designed to be called by the existing `.github/workflows/global-cash-promoter.yml` workflow. The workflow has been modified to simply trigger this service rather than implementing complex logic directly.

## Output Format

The service outputs a JSON file at `results/global_cash_shortlist.json` with the following structure:

```json
{
  "generated_at": "2023-11-15T12:34:56.789123",
  "shortlist": [
    {
      "id": 12345678,
      "number": 42,
      "title": "Example bounty task",
      "url": "https://github.com/user/repo/issues/42",
      "repo": "user/repo",
      "created_at": "2023-10-01T12:00:00Z",
      "updated_at": "2023-11-10T08:30:00Z",
      "reward_amount": 50.0,
      "reward_currency": "USD",
      "provider": "algora",
      "receipt_url": "https://example.com/receipt",
      "active_attempts": 2,
      "labels": ["python", "bounty"]
    }
  ],
  "count": 1
}
```
