"""Real-time supervision dashboard for ATLAS monetization issue #77.

Usage: python -m atlas.monetization_dashboard
Data sources are deliberately file-based and auditable:
- results/monetization.json
- results/monetization_experiments.jsonl
- results/evidence.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    except (OSError, json.JSONDecodeError):
        pass
    return rows


def build_snapshot(root: Path = ROOT) -> dict[str, Any]:
    ledger = _json(root / "results" / "monetization.json", {})
    experiments = _jsonl(root / "results" / "monetization_experiments.jsonl")
    evidence = _jsonl(root / "results" / "evidence.jsonl")
    latest = experiments[-1] if experiments else {}

    received = float(ledger.get("revenue_received", 0) or 0)
    pipeline = float(ledger.get("weighted_pipeline", 0) or 0)
    hours = float(ledger.get("hours_invested", 0) or 0)
    sent = int(ledger.get("outreach_sent", 0) or 0)
    replies = int(ledger.get("qualified_replies", 0) or 0)
    conversions = int(ledger.get("conversions", 0) or 0)

    activity = []
    for item in experiments[-20:] + evidence[-20:]:
        activity.append({
            "time": item.get("timestamp") or item.get("created_at") or "unknown",
            "type": item.get("type") or item.get("domain") or "evidence",
            "summary": item.get("summary") or item.get("action") or item.get("decision") or "Evidence recorded",
            "proof": item.get("proof") or item.get("source") or item.get("id"),
        })
    activity.sort(key=lambda row: str(row["time"]), reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": latest.get("stage") or latest.get("status") or "idle",
        "mission": latest.get("title") or latest.get("opportunity") or "Waiting for first verified experiment",
        "domain": latest.get("domain") or "unassigned",
        "metrics": {
            "revenue_received": received,
            "weighted_pipeline": pipeline,
            "revenue_per_hour": received / hours if hours else 0,
            "outreach_sent": sent,
            "qualified_replies": replies,
            "conversions": conversions,
            "reply_rate": replies / sent if sent else 0,
            "conversion_rate": conversions / sent if sent else 0,
            "hours_invested": hours,
        },
        "current": {
            "next_action": latest.get("next_action") or "Launch and prove the first monetization action",
            "blocker": latest.get("blocker") or "No verified blocker recorded",
            "decision": latest.get("decision") or "continue",
            "expected_hourly_revenue": float(latest.get("expected_hourly_revenue", 0) or 0),
            "probability": float(latest.get("probability", 0) or 0),
        },
        "activity": activity[:30],
        "integrity": {
            "experiment_count": len(experiments),
            "evidence_count": len(evidence),
            "data_is_empty": not ledger and not experiments,
        },
    }


HTML = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ATLAS Live Monetization</title><style>
:root{--bg:#07111f;--panel:#0d1b2d;--panel2:#12233a;--text:#eef5ff;--muted:#8da2bd;--accent:#57e6b1;--warn:#ffc857}*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;background:radial-gradient(circle at top right,#17355e 0,#07111f 42%);color:var(--text)}main{max-width:1440px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.brand h1{margin:0;font-size:27px}.brand p{margin:5px 0;color:var(--muted)}.live{display:flex;gap:9px;align-items:center;background:#0c2a25;border:1px solid #1a5a4d;padding:9px 13px;border-radius:999px}.dot{width:9px;height:9px;background:var(--accent);border-radius:50%;box-shadow:0 0 12px var(--accent)}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid #203752;border-radius:17px;padding:18px;box-shadow:0 12px 30px #0004}.metric b{font-size:28px;display:block;margin-top:9px}.label{color:var(--muted);font-size:13px}.wide{grid-column:span 2}.full{grid-column:1/-1}.status{font-size:20px;margin:8px 0}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#173b36;color:var(--accent);font-size:12px}.row{display:flex;justify-content:space-between;gap:15px;padding:11px 0;border-bottom:1px solid #21364d}.row:last-child{border:0}.small{font-size:12px;color:var(--muted)}.timeline{max-height:430px;overflow:auto}.proof{color:var(--accent);word-break:break-all}.empty{border-color:#66572d;color:var(--warn)}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.wide{grid-column:span 2}}@media(max-width:560px){main{padding:14px}.grid{grid-template-columns:1fr}.wide,.full{grid-column:span 1}.top{align-items:flex-start;gap:12px;flex-direction:column}}
</style></head><body><main><div class="top"><div class="brand"><h1>ATLAS · Live Monetization</h1><p>Issue maître #77 · données vérifiables uniquement</p></div><div class="live"><span class="dot"></span><span id="updated">Connexion…</span></div></div><section class="grid"><div class="card metric"><span class="label">Revenu encaissé</span><b id="revenue">—</b></div><div class="card metric"><span class="label">Pipeline pondéré</span><b id="pipeline">—</b></div><div class="card metric"><span class="label">Revenu réel / heure</span><b id="rph">—</b></div><div class="card metric"><span class="label">Conversion</span><b id="conversion">—</b></div><div class="card wide"><span class="label">Mission en cours</span><div class="status" id="mission">—</div><span class="pill" id="stage">—</span> <span class="pill" id="domain">—</span></div><div class="card wide"><span class="label">Décision et prochaine action</span><div class="row"><span>Décision</span><b id="decision">—</b></div><div class="row"><span>Prochaine action</span><b id="next">—</b></div><div class="row"><span>Blocage</span><b id="blocker">—</b></div></div><div class="card wide"><span class="label">Entonnoir</span><div class="row"><span>Actions sortantes</span><b id="sent">0</b></div><div class="row"><span>Réponses qualifiées</span><b id="replies">0</b></div><div class="row"><span>Conversions</span><b id="conversions">0</b></div><div class="row"><span>Taux de réponse</span><b id="replyRate">0%</b></div></div><div class="card wide"><span class="label">Intégrité des preuves</span><div class="row"><span>Expériences</span><b id="experiments">0</b></div><div class="row"><span>Preuves</span><b id="evidence">0</b></div><div class="row"><span>Probabilité actuelle</span><b id="probability">0%</b></div><div class="row"><span>Revenu horaire espéré</span><b id="expected">0 €</b></div></div><div class="card full"><span class="label">Journal d’activité</span><div class="timeline" id="activity"></div></div></section></main><script>
const eur=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(Number(n||0)),pct=n=>`${(Number(n||0)*100).toFixed(1)} %`,set=(id,v)=>document.getElementById(id).textContent=v;async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'}),d=await r.json(),m=d.metrics,c=d.current;set('updated','Actualisé '+new Date(d.generated_at).toLocaleTimeString());set('revenue',eur(m.revenue_received));set('pipeline',eur(m.weighted_pipeline));set('rph',eur(m.revenue_per_hour));set('conversion',pct(m.conversion_rate));set('mission',d.mission);set('stage',d.status);set('domain',d.domain);set('decision',c.decision);set('next',c.next_action);set('blocker',c.blocker);set('sent',m.outreach_sent);set('replies',m.qualified_replies);set('conversions',m.conversions);set('replyRate',pct(m.reply_rate));set('experiments',d.integrity.experiment_count);set('evidence',d.integrity.evidence_count);set('probability',pct(c.probability));set('expected',eur(c.expected_hourly_revenue));document.getElementById('activity').innerHTML=d.activity.length?d.activity.map(x=>`<div class="row"><div><b>${x.summary}</b><div class="small">${x.time} · ${x.type}</div>${x.proof?`<div class="small proof">Preuve: ${x.proof}</div>`:''}</div></div>`).join(''):'<div class="row empty">Aucune action prouvée pour le moment.</div>'}catch(e){set('updated','Hors ligne')}}refresh();setInterval(refresh,10000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            payload, content_type = HTML.encode(), "text/html; charset=utf-8"
        elif self.path.startswith("/api/status"):
            payload, content_type = json.dumps(build_snapshot()).encode(), "application/json; charset=utf-8"
        elif self.path == "/healthz":
            payload, content_type = b'{"status":"ok"}', "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("ATLAS_DASHBOARD_LOGS") == "1":
            super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    args = parser.parse_args()
    print(f"ATLAS monetization dashboard: http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
