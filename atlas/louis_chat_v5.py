"""Louis OS web chat with Firestore memory, verified state and safe web research."""
from __future__ import annotations

import json
import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from google import genai
from google.cloud import firestore

from atlas.louis_state import prompt_context, snapshot
from atlas.web_gateway import research

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
PORT = int(os.getenv("PORT", "8080"))
MODEL = os.getenv("LOUIS_CHAT_MODEL", "gemini-2.5-flash")
HISTORY_LIMIT = int(os.getenv("LOUIS_HISTORY_LIMIT", "24"))
MEMORY_LIMIT = int(os.getenv("LOUIS_MEMORY_LIMIT", "40"))

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
    return [{"role": str(x.get("role", "user")), "text": str(x.get("text", "")), "created_at": str(x.get("created_at", ""))} for x in rows]


def _save(session_id: str, role: str, text: str, channel: str = "web") -> None:
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
    return [{"id": d.id, "category": str(d.to_dict().get("category", "general")), "text": str(d.to_dict().get("text", "")), "updated_at": str(d.to_dict().get("updated_at", ""))} for d in docs]


def _remember(text: str, category: str = "general", source: str = "user") -> str:
    memory_id = uuid.uuid4().hex
    _firestore().collection("louis_permanent_memory").document(memory_id).set({
        "text": text[:8000], "category": category[:80] or "general", "source": source,
        "created_at": _now(), "updated_at": _now(), "active": True,
    })
    return memory_id


def _needs_web(message: str) -> bool:
    text = message.lower()
    markers = (
        "recherche sur internet", "cherche sur internet", "va sur internet", "sur le web",
        "recherche web", "trouve-moi", "trouve moi", "actuellement", "aujourd'hui",
        "dernières nouvelles", "derniere nouvelle", "vérifie en ligne", "verifie en ligne",
    )
    return any(marker in text for marker in markers)


def _save_web_evidence(session_id: str, payload: dict[str, Any]) -> None:
    _firestore().collection("louis_web_evidence").add({
        "session_id": session_id,
        "query": payload.get("query", ""),
        "searched_at": payload.get("searched_at", _now()),
        "results": payload.get("results", []),
        "errors": payload.get("errors", []),
    })


def _reply(session_id: str, user_text: str) -> str:
    _save(session_id, "user", user_text)
    web_context = "- aucune recherche web déclenchée"
    if _needs_web(user_text):
        try:
            web = research(user_text, limit=5, fetch_top=3)
            _save_web_evidence(session_id, web)
            condensed = {
                "searched_at": web.get("searched_at"),
                "results": web.get("results", []),
                "pages": [
                    {"title": p.get("title"), "url": p.get("url"), "text": str(p.get("text", ""))[:5000]}
                    for p in web.get("pages", [])
                ],
                "errors": web.get("errors", []),
            }
            web_context = json.dumps(condensed, ensure_ascii=False, indent=2)
        except Exception as exc:
            web_context = f"Recherche web tentée mais indisponible: {type(exc).__name__}: {exc}"

    history = _history(session_id)
    memories = _memories()
    transcript = "\n".join(f"{m['role']}: {m['text']}" for m in history)
    memory_text = "\n".join(f"- [{m['category']}] {m['text']}" for m in memories)
    prompt = f"""Tu es Louis OS / ATLAS, le système autonome personnel de Louis.
Réponds en français, à la première personne, de façon opérationnelle et honnête.
Distingue toujours vérifié, préparé, en attente et non vérifié.
N'invente jamais une action, une recherche, une source ou un revenu.
Quand un contexte web est fourni, cite les URLs pertinentes dans ta réponse et précise la date de recherche.
Les actions financières, juridiques, d'envoi externe, de suppression ou irréversibles exigent une confirmation explicite.

ÉTAT OPÉRATIONNEL VÉRIFIÉ:
{prompt_context()}

MÉMOIRE PERMANENTE:
{memory_text or '- aucune mémoire enregistrée'}

RÉSULTATS DE RECHERCHE WEB POUR CE MESSAGE:
{web_context}

CONVERSATION RÉCENTE:
{transcript}
"""
    try:
        result = _client().models.generate_content(model=MODEL, contents=prompt)
        answer = (result.text or "").strip() or "Je n'ai pas pu produire de réponse exploitable."
    except Exception as exc:
        answer = f"Je suis joignable, mais mon moteur IA est momentanément indisponible: {type(exc).__name__}."
    _save(session_id, "assistant", answer)
    return answer


PAGE = """<!doctype html><html lang=fr><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Louis OS</title><style>
body{margin:0;background:#0b1020;color:#eef2ff;font-family:system-ui}main{max-width:780px;margin:auto;padding:14px}.card{background:#151c31;border:1px solid #293451;border-radius:18px;padding:15px}.top{display:flex;justify-content:space-between;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:#42d392;display:inline-block}.tabs{display:flex;gap:8px;margin:10px 0}.tabs button{flex:1}.log{height:58vh;overflow:auto;padding:8px 0}.m{padding:11px 14px;border-radius:15px;margin:8px 0;white-space:pre-wrap}.u{background:#315efb;margin-left:12%}.a{background:#222c47;margin-right:12%}.row{display:flex;gap:8px}input,textarea,button{font:inherit;border-radius:12px;border:1px solid #3b4767;padding:12px;background:#0f1628;color:#fff}textarea{flex:1;resize:none}button{background:#315efb;border:0;font-weight:700}.muted{color:#9aa7c7;font-size:13px}.hidden{display:none}.memory{padding:9px;border-bottom:1px solid #293451}</style></head>
<body><main><div class=card><div class=top><h2>Louis OS</h2><span><i class=dot></i> en ligne</span></div><div class=muted>Console ATLAS · mémoire Firestore · recherche web sécurisée</div>
<div class=tabs><button onclick=showChat()>Chat</button><button onclick=showMemory()>Mémoire</button><button onclick=newSession()>Nouvelle session</button></div>
<section id=chat><div id=log class=log></div><div class=row><textarea id=msg rows=2 placeholder='Écrire à Louis OS...'></textarea><button onclick=send()>Envoyer</button></div></section>
<section id=memory class=hidden><div class=row><input id=memtext style='flex:1' placeholder='Information à retenir'><button onclick=remember()>Mémoriser</button></div><div id=memlist></div></section></div></main>
<script>const log=document.getElementById('log'),msg=document.getElementById('msg'),chat=document.getElementById('chat'),memory=document.getElementById('memory'),memlist=document.getElementById('memlist');let sid=localStorage.louisSid||crypto.randomUUID();localStorage.louisSid=sid;
function headers(){return {'Content-Type':'application/json'}}function add(t,c){let d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight}
async function load(){log.innerHTML='';let r=await fetch('/v1/history?session_id='+encodeURIComponent(sid));if(r.ok){let j=await r.json();(j.messages||[]).forEach(x=>add(x.text,x.role==='user'?'u':'a'))}}
async function send(){let t=msg.value.trim();if(!t)return;add(t,'u');msg.value='';try{let r=await fetch('/v1/chat',{method:'POST',headers:headers(),body:JSON.stringify({session_id:sid,message:t})});let j=await r.json();add(j.reply||j.error||'Erreur','a')}catch(e){add('Service indisponible','a')}}
async function loadMemory(){memlist.innerHTML='';let r=await fetch('/v1/memories');if(r.ok){let j=await r.json();(j.memories||[]).forEach(x=>{let d=document.createElement('div');d.className='memory';d.textContent='['+x.category+'] '+x.text;memlist.appendChild(d)})}}
async function remember(){let t=document.getElementById('memtext').value.trim();if(!t)return;await fetch('/v1/memories',{method:'POST',headers:headers(),body:JSON.stringify({text:t,category:'user'})});document.getElementById('memtext').value='';loadMemory()}
function showChat(){chat.classList.remove('hidden');memory.classList.add('hidden');load()}function showMemory(){chat.classList.add('hidden');memory.classList.remove('hidden');loadMemory()}function newSession(){sid=crypto.randomUUID();localStorage.louisSid=sid;log.innerHTML=''}msg.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});load();</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LouisChat/5.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/health", "/healthz"}:
            _json(self, 200, {"status": "ok", "service": "louis-chat", "web_search": True})
            return
        if parsed.path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/v1/history":
            sid = str(query.get("session_id", [""])[0])[:128]
            _json(self, 200, {"session_id": sid, "messages": _history(sid) if sid else []})
            return
        if parsed.path == "/v1/memories":
            _json(self, 200, {"memories": _memories(100)})
            return
        if parsed.path == "/v1/status":
            _json(self, 200, {"status": "online", "model": MODEL, "memory": "firestore", "web_search": "enabled", "state": snapshot()})
            return
        _json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        body = _read_json(self)
        if self.path == "/v1/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                _json(self, 400, {"error": "message_required"})
                return
            sid = str(body.get("session_id") or uuid.uuid4())[:128]
            _json(self, 200, {"session_id": sid, "reply": _reply(sid, message[:12000])})
            return
        if self.path == "/v1/search":
            query = str(body.get("query", "")).strip()
            if not query:
                _json(self, 400, {"error": "query_required"})
                return
            result = research(query, limit=5, fetch_top=3)
            _save_web_evidence(str(body.get("session_id") or "api"), result)
            _json(self, 200, result)
            return
        if self.path == "/v1/memories":
            text = str(body.get("text", "")).strip()
            if not text:
                _json(self, 400, {"error": "text_required"})
                return
            _json(self, 201, {"id": _remember(text, str(body.get("category", "general"))), "stored": True})
            return
        _json(self, 404, {"error": "not_found"})


def main() -> None:
    print(f"Louis Chat 5.0 listening on :{PORT} for project {PROJECT_ID}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
