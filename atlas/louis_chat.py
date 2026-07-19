"""Independent Louis OS chat with durable Firestore memory.

Provides a mobile web chat, JSON API, persistent sessions, durable user memories,
conversation summaries and optional Telegram access. External or sensitive actions
remain confirmation-gated by the system prompt.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from google import genai
from google.cloud import firestore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
PORT = int(os.getenv("PORT", "8080"))
CHAT_KEY = os.getenv("LOUIS_CHAT_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "")
MODEL = os.getenv("LOUIS_CHAT_MODEL", "gemini-2.5-flash")
MEMORY_LIMIT = int(os.getenv("LOUIS_MEMORY_LIMIT", "40"))
HISTORY_LIMIT = int(os.getenv("LOUIS_HISTORY_LIMIT", "24"))

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
    return bool(CHAT_KEY) and headers.get("Authorization", "") == f"Bearer {CHAT_KEY}"


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
    try:
        return json.loads(handler.rfile.read(size))
    except json.JSONDecodeError:
        return {}


def _session_ref(session_id: str) -> firestore.DocumentReference:
    return _firestore().collection("louis_chat_sessions").document(session_id)


def _history(session_id: str, limit: int = HISTORY_LIMIT) -> list[dict[str, str]]:
    docs = (
        _session_ref(session_id)
        .collection("messages")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    rows = [doc.to_dict() for doc in docs]
    rows.reverse()
    return [
        {
            "role": str(row.get("role", "user")),
            "text": str(row.get("text", "")),
            "created_at": str(row.get("created_at", "")),
        }
        for row in rows
    ]


def _save(session_id: str, role: str, text: str, channel: str) -> None:
    now = _now()
    root = _session_ref(session_id)
    root.set({"updated_at": now, "channel": channel, "last_message": text[:500]}, merge=True)
    root.collection("messages").add({"role": role, "text": text, "channel": channel, "created_at": now})


def _memories(limit: int = MEMORY_LIMIT) -> list[dict[str, str]]:
    docs = (
        _firestore().collection("louis_permanent_memory")
        .order_by("updated_at", direction=firestore.Query.DESCENDING)
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    return [
        {
            "id": doc.id,
            "category": str(doc.to_dict().get("category", "general")),
            "text": str(doc.to_dict().get("text", "")),
            "updated_at": str(doc.to_dict().get("updated_at", "")),
        }
        for doc in docs
    ]


def _remember(text: str, category: str = "general", source: str = "user") -> str:
    memory_id = uuid.uuid4().hex
    _firestore().collection("louis_permanent_memory").document(memory_id).set(
        {"text": text[:8000], "category": category[:80] or "general", "source": source, "created_at": _now(), "updated_at": _now(), "active": True}
    )
    return memory_id


def _forget(memory_id: str) -> bool:
    ref = _firestore().collection("louis_permanent_memory").document(memory_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def _session_summary(session_id: str) -> str:
    snap = _session_ref(session_id).get()
    if not snap.exists:
        return ""
    return str((snap.to_dict() or {}).get("summary", ""))


def _update_summary(session_id: str) -> None:
    history = _history(session_id, 40)
    if len(history) < 8 or len(history) % 6 != 0:
        return
    transcript = "\n".join(f"{m['role']}: {m['text']}" for m in history)
    try:
        result = _client().models.generate_content(model=MODEL, contents="Résume cette conversation en français en moins de 180 mots, sans rien inventer.\n\n" + transcript)
        summary = (result.text or "").strip()
        if summary:
            _session_ref(session_id).set({"summary": summary, "summary_updated_at": _now()}, merge=True)
    except Exception:
        return


def _reply(session_id: str, user_text: str, channel: str) -> str:
    _save(session_id, "user", user_text, channel)
    history = _history(session_id)
    memories = _memories()
    summary = _session_summary(session_id)
    transcript = "\n".join(f"{m['role']}: {m['text']}" for m in history)
    memory_text = "\n".join(f"- [{m['category']}] {m['text']}" for m in memories)
    prompt = f"""Tu es Louis OS, assistant autonome de Louis.
Réponds en français, de manière opérationnelle, concise et honnête.
Ne prétends jamais avoir exécuté une action sans preuve vérifiable.
Les actions financières, juridiques, d'envoi externe, de suppression ou irréversibles exigent une confirmation explicite.
La mémoire permanente ci-dessous est une source de contexte, pas une autorisation d'action.

Mémoire permanente:
{memory_text or '- aucune mémoire enregistrée'}

Résumé de session:
{summary or '- aucun résumé'}

Conversation récente:
{transcript}
"""
    try:
        result = _client().models.generate_content(model=MODEL, contents=prompt)
        answer = (result.text or "").strip() or "Je n'ai pas pu produire de réponse exploitable."
    except Exception as exc:
        answer = f"Louis OS est joignable, mais le moteur IA est momentanément indisponible: {type(exc).__name__}."
    _save(session_id, "assistant", answer, channel)
    _update_summary(session_id)
    return answer


def _telegram_send(chat_id: str, text: str) -> None:
    if not TELEGRAM_TOKEN:
        return
    body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20):
        pass


PAGE = """<!doctype html><html lang=fr><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Louis OS</title><style>
body{margin:0;background:#0b1020;color:#eef2ff;font-family:system-ui}main{max-width:780px;margin:auto;padding:14px}.card{background:#151c31;border:1px solid #293451;border-radius:18px;padding:15px}.top{display:flex;justify-content:space-between;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:#42d392;display:inline-block}.tabs{display:flex;gap:8px;margin:10px 0}.tabs button{flex:1}.log{height:52vh;overflow:auto;padding:8px 0}.m{padding:11px 14px;border-radius:15px;margin:8px 0;white-space:pre-wrap}.u{background:#315efb;margin-left:12%}.a{background:#222c47;margin-right:12%}.row{display:flex;gap:8px}input,textarea,button{font:inherit;border-radius:12px;border:1px solid #3b4767;padding:12px;background:#0f1628;color:#fff}textarea{flex:1;resize:none}button{background:#315efb;border:0;font-weight:700}.key{flex:1}.muted{color:#9aa7c7;font-size:13px}.hidden{display:none}.memory{padding:9px;border-bottom:1px solid #293451}.auth{display:flex;gap:8px;margin:10px 0}.status{min-height:20px;margin-bottom:8px;font-size:14px}.ok{color:#42d392}.bad{color:#ff8080}</style></head>
<body><main><div class=card><div class=top><h2>Louis OS</h2><span><i class=dot></i> en ligne</span></div><div class=muted>Chat indépendant · mémoire permanente Firestore</div>
<div class=auth><input id=key class=key type=password placeholder='Clé Louis OS'><button id=validate onclick=validateKey()>Valider</button></div><div id=authStatus class=status>Clé non validée</div>
<div class=tabs><button onclick=showChat()>Chat</button><button onclick=showMemory()>Mémoire</button><button onclick=newSession()>Nouvelle session</button></div>
<section id=chat><div id=log class=log></div><div class=row><textarea id=msg rows=2 placeholder='Écrire à Louis OS...'></textarea><button onclick=send()>Envoyer</button></div></section>
<section id=memory class=hidden><div class=row><input id=memtext style='flex:1' placeholder='Information à retenir'><button onclick=remember()>Mémoriser</button></div><div id=memlist></div></section></div></main>
<script>const log=document.getElementById('log'),key=document.getElementById('key'),msg=document.getElementById('msg'),chat=document.getElementById('chat'),memory=document.getElementById('memory'),memlist=document.getElementById('memlist'),authStatus=document.getElementById('authStatus');key.value=localStorage.louisKey||'';let sid=localStorage.louisSid||crypto.randomUUID();localStorage.louisSid=sid;let authenticated=false;
function headers(){return {'Content-Type':'application/json','Authorization':'Bearer '+key.value.trim()}}
function setAuth(ok,text){authenticated=ok;authStatus.textContent=text;authStatus.className='status '+(ok?'ok':'bad');if(ok)localStorage.louisKey=key.value.trim()}
async function validateKey(){let k=key.value.trim();if(!k){setAuth(false,'Saisis la clé Louis OS');return}authStatus.textContent='Validation...';try{let r=await fetch('/v1/status',{headers:headers()});if(r.ok){setAuth(true,'Clé validée · accès autorisé');await load()}else{setAuth(false,'Clé incorrecte ou accès refusé')}}catch(e){setAuth(false,'Service indisponible')}}
function add(t,c){let d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight}
async function load(){if(!authenticated)return;log.innerHTML='';let r=await fetch('/v1/history?session_id='+encodeURIComponent(sid),{headers:headers()});if(r.ok){let j=await r.json();(j.messages||[]).forEach(x=>add(x.text,x.role==='user'?'u':'a'))}}
async function send(){if(!authenticated){setAuth(false,'Valide d’abord la clé');return}let t=msg.value.trim();if(!t)return;add(t,'u');msg.value='';try{let r=await fetch('/v1/chat',{method:'POST',headers:headers(),body:JSON.stringify({session_id:sid,message:t})});let j=await r.json();add(j.reply||j.error||'Erreur','a')}catch(e){add('Service indisponible','a')}}
async function loadMemory(){if(!authenticated){setAuth(false,'Valide d’abord la clé');return}memlist.innerHTML='';let r=await fetch('/v1/memories',{headers:headers()});if(r.ok){let j=await r.json();(j.memories||[]).forEach(x=>{let d=document.createElement('div');d.className='memory';d.textContent='['+x.category+'] '+x.text;memlist.appendChild(d)})}}
async function remember(){if(!authenticated){setAuth(false,'Valide d’abord la clé');return}let t=document.getElementById('memtext').value.trim();if(!t)return;await fetch('/v1/memories',{method:'POST',headers:headers(),body:JSON.stringify({text:t,category:'user'})});document.getElementById('memtext').value='';loadMemory()}
function showChat(){chat.classList.remove('hidden');memory.classList.add('hidden');load()}function showMemory(){chat.classList.add('hidden');memory.classList.remove('hidden');loadMemory()}function newSession(){sid=crypto.randomUUID();localStorage.louisSid=sid;log.innerHTML=''}
key.addEventListener('keydown',e=>{if(e.key==='Enter')validateKey()});msg.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});if(key.value)validateKey();</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LouisChat/2.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/health", "/healthz"}:
            _json(self, 200, {"status": "ok", "service": "louis-chat", "project": PROJECT_ID})
            return
        if parsed.path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not _authorized(self.headers):
            _json(self, 401, {"error": "unauthorized"})
            return
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/v1/history":
            session_id = str(query.get("session_id", [""])[0])[:128]
            _json(self, 200, {"session_id": session_id, "messages": _history(session_id) if session_id else []})
            return
        if parsed.path == "/v1/memories":
            _json(self, 200, {"memories": _memories(100)})
            return
        if parsed.path == "/v1/status":
            _json(self, 200, {"status": "online", "project": PROJECT_ID, "model": MODEL, "memory": "firestore"})
            return
        _json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path == "/telegram/webhook":
            body = _read_json(self)
            msg = body.get("message") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            text = str(msg.get("text", "")).strip()
            if not chat_id or not text or (TELEGRAM_CHAT_ID and chat_id != TELEGRAM_CHAT_ID):
                _json(self, 200, {"ok": True})
                return
            if text == "/status":
                answer = "Louis OS est en ligne. Mémoire permanente Firestore opérationnelle."
            elif text.startswith("/remember "):
                memory_id = _remember(text[10:].strip(), "telegram", "telegram")
                answer = f"Mémoire enregistrée: {memory_id[:8]}."
            else:
                answer = _reply(f"telegram-{chat_id}", text[:12000], "telegram")
            _telegram_send(chat_id, answer[:4000])
            _json(self, 200, {"ok": True})
            return
        if not _authorized(self.headers):
            _json(self, 401, {"error": "unauthorized"})
            return
        body = _read_json(self)
        if self.path == "/v1/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                _json(self, 400, {"error": "message_required"})
                return
            session_id = str(body.get("session_id") or uuid.uuid4())[:128]
            _json(self, 200, {"session_id": session_id, "reply": _reply(session_id, message[:12000], "web")})
            return
        if self.path == "/v1/memories":
            text = str(body.get("text", "")).strip()
            if not text:
                _json(self, 400, {"error": "text_required"})
                return
            memory_id = _remember(text, str(body.get("category", "general")), "web")
            _json(self, 201, {"id": memory_id, "stored": True})
            return
        if self.path == "/v1/forget":
            memory_id = str(body.get("id", "")).strip()
            deleted = _forget(memory_id) if memory_id else False
            _json(self, 200 if deleted else 404, {"deleted": deleted})
            return
        _json(self, 404, {"error": "not_found"})


def main() -> None:
    print(f"Louis Chat 2.1 listening on :{PORT} for project {PROJECT_ID}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
