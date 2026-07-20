# Louis OS ↔ Codex mentor bridge

## Purpose

The bridge connects one dedicated Louis OS chat session to Codex without an OpenAI API key. Louis OS remains the primary orchestrator and model router. Codex is exposed only as a mentor that can read the paired history, talk to Louis OS, inspect pending mentor requests and attach a reply.

This does not connect a private Codex Desktop task transcript automatically. MCP gives Codex tools that operate on the paired Louis OS session when Codex is running. Continuous background mentoring requires a separately approved monitor or automation.

## Pairing and isolation

1. In the Louis OS chat, select **Connecter Codex**.
2. Louis OS creates a new dedicated session and a random pairing token.
3. The browser displays the token once and retains it locally for that session.
4. Firestore stores only the SHA-256 digest, the dedicated session identifier, timestamps and active state.
5. Pairings expire after 30 days by default and cannot access any other session.

Creating the dedicated session on the server prevents a client from attaching a token to an existing arbitrary chat identifier.

## MCP endpoint

- Transport: Streamable HTTP with JSON responses.
- URL: `https://<louis-os-chat-service>/mcp`.
- Authentication: `Authorization: Bearer <pairing token>`.
- Supported protocol versions: `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`.
- Cross-origin requests are rejected unless the origin is explicitly listed in `LOUIS_MCP_ALLOWED_ORIGINS`.

Tools:

- `get_louis_chat_history`: read the paired history;
- `send_message_to_louis`: send a message through Louis OS and its existing multi-model router;
- `list_pending_mentor_messages`: read requests queued for Codex;
- `reply_to_mentor_message`: attach one idempotent mentor reply.

The tools cannot select another session, reveal the pairing token, modify IAM, deploy, send email, make payments or merge code.

## Configure Codex Desktop

No administrator rights are required.

1. Save the displayed pairing token in the user environment variable `LOUIS_CHAT_MCP_TOKEN`.
2. Open **Settings → MCP servers → Add server**.
3. Choose **Streamable HTTP** and use the production `/mcp` URL.
4. Configure the bearer token environment variable as `LOUIS_CHAT_MCP_TOKEN`.
5. Save and restart Codex.

Equivalent project-scoped configuration for a trusted repository:

```toml
[mcp_servers.louis_os]
url = "https://<louis-os-chat-service>/mcp"
bearer_token_env_var = "LOUIS_CHAT_MCP_TOKEN"
```

Do not put the pairing token in Git, documentation, shell history, `http_headers`, screenshots or chat messages.

## Chat workflow

- Use **Louis** to obtain an immediate answer from the Louis OS router.
- Use **Codex** to enqueue a mentor request.
- When Codex is active, ask it to use `list_pending_mentor_messages`, then `reply_to_mentor_message`.
- The Louis OS page polls for completed mentor replies and displays each response once.

## Evidence and failure behavior

- Pairings: Firestore collection `louis_codex_pairings`.
- Requests and replies: `louis_codex_pairings/{token_digest}/messages`.
- Conflicting second replies are refused; replaying the exact reply is idempotent.
- Invalid, missing or expired tokens return HTTP 401.
- An invalid Origin returns HTTP 403.
- Deployment smoke tests require anonymous MCP rejection, successful authenticated initialization and exactly four advertised tools.

## Disable and rollback

- Remove the MCP server from Codex settings and delete the local `LOUIS_CHAT_MCP_TOKEN` variable.
- Set the pairing document `active` to `false` to revoke one pairing immediately.
- Roll back the Cloud Run revision or revert the bridge commit to remove the endpoint and UI controls.
