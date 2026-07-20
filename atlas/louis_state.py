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


def _response_policy() -> dict[str, Any]:
    """Policy injected into every chat turn to prevent passive permission loops."""
    return {
        "mode": "initiative_first_result_driven",
        "default_behavior": [
            "infer the next useful step from the verified objective and current state",
            "choose and start the best low-risk reversible action without asking what to do",
            "when a capability is missing, identify and attempt the best available workaround",
            "when execution is impossible, produce a concrete implementation task instead of stopping at the limitation",
            "after failure, try another bounded strategy before escalating to the user",
            "report actions with evidence and distinguish attempted, prepared and verified outcomes",
        ],
        "forbidden_response_patterns": [
            "Que souhaites-tu que je fasse exactement ?",
            "J'ai besoin d'instructions claires et précises pour continuer.",
            "Je ne possède pas cette capacité, donc je m'arrête.",
        ],
        "human_confirmation_only_for": [
            "money movement or paid purchase",
            "contract, legal terms or binding commitment",
            "account creation, identity verification or KYC",
            "privileged credential or permission escalation",
            "destructive, irreversible or privacy-sensitive action",
            "action outside an explicitly supported and allow-listed connector",
        ],
        "response_contract": {
            "must_include": ["decision", "next concrete step", "evidence status"],
            "must_not_end_with": "an open-ended request for instructions when a safe next step can be inferred",
        },
    }


def snapshot() -> dict[str, Any]:
    money = _read_json(RESULTS / "monetization.json")
    experiments = _count_jsonl(RESULTS / "monetization_experiments.jsonl")
    evidence = _count_jsonl(RESULTS / "evidence.jsonl")
    runtime = _runtime_state()
    worker_verified = bool(runtime.get("worker_verified"))
    external_actions = int(
        runtime.get("external_actions_submitted", runtime.get("actions_submitted", 0)) or 0
    )
    verified_receipts = int(runtime.get("external_receipts_verified", 0) or 0)

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
    if external_actions:
        verified_capabilities.append("action externe soumise avec compteur runtime vérifié")
    if verified_receipts:
        verified_capabilities.append("reçu d'action externe vérifié")

    not_yet_verified = ["revenu encaissé"]
    if not external_actions:
        not_yet_verified.append("première action externe réellement soumise")
    if not verified_receipts:
        not_yet_verified.append("premier reçu vérifiable d'exécution externe")
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
        "response_policy": _response_policy(),
        "autonomous_worker": {
            "status": runtime.get("worker_status", "not_verified"),
            "verified": worker_verified,
            "policy_mode": runtime.get("autonomy_policy", runtime.get("policy_mode", "initiative_first_result_driven")),
            "waiting_for_instruction": bool(runtime.get("waiting_for_instruction", False)),
            "human_gate_pending": bool(runtime.get("human_gate_pending", False)),
            "requires_user_validation": bool(runtime.get("requires_user_validation", False)),
            "last_cycle_at": runtime.get("last_cycle_at", runtime.get("synced_at")),
            "last_cycle_status": runtime.get("last_cycle_status", runtime.get("execution_status")),
            "sources_checked": runtime.get("sources_checked", 0),
            "opportunities_qualified": runtime.get("opportunities_qualified", 0),
            "actions_submitted": external_actions,
            "external_receipts_verified": verified_receipts,
            "top_candidate": runtime.get("top_candidate"),
            "next_action": runtime.get("next_action", "Infer and execute the next safe, reversible step."),
            "runtime_read_error": runtime.get("runtime_read_error"),
        },
        "monetization": {
            "revenue_received_eur": runtime.get("revenue_confirmed_eur", money.get("revenue_received", 0)),
            "weighted_pipeline_eur": money.get("weighted_pipeline", 0),
            "hours_invested": money.get("hours_invested", 0),
            "outreach_sent": money.get("outreach_sent", 0),
            "qualified_replies": money.get("qualified_replies", 0),
            "conversions": money.get("conversions", 0),
            "updated_at": runtime.get("last_cycle_at", runtime.get("synced_at", money.get("updated_at"))),
            "note": money.get("note", "Aucune note disponible"),
            "recorded_experiments": experiments,
            "recorded_evidence_items": evidence,
        },
        "verified_capabilities": verified_capabilities,
        "not_yet_verified": not_yet_verified,
        "guardrails": [
            "ne jamais déclarer une action ou un revenu sans preuve",
            "confirmation explicite uniquement pour paiement, contrat, KYC, privilège, suppression, irréversibilité ou donnée sensible",
            "les actions faibles risques, réversibles et allow-listées avancent sans seconde permission",
            "cybersécurité uniquement sur périmètre explicitement autorisé",
            "aucune activité charbon dans la mission de monétisation #77",
            "une limite de capacité déclenche une stratégie alternative ou une tâche d'implémentation, pas une demande vague à l'utilisateur",
        ],
    }


def prompt_context() -> str:
    return json.dumps(snapshot(), ensure_ascii=False, indent=2, default=str)
