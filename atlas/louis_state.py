"""Verified operational state exposed to the Louis OS chat.

Versioned artefacts provide the baseline; Firestore supplies live worker state when
available. Missing evidence is reported explicitly instead of being guessed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")


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


def _runtime_state() -> dict[str, Any]:
    try:
        snap = firestore.Client(project=PROJECT_ID).collection("louis_runtime").document("current").get()
        return snap.to_dict() if snap.exists else {}
    except Exception as exc:
        return {"worker_status": "unknown", "runtime_read_error": type(exc).__name__}


def snapshot() -> dict[str, Any]:
    money = _read_json(RESULTS / "monetization.json")
    experiments = _count_jsonl(RESULTS / "monetization_experiments.jsonl")
    evidence = _count_jsonl(RESULTS / "evidence.jsonl")
    runtime = _runtime_state()
    worker_verified = bool(runtime.get("worker_verified"))

    verified_capabilities = [
        "chat web indépendant de ChatGPT",
        "historique et mémoire permanente Firestore",
        "déploiement Cloud Run par GitHub Actions",
        "tableau de bord de monétisation déployé",
    ]
    if worker_verified:
        verified_capabilities.append("worker autonome actif avec cycles enregistrés dans Firestore")
    else:
        verified_capabilities.append("infrastructure de worker VM préparée")

    not_yet_verified = [
        "revenu encaissé",
        "première expérience réelle de monétisation avec preuve d'exécution externe",
        "action externe exécutée depuis ce chat",
    ]
    if not worker_verified:
        not_yet_verified.append("worker autonome H24 confirmé en fonctionnement")

    return {
        "identity": "Louis OS / ATLAS",
        "project": PROJECT_ID,
        "runtime": "Cloud Run chat with Firestore memory and live worker state",
        "master_mission": {
            "issue": 77,
            "title": "Entraînement ATLAS — test réel de monétisation multi-domaines",
            "objective": "Obtenir des revenus réels hors charbon par des expériences légales, mesurées et prouvées.",
            "state": "open",
        },
        "autonomous_worker": {
            "status": runtime.get("worker_status", "not_verified"),
            "verified": worker_verified,
            "last_cycle_at": runtime.get("last_cycle_at"),
            "last_cycle_status": runtime.get("last_cycle_status"),
            "sources_checked": runtime.get("sources_checked", 0),
            "opportunities_qualified": runtime.get("opportunities_qualified", 0),
            "actions_submitted": runtime.get("actions_submitted", 0),
            "top_candidate": runtime.get("top_candidate"),
            "next_action": runtime.get("next_action", "Await first verified worker cycle"),
            "runtime_read_error": runtime.get("runtime_read_error"),
        },
        "monetization": {
            "revenue_received_eur": runtime.get("revenue_confirmed_eur", money.get("revenue_received", 0)),
            "weighted_pipeline_eur": money.get("weighted_pipeline", 0),
            "hours_invested": money.get("hours_invested", 0),
            "outreach_sent": money.get("outreach_sent", 0),
            "qualified_replies": money.get("qualified_replies", 0),
            "conversions": money.get("conversions", 0),
            "updated_at": runtime.get("last_cycle_at", money.get("updated_at")),
            "note": money.get("note", "Aucune note disponible"),
            "recorded_experiments": experiments,
            "recorded_evidence_items": evidence,
        },
        "verified_capabilities": verified_capabilities,
        "not_yet_verified": not_yet_verified,
        "guardrails": [
            "ne jamais déclarer une action ou un revenu sans preuve",
            "confirmation explicite pour paiements, contrats, suppressions et engagements juridiques",
            "cybersécurité uniquement sur périmètre explicitement autorisé",
            "aucune activité charbon dans la mission de monétisation #77",
            "aucune soumission liée à un compte, KYC ou engagement externe sans validation explicite",
        ],
    }


def prompt_context() -> str:
    return json.dumps(snapshot(), ensure_ascii=False, indent=2, default=str)
