from __future__ import annotations
import html, json
from pathlib import Path
from .evidence import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]

def generate_report() -> Path:
    summary_path = ROOT / "results" / "summary.json"
    if not summary_path.exists():
        from .runner import run_all
        run_all()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = []
    for name in ("baseline", "guarded_v1"):
        x = summary[name]
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{x['score']:.1%}</td><td>{x['pass_rate']:.1%}</td><td>{x['critical_regressions']}</td></tr>")
    p = summary["promotion"]
    status = "PROMUE" if p["promoted"] else "REJETÉE"
    failures = [e for e in EvidenceStore(ROOT / "results" / "evidence.jsonl").read_all() if not e["evaluation"]["passed"]]
    fail_items = "".join(f"<li>{html.escape(x['variant'])} — {html.escape(x['case_id'])}</li>" for x in failures)
    doc = f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>ATLAS v2 Report</title></head><body><h1>ATLAS v2 — Rapport expérimental</h1><h2>Décision : guarded_v1 {status}</h2><p>Delta score : {p['score_delta']:+.1%}</p><table><tr><th>Variante</th><th>Score</th><th>Pass rate</th><th>Régressions</th></tr>{''.join(rows)}</table><h2>Échecs</h2><ul>{fail_items or '<li>Aucun</li>'}</ul></body></html>"""
    path = ROOT / "results" / "report.html"
    path.write_text(doc, encoding="utf-8")
    return path
