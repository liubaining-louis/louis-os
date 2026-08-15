# Transaction history formatter

Small dependency-free Python utility for turning blockchain transaction records into a readable Markdown table.

## Usage

```python
from transaction_formatter import format_transactions

print(format_transactions([
    {
        "hash": "0x1234...",
        "from": "0xabc...",
        "to": "0xdef...",
        "value": "5.25",
        "symbol": "USDC",
        "status": "confirmed",
        "timestamp": 1786773600,
    }
]))
```

The formatter supports common aliases such as `tx_hash`, `sender`, `recipient`, `amount`, and `created_at`; escapes Markdown separators; normalizes timestamps to UTC; shortens long hashes/addresses; and does not mutate input.

## Verify

```bash
cd deliverables/clawlancer_transaction_formatter
python -m unittest -v
```

No third-party dependencies are required.
