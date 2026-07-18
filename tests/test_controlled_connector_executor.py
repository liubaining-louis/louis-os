from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas.controlled_connector_executor import ConnectorOperation, ControlledConnectorExecutor


class Adapter:
    def __init__(self, *, read_only=True, fail_once=False):
        self.read_only = read_only
        self.fail_once = fail_once
        self.calls = 0

    def execute(self, operation):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise RuntimeError("temporary connector error")
        return f"ref://{operation.operation_id}"


class ControlledConnectorExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = ControlledConnectorExecutor(maximum_operations=5, maximum_attempts=2)

    def test_executes_read_operations_automatically(self):
        result = self.executor.execute(
            "b1",
            [ConnectorOperation("w1", "web_read", {"query": "industrial sourcing"}, "auto_execute")],
            web_adapter=Adapter(),
            gmail_adapter=Adapter(),
        )
        self.assertEqual(result.completed, 1)

    def test_blocks_unapproved_gmail_draft(self):
        result = self.executor.execute(
            "b1",
            [ConnectorOperation("d1", "gmail_create_draft", {"to": "buyer@example.com"}, "requires_approval")],
            web_adapter=Adapter(),
            gmail_adapter=Adapter(read_only=False),
        )
        self.assertEqual(result.approval_required, 1)

    def test_executes_approved_draft_once(self):
        adapter = Adapter(read_only=False)
        operation = ConnectorOperation("d1", "gmail_create_draft", {"to": "buyer@example.com"}, "requires_approval")
        result = self.executor.execute(
            "b1", [operation], web_adapter=Adapter(), gmail_adapter=adapter, approved_operation_ids=["d1"]
        )
        self.assertEqual(result.completed, 1)
        duplicate = self.executor.execute(
            "b2", [operation], web_adapter=Adapter(), gmail_adapter=adapter, previously_completed=["d1"], approved_operation_ids=["d1"]
        )
        self.assertEqual(duplicate.duplicates, 1)

    def test_retries_transient_connector_failure(self):
        adapter = Adapter(fail_once=True)
        result = self.executor.execute(
            "b1",
            [ConnectorOperation("g1", "gmail_read", {"query": "newer_than:1d"}, "auto_execute")],
            web_adapter=Adapter(),
            gmail_adapter=adapter,
        )
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.records[0].attempts, 2)

    def test_isolates_permanent_failure(self):
        class Broken(Adapter):
            def execute(self, operation):
                raise RuntimeError("permanent failure")

        result = self.executor.execute(
            "b1",
            [ConnectorOperation("w1", "web_read", {}, "auto_execute")],
            web_adapter=Broken(),
            gmail_adapter=Adapter(),
        )
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.records[0].attempts, 2)

    def test_rejects_non_read_only_read_adapter(self):
        with self.assertRaises(ValueError):
            self.executor.execute(
                "b1",
                [ConnectorOperation("w1", "web_read", {}, "auto_execute")],
                web_adapter=Adapter(read_only=False),
                gmail_adapter=Adapter(),
            )

    def test_enforces_operation_quota(self):
        operations = [ConnectorOperation(f"w{i}", "web_read", {}, "auto_execute") for i in range(6)]
        with self.assertRaises(ValueError):
            self.executor.execute("b1", operations, web_adapter=Adapter(), gmail_adapter=Adapter())

    def test_writes_auditable_artifact(self):
        result = self.executor.execute(
            "b1",
            [ConnectorOperation("w1", "web_read", {}, "auto_execute")],
            web_adapter=Adapter(),
            gmail_adapter=Adapter(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connector_execution.json"
            self.executor.write(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["connector_execution"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
