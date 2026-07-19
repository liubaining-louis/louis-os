"""Verified operational state exposed to the Louis OS chat.

Only local, versioned artefacts and runtime metadata are used. Missing evidence is
reported explicitly instead of being guessed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _count_jsonl(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def snapshot() -> dict[str, Any]:
    money = _read_json(RESULTS / "monetization.json")
    experiments = _count_jsonl(RESULTS / "monetization_experiments.jsonl")
    evidence = _count_jsonl(RESULTS / "evidence.jsonl")

    return {
        "identity": "Louis OS / ATLAS",
        "project": os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814"),
        "runtime": "Cloud Run chat with Firestore memory",
        "master_mission": {
            "issue": 77,
            "title": "Entraînement ATLAS — test réel de monétisation multi-domaines",
            "objective": "Obtenir des revenus réels hors charbon par des expériences légales, mesurées et prouvées.",
            "state": "open",
        },
        "monetization": {
            "revenue_received_eur": money.get("revenue_received", 0),
            "weighted_pipeline_eur": money.get("weighted_pipeline", 0),
            "hours_invested": money.get("hours_invested", 0),
            "outreach_sent": money.get("outreach_sent", 0),
            "qualified_replies": money.get("qualified_replies", 0),
            "conversions": money.get("conversions", 0),
            "updated_at": money.get("updated_at"),
            "note": money.get("note", "Aucune note disponible"),
            "recorded_experiments": experiments,
            "recorded_evidence_items": evidence,
        },
        "verified_capabilities": [
            "chat web indépendant de ChatGPT",
            "historique et mémoire permanente Firestore",
            "déploiement Cloud Run par GitHub Actions",
            "infrastructure de worker VM préparée",
            "tableau de bord de monétisation déployé",
        ],
        "not_yet_verified": [
            "revenu encaissé",
            "première expérience réelle de monétisation avec preuve",
            "worker autonome H24 confirmé en fonctionnement",
            "action externe exécutée depuis ce chat",
        ],
        "guardrails": [
            "ne jamais déclarer une action ou un revenu sans preuve",
            "confirmation explicite pour paiements, contrats, suppressions et engagements juridiques",
            "cybersécurité uniquement sur périmètre explicitement autorisé",
            "aucune activité charbon dans la mission de monétisation #77",
        ],
    }


def prompt_context() -> str:
    state = snapshot()
    return json.dumps(state, ensure_ascii=False, indent=2)
