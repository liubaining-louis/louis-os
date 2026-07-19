"""Louis OS chat v7: v6 capabilities plus adaptive Gemini, Qwen and Groq routing."""
from __future__ import annotations

from atlas import louis_chat_v6 as chat
from atlas.llm_router import RoutedClient, provider_status

_ROUTED_CLIENT = RoutedClient()


def _routed_client() -> RoutedClient:
    return _ROUTED_CLIENT


# Replace the single Gemini client used by v6 with a compatible routed client.
chat._client = _routed_client
chat.MODEL = "adaptive:gemini|qwen|groq"
chat.Handler.server_version = "LouisChat/7.0"

_original_snapshot = chat.snapshot


def _snapshot_with_router():
    state = _original_snapshot()
    state["llm_router"] = provider_status()
    return state


chat.snapshot = _snapshot_with_router


def main() -> None:
    print("Louis Chat 7.0 listening with adaptive Gemini/Qwen/Groq routing", flush=True)
    chat.ThreadingHTTPServer(("0.0.0.0", chat.PORT), chat.Handler).serve_forever()


if __name__ == "__main__":
    main()
