# CSV automation demo

Run `python process_csv.py sample_input.csv output.csv --report report.json`. Existing destinations are refused. Only the name/email/company contact schema is supported. Invalid values and duplicates are reported, not silently discarded. UTF-8/BOM comma-separated input, 10 MB and 100,000 row limits. Email checks are syntactic, not mailbox verification. See the independent CSV delivery benchmark and contract in the repository.
