"""Standalone Louis OS chat gateway for web and Telegram.

The service provides a mobile-friendly web UI, a JSON chat API, Firestore-backed
conversation history, and an optional Telegram webhook. Authentication is by a
shared bearer secret injected from Secret Manager.
"""

from __future__ import annotations

import html
import json
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from google.cloud import firestore
from google import genai

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
PORT = int(os.getenv("PORT", "8080"))
CHAT_KEY = os.getenv("LOUIS_CHAT_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "")
MODEL = os.getenv("LOUIS_CHAT_MODEL", "gemini-2.5-flash")

_db: firestore.Client | None = None
_ai: genai.Client | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _firestore() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID)
    return _db


def _client() -> genai.Client:
    global _ai
    if _ai is None:
        _ai = genai.Client()
    return _ai


def _authorized(headers: Any) -> bool:
    if not CHAT_KEY:
        return False
    return headers.get("Authorization", "") == f"Bearer {CHAT_KEY}"


def _json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    size = int(handler.headers.get("Content-Length", "0"))
    if size <= 0 or size > 1_000_000:
        return {}
    return json.loads(handler.rfile.read(size))


def _history(session_id: str, limit: int = 20) -> list[dict[str, str]]:
    docs = (
        _firestore().collection("louis_chat_sessions").document(session_id)
        .collection("messages").order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit).stream()
    )
    rows = [doc.to_dict() for doc in docs]
    rows.reverse()
    return [{"role": str(x.get("role", "user")), "text": str(x.get("text", ""))} for x in rows]


def _save(session_id: str, role: str, text: str, channel: str) -> None:
    root = _firestore().collection("louis_chat_sessions").document(session_id)
    root.set({"updated_at": _now(), "channel": channel}, merge=True)
    root.collection("messages").add({"role": role, "text": text, "channel": channel, "created_at": _now()})


def _reply(session_id: str, user_text: str, channel: str) -> str:
    _save(session_id, "user", user_text, channel)
    context = _history(session_id, 16)
    transcript = "\n".join(f"{m['role']}: {m['text']}" for m in context)
    prompt = (
        "Tu es Louis OS, assistant autonome de Louis. Réponds en français, de façon opérationnelle et honnête. "
        "Ne prétends jamais avoir exécuté une action sans preuve. Les actions financières, juridiques, d'envoi externe "
        "ou de suppression exigent une confirmation explicite. Voici la conversation:\n" + transcript
    )
    try:
        result = _client().models.generate_content(model=MODEL, contents=prompt)
        answer = (result.text or "").strip() or "Je n'ai pas pu produire de réponse exploitable."
    except Exception as exc:  # graceful degraded mode
        answer = f"Louis OS est joignable, mais le moteur IA est momentanément indisponible: {type(exc).__name__}."
    _save(session_id, "assistant", answer, channel)
    return answer


def _telegram_send(chat_id: str, text: str) -> None:
    if not TELEGRAM_TOKEN:
        return
    body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20):
        pass


PAGE = """<!doctype html><html lang=fr><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Louis OS</title><style>
body{margin:0;background:#0b1020;color:#eef2ff;font-family:system-ui}main{max-width:760px;margin:auto;padding:16px}.card{background:#151c31;border:1px solid #293451;border-radius:18px;padding:16px}.top{display:flex;justify-content:space-between;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:#42d392;display:inline-block}.log{height:58vh;overflow:auto;padding:10px 0}.m{padding:11px 14px;border-radius:15px;margin:8px 0;white-space:pre-wrap}.u{background:#315efb;margin-left:12%}.a{background:#222c47;margin-right:12%}.row{display:flex;gap:8px}input,textarea,button{font:inherit;border-radius:12px;border:1px solid #3b4767;padding:12px;background:#0f1628;color:#fff}textarea{flex:1;resize:none}button{background:#315efb;border:0;font-weight:700}.key{width:100%;box-sizing:border-box;margin:10px 0}.muted{color:#9aa7c7;font-size:13px}</style></head>
<body><main><div class=card><div class=top><h2>Louis OS</h2><span><i class=dot></i> en ligne</span></div><div class=muted>Interface indépendante de ChatGPT · historique Firestore</div>
<input id=key class=key type=password placeholder='Clé Louis OS'><div id=log class=log></div><div class=row><textarea id=msg rows=2 placeholder='Écrire à Louis OS...'></textarea><button onclick=send()>Envoyer</button></div></div></main>
<script>const log=document.getElementById('log'),key=document.getElementById('key'),msg=document.getElementById('msg');key.value=localStorage.louisKey||'';let sid=localStorage.louisSid||crypto.randomUUID();localStorage.louisSid=sid;
function add(t,c){let d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight}
async function send(){let t=msg.value.trim();if(!t)return;localStorage.louisKey=key.value;add(t,'u');msg.value='';try{let r=await fetch('/v1/chat',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+key.value},body:JSON.stringify({session_id:sid,message:t})});let j=await r.json();add(j.reply||j.error||'Erreur','a')}catch(e){add('Service indisponible','a')}}
msg.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}})</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LouisChat/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/healthz"}:
            _json(self, 200, {"status": "ok", "service": "louis-chat", "project": PROJECT_ID})
            return
        if self.path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        _json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/chat":
            if not _authorized(self.headers):
                _json(self, 401, {"error": "unauthorized"})
                return
            body = _read_json(self)
            message = str(body.get("message", "")).strip()
            if not message:
                _json(self, 400, {"error": "message_required"})
                return
            session_id = str(body.get("session_id") or uuid.uuid4())[:128]
            answer = _reply(session_id, message[:12000], "web")
            _json(self, 200, {"session_id": session_id, "reply": answer})
            return

        if self.path == "/telegram/webhook":
            body = _read_json(self)
            msg = body.get("message") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            text = str(msg.get("text", "")).strip()
            if not chat_id or not text or (TELEGRAM_CHAT_ID and chat_id != TELEGRAM_CHAT_ID):
                _json(self, 200, {"ok": True})
                return
            if text == "/status":
                answer = "Louis OS est en ligne. Canal Telegram opérationnel."
            else:
                answer = _reply(f"telegram-{chat_id}", text[:12000], "telegram")
            _telegram_send(chat_id, answer[:4000])
            _json(self, 200, {"ok": True})
            return

        _json(self, 404, {"error": "not_found"})


def main() -> None:
    print(f"Louis Chat listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
