# Cycle execution protocol

The production command bridge is triggered by opening an issue titled `Louis Command: ...`.

For the current cycle, Louis OS must:

- load issue #77 as source of truth;
- run `python scripts/execute_best_verified_candidate.py`;
- verify generated evidence;
- report either `deliverable_created` with workspace, manifest, receipt and SHA-256, or `no_authentic_executable_candidate`;
- keep external submissions and confirmed revenue unchanged unless external receipts exist.
