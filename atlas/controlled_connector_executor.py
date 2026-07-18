from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal, Protocol

OperationType = Literal["web_read", "gmail_read", "gmail_create_draft"]
Authorization = Literal["auto_execute", "requires_approval", "forbidden"]
ExecutionStatus = Literal["completed", "approval_required", "duplicate", "failed", "forbidden"]


@dataclass(frozen=True)
class ConnectorOperation:
    operation_id: str
    operation_type: OperationType
    payload: dict[str, str]
    authorization: Authorization

    def validate(self) -> None:
        if not self.operation_id.strip():
            raise ValueError("operation_id is required")
        if self.operation_type not in {"web_read", "gmail_read", "gmail_create_draft"}:
            raise ValueError("unsupported operation type")
        if self.operation_type == "gmail_create_draft" and self.authorization != "requires_approval":
            raise ValueError("Gmail draft creation requires approval")
        if self.operation_type in {"web_read", "gmail_read"} and self.authorization == "forbidden":
            raise ValueError("read operations cannot be declared forbidden")


@dataclass(frozen=True)
class ConnectorExecutionRecord:
    operation_id: str
    operation_type: OperationType
    status: ExecutionStatus
    attempts: int
    result_reference: str
    error: str


@dataclass(frozen=True)
class ConnectorExecutionBatch:
    batch_id: str
    completed: int
    approval_required: int
    duplicates: int
    failed: int
    forbidden: int
    records: tuple[ConnectorExecutionRecord, ...]


class ConnectorAdapter(Protocol):
    read_only: bool

    def execute(self, operation: ConnectorOperation) -> str: ...


class ControlledConnectorExecutor:
    """Execute bounded connector work with idempotency, approval gates and retries."""

    def __init__(self, *, maximum_operations: int = 25, maximum_attempts: int = 2) -> None:
        if maximum_operations <= 0 or maximum_attempts <= 0:
            raise ValueError("operation and attempt limits must be positive")
        self.maximum_operations = maximum_operations
        self.maximum_attempts = maximum_attempts

    def execute(
        self,
        batch_id: str,
        operations: Iterable[ConnectorOperation],
        *,
        web_adapter: ConnectorAdapter,
        gmail_adapter: ConnectorAdapter,
        previously_completed: Iterable[str] = (),
        approved_operation_ids: Iterable[str] = (),
    ) -> ConnectorExecutionBatch:
        if not batch_id.strip():
            raise ValueError("batch_id is required")
        items = tuple(operations)
        if len(items) > self.maximum_operations:
            raise ValueError("operation quota exceeded")
        completed_ids = set(previously_completed)
        approved_ids = set(approved_operation_ids)
        records: list[ConnectorExecutionRecord] = []

        for operation in items:
            operation.validate()
            if operation.operation_id in completed_ids:
                records.append(ConnectorExecutionRecord(operation.operation_id, operation.operation_type, "duplicate", 0, "", ""))
                continue
            if operation.authorization == "forbidden":
                records.append(ConnectorExecutionRecord(operation.operation_id, operation.operation_type, "forbidden", 0, "", "operation forbidden by policy"))
                continue
            if operation.authorization == "requires_approval" and operation.operation_id not in approved_ids:
                records.append(ConnectorExecutionRecord(operation.operation_id, operation.operation_type, "approval_required", 0, "", "explicit approval missing"))
                continue

            adapter = web_adapter if operation.operation_type == "web_read" else gmail_adapter
            if operation.operation_type in {"web_read", "gmail_read"} and not getattr(adapter, "read_only", False):
                raise ValueError("read connector adapter must be read-only")

            result_reference = ""
            error = ""
            attempts = 0
            status: ExecutionStatus = "failed"
            while attempts < self.maximum_attempts:
                attempts += 1
                try:
                    result_reference = adapter.execute(operation)
                    if not result_reference.strip():
                        raise RuntimeError("connector returned an empty result reference")
                    status = "completed"
                    completed_ids.add(operation.operation_id)
                    break
                except Exception as exc:  # adapter isolation boundary
                    error = str(exc)
            records.append(ConnectorExecutionRecord(operation.operation_id, operation.operation_type, status, attempts, result_reference, error))

        return ConnectorExecutionBatch(
            batch_id=batch_id,
            completed=sum(item.status == "completed" for item in records),
            approval_required=sum(item.status == "approval_required" for item in records),
            duplicates=sum(item.status == "duplicate" for item in records),
            failed=sum(item.status == "failed" for item in records),
            forbidden=sum(item.status == "forbidden" for item in records),
            records=tuple(records),
        )

    def write(self, result: ConnectorExecutionBatch, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "1.0", "connector_execution": asdict(result)}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
