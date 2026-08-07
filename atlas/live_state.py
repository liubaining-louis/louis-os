from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "test-bot-499814")
COLLECTION = os.getenv("LOUIS_LIVE_STATE_COLLECTION", "louis_live")
DOCUMENT = os.getenv("LOUIS_LIVE_STATE_DOCUMENT", "current")


def read_live_state() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        from google.cloud import firestore

        snap = firestore.Client(project=PROJECT_ID).collection(COLLECTION).document(DOCUMENT).get()
        if not snap.exists:
            return {"available": False, "checked_at": checked_at, "error": "live_document_missing"}
        data = snap.to_dict() or {}
        data["available"] = True
        data["checked_at"] = checked_at
        return data
    except Exception as exc:
        return {"available": False, "checked_at": checked_at, "error": type(exc).__name__}


def live_prompt_context() -> str:
    return json.dumps(read_live_state(), ensure_ascii=False, indent=2, default=str)
