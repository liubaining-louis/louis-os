# Real-world opportunity sources

Louis OS can now collect structured opportunity signals from external HTTPS JSON endpoints before passing them to `AutonomousOpportunityDiscovery`.

## Safety boundary

`HttpJsonOpportunitySource` is read-only and performs only bounded GET requests. Each endpoint must:

- use HTTPS;
- match an explicit host allowlist;
- return JSON;
- stay within the configured response-size limit;
- complete within the configured timeout;
- provide numeric scores between 0 and 1, subsequently validated by the discovery gate.

The source adapter does not contact prospects, purchase products, publish content or execute any commercial action. Existing AVB approval gates remain responsible for external actions.

## Expected JSON shape

```json
{
  "items": [
    {
      "source_id": "signal-001",
      "source_url": "https://evidence.example/item/001",
      "title": "Opportunity title",
      "problem": "Observed customer problem",
      "target_customer": "Customer segment",
      "proposed_offer": "Bounded offer to validate",
      "expected_value": 0.8,
      "autonomy": 0.9,
      "learning_value": 0.8,
      "speed": 0.7,
      "human_dependency": 0.2,
      "cost": 0.2,
      "risk": 0.3
    }
  ]
}
```

A top-level JSON list is accepted as well. Signals then flow through evidence validation, autonomy/risk gates, deduplication, ranking and the bounded venture cycle.
