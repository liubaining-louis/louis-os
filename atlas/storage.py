from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .runner import ROOT


class MissionStore:
    def save(self, mission_id: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def get(self, mission_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError


class LocalMissionStore(MissionStore):
    def __init__(self) -> None:
        self.root = ROOT / "results" / "missions"

    def save(self, mission_id: str, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{mission_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, mission_id: str) -> dict[str, Any] | None:
        path = self.root / f"{mission_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self.root.glob("*.json")
        ]
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return records[:limit]


class FirestoreMissionStore(MissionStore):
    def __init__(self) -> None:
        from google.cloud import firestore

        self.client = firestore.Client()
        self.collection = self.client.collection(
            os.environ.get("FIRESTORE_MISSIONS_COLLECTION", "missions")
        )

    def save(self, mission_id: str, payload: dict[str, Any]) -> None:
        self.collection.document(mission_id).set(payload)

    def get(self, mission_id: str) -> dict[str, Any] | None:
        snapshot = self.collection.document(mission_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        query = self.collection.order_by(
            "created_at", direction="DESCENDING"
        ).limit(limit)
        return [doc.to_dict() for doc in query.stream()]


def get_mission_store() -> MissionStore:
    backend = os.environ.get("MISSION_STORE", "local").strip().lower()
    if backend == "firestore":
        return FirestoreMissionStore()
    return LocalMissionStore()
