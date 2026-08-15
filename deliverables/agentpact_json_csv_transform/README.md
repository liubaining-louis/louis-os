# Tested JSON → CSV transform

Dependency-free Python utility that converts JSON object data to CSV and validates the generated output before reporting success.

## Supported input

- A JSON array of objects → one CSV row per object.
- A single JSON object → one CSV row.
- Missing keys are represented as empty cells.
- Nested dict/list values are stored as deterministic compact JSON strings.
- Columns use a stable alphabetical union of all row keys.

## Usage

```bash
python json_to_csv.py input.json output.csv
```

On success the command prints a JSON validation report containing the output row count and exact header. Invalid JSON, scalar top-level values, and non-object rows fail with a non-zero exit code.

## Tests

```bash
cd deliverables/agentpact_json_csv_transform
python -m unittest -v
```

The test suite covers missing fields, single-object input, nested values, empty arrays, invalid row types, invalid top-level values, and malformed JSON.
