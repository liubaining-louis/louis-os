"""Authenticated MCP bridge between a paired Louis OS chat and Codex."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol


SUPPORTED_PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
PAIRING_COLLECTION = "louis_codex_pairings"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token(value: str | None) -> str:
    if not value:
        return ""
    scheme, separator, token = value.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        return ""
    candidate = token.strip()
    return candidate if len(candidate) >= 32 else ""


class MentorBridgeStore(Protocol):
    def create_pairing(self, digest: str, session_id: str, created_at: str, expires_at: str) -> None: ...

    def resolve_pairing(self, digest: str) -> str | None: ...

    def queue_message(self, digest: str, text: str, created_at: str) -> dict[str, Any]: ...

    def list_messages(self, digest: str, limit: int) -> list[dict[str, Any]]: ...

    def reply_message(self, digest: str, message_id: str, text: str, replied_at: str) -> dict[str, Any]: ...


@dataclass
class MemoryMentorBridgeStore:
    pairings: dict[str, dict[str, str]] = field(default_factory=dict)
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def create_pairing(self, digest: str, session_id: str, created_at: str, expires_at: str) -> None:
        self.pairings[digest] = {"session_id": session_id, "expires_at": expires_at}
        self.messages.setdefault(digest, [])

    def resolve_pairing(self, digest: str) -> str | None:
        value = self.pairings.get(digest)
        if not value or value["expires_at"] <= utc_now():
            return None
        return value["session_id"]

    def queue_message(self, digest: str, text: str, created_at: str) -> dict[str, Any]:
        if digest not in self.pairings:
            raise PermissionError("invalid_pairing")
        message = {
            "message_id": uuid.uuid4().hex,
            "session_id": self.pairings[digest]["session_id"],
            "text": text,
            "status": "pending",
            "created_at": created_at,
            "reply": "",
            "replied_at": "",
        }
        self.messages[digest].append(message)
        return dict(message)

    def list_messages(self, digest: str, limit: int) -> list[dict[str, Any]]:
        if digest not in self.pairings:
            raise PermissionError("invalid_pairing")
        return [dict(item) for item in self.messages.get(digest, [])[-limit:]]

    def reply_message(self, digest: str, message_id: str, text: str, replied_at: str) -> dict[str, Any]:
        if digest not in self.pairings:
            raise PermissionError("invalid_pairing")
        for item in self.messages.get(digest, []):
            if item["message_id"] != message_id:
                continue
            if item["status"] == "replied":
                if item["reply"] != text:
                    raise ValueError("message_already_replied")
                return dict(item)
            item.update({"status": "replied", "reply": text, "replied_at": replied_at})
            return dict(item)
        raise KeyError("message_not_found")


class FirestoreMentorBridgeStore:
    def __init__(self, client: Any, collection_name: str = PAIRING_COLLECTION) -> None:
        self.collection = client.collection(collection_name)

    def _pairing(self, digest: str) -> Any:
        return self.collection.document(digest)

    def create_pairing(self, digest: str, session_id: str, created_at: str, expires_at: str) -> None:
        self._pairing(digest).set(
            {
                "session_id": session_id,
                "active": True,
                "created_at": created_at,
                "updated_at": created_at,
                "expires_at": expires_at,
            }
        )

    def resolve_pairing(self, digest: str) -> str | None:
        snapshot = self._pairing(digest).get()
        if not snapshot.exists:
            return None
        value = snapshot.to_dict() or {}
        if not value.get("active"):
            return None
        if str(value.get("expires_at", "")) <= utc_now():
            return None
        session_id = str(value.get("session_id", ""))
        return session_id or None

    def queue_message(self, digest: str, text: str, created_at: str) -> dict[str, Any]:
        session_id = self.resolve_pairing(digest)
        if not session_id:
            raise PermissionError("invalid_pairing")
        ref = self._pairing(digest).collection("messages").document()
        value = {
            "message_id": ref.id,
            "session_id": session_id,
            "text": text,
            "status": "pending",
            "created_at": created_at,
            "reply": "",
            "replied_at": "",
        }
        ref.set(value)
        return value

    def list_messages(self, digest: str, limit: int) -> list[dict[str, Any]]:
        if not self.resolve_pairing(digest):
            raise PermissionError("invalid_pairing")
        docs = (
            self._pairing(digest)
            .collection("messages")
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        values = [doc.to_dict() or {} for doc in docs]
        values.reverse()
        return values

    def reply_message(self, digest: str, message_id: str, text: str, replied_at: str) -> dict[str, Any]:
        if not self.resolve_pairing(digest):
            raise PermissionError("invalid_pairing")
        ref = self._pairing(digest).collection("messages").document(message_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError("message_not_found")
        value = snapshot.to_dict() or {}
        if value.get("status") == "replied":
            if value.get("reply") != text:
                raise ValueError("message_already_replied")
            return value
        value.update({"status": "replied", "reply": text, "replied_at": replied_at})
        ref.set(value, merge=True)
        return value


class MentorBridge:
    def __init__(
        self,
        store: MentorBridgeStore,
        history: Callable[[str, int], list[dict[str, str]]],
        louis_reply: Callable[[str, str], str],
    ) -> None:
        self.store = store
        self.history = history
        self.louis_reply = louis_reply

    def create_pairing(self) -> dict[str, str]:
        normalized = f"codex-{uuid.uuid4().hex}"
        token = secrets.token_urlsafe(32)
        created_at = utc_now()
        try:
            ttl_days = max(1, min(int(os.getenv("LOUIS_CODEX_PAIRING_TTL_DAYS", "30")), 90))
        except ValueError:
            ttl_days = 30
        expires_at = (datetime.fromisoformat(created_at) + timedelta(days=ttl_days)).isoformat()
        self.store.create_pairing(token_hash(token), normalized, created_at, expires_at)
        return {"session_id": normalized, "token": token, "expires_at": expires_at, "mcp_path": "/mcp"}

    def resolve(self, token: str) -> tuple[str, str]:
        if len(token) < 32:
            raise PermissionError("invalid_pairing")
        digest = token_hash(token)
        session_id = self.store.resolve_pairing(digest)
        if not session_id:
            raise PermissionError("invalid_pairing")
        return digest, session_id

    def queue(self, token: str, text: str) -> dict[str, Any]:
        digest, _ = self.resolve(token)
        message = text.strip()[:12000]
        if not message:
            raise ValueError("message_required")
        return self.store.queue_message(digest, message, utc_now())

    def messages(self, token: str, limit: int = 30) -> list[dict[str, Any]]:
        digest, _ = self.resolve(token)
        return self.store.list_messages(digest, max(1, min(limit, 100)))

    def rpc(self, token: str, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = str(request.get("method", ""))
        if method.startswith("notifications/"):
            return None
        if request.get("jsonrpc") != "2.0" or not method:
            return self._error(request_id, -32600, "Invalid Request")
        if method == "initialize":
            params = request.get("params") if isinstance(request.get("params"), dict) else {}
            requested = str(params.get("protocolVersion", ""))
            protocol = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            return self._result(
                request_id,
                {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "louis-os-mentor", "version": "1.0.0"},
                    "instructions": (
                        "Louis OS remains the primary orchestrator. This bridge is limited to one paired chat session. "
                        "Read pending mentor requests before replying; never claim an external action without evidence."
                    ),
                },
            )
        try:
            digest, session_id = self.resolve(token)
        except PermissionError:
            return self._error(request_id, -32001, "Invalid or expired pairing")
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self._tools()})
        if method != "tools/call":
            return self._error(request_id, -32601, "Method not found")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        name = str(params.get("name", ""))
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        try:
            if name == "get_louis_chat_history":
                limit = max(1, min(int(arguments.get("limit", 24)), 100))
                value: Any = {"session_id": session_id, "messages": self.history(session_id, limit)}
            elif name == "send_message_to_louis":
                message = str(arguments.get("message", "")).strip()[:12000]
                if not message:
                    raise ValueError("message_required")
                value = {"session_id": session_id, "reply": self.louis_reply(session_id, message)}
            elif name == "list_pending_mentor_messages":
                limit = max(1, min(int(arguments.get("limit", 30)), 100))
                messages = self.store.list_messages(digest, limit)
                value = {"session_id": session_id, "messages": [m for m in messages if m.get("status") == "pending"]}
            elif name == "reply_to_mentor_message":
                message_id = str(arguments.get("message_id", "")).strip()
                reply = str(arguments.get("reply", "")).strip()[:12000]
                if not message_id or not reply:
                    raise ValueError("message_id_and_reply_required")
                value = self.store.reply_message(digest, message_id, reply, utc_now())
            else:
                return self._tool_result(request_id, {"error": "unknown_tool"}, is_error=True)
        except (KeyError, PermissionError, ValueError) as exc:
            return self._tool_result(request_id, {"error": str(exc)}, is_error=True)
        return self._tool_result(request_id, value)

    @staticmethod
    def _result(request_id: Any, value: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @classmethod
    def _tool_result(cls, request_id: Any, value: Any, is_error: bool = False) -> dict[str, Any]:
        return cls._result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                "structuredContent": value,
                "isError": is_error,
            },
        )

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        return [
            {
                "name": "get_louis_chat_history",
                "title": "Read paired Louis OS chat history",
                "description": "Read recent messages from the one Louis OS chat session paired with this token.",
                "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
            },
            {
                "name": "send_message_to_louis",
                "title": "Send a message to Louis OS",
                "description": "Send a message to Louis OS in the paired session and return its model-routed reply.",
                "inputSchema": {"type": "object", "properties": {"message": {"type": "string", "maxLength": 12000}}, "required": ["message"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            },
            {
                "name": "list_pending_mentor_messages",
                "title": "List pending Codex mentor requests",
                "description": "List unanswered requests sent from the paired Louis OS chat to Codex.",
                "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
            },
            {
                "name": "reply_to_mentor_message",
                "title": "Reply as the Codex mentor",
                "description": "Attach a Codex mentor reply to one pending request in the paired Louis OS chat.",
                "inputSchema": {"type": "object", "properties": {"message_id": {"type": "string"}, "reply": {"type": "string", "maxLength": 12000}}, "required": ["message_id", "reply"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
            },
        ]
