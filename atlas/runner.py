from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
from .agents import BaselineAgent, GuardedAgent
from .evidence import EvidenceStore
from .evaluators import evaluate
from .models import Case, RunRecord

ROOT = Path(__file__).resolve().parents[1]
_CASE_FIELDS = {"id", "workflow", "input", "expected"}


def _normalize_case_payload(payload: dict) -> dict:
    """Normalize historical identifiers and retain only the MVP Case contract."""
    normalized = dict(payload)
    if "id" not in normalized and "case_id" in normalized:
        normalized["id"] = normalized["case_id"]
    return {key: normalized[key] for key in _CASE_FIELDS if key in normalized}


def _is_mvp_case_payload(payload: dict) -> bool:
    """Return true only for benchmark records compatible with ``Case``.

    The benchmarks tree also contains specialized schemas (for example
    engineering objectives). Those must be evaluated by their own runners
    rather than being passed accidentally to the MVP agent benchmark.
    """
    return _CASE_FIELDS.issubset(payload)


def load_cases() -> list[Case]:
    cases = []
    for path in sorted((ROOT / "benchmarks").glob("*/*.json")):
        payload = _normalize_case_payload(json.loads(path.read_text(encoding="utf-8")))
        if not _is_mvp_case_payload(payload):
            continue
        cases.append(Case(**payload))
    return cases


def run_all(clear: bool = True) -> dict:
    store = EvidenceStore(ROOT / "results" / "evidence.jsonl")
    if clear: store.clear()
    summary = {}
    for agent in [BaselineAgent(), GuardedAgent()]:
        records = []
        for case in load_cases():
            output = agent.run(case.workflow, case.input)
            ev = evaluate(case.workflow, output, case.expected)
            record = RunRecord(str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), case.workflow, case.id, agent.name, output, ev)
            store.append(record)
            records.append(record)
        summary[agent.name] = {
            "score": sum(r.evaluation.score for r in records) / len(records),
            "pass_rate": sum(r.evaluation.passed for r in records) / len(records),
            "critical_regressions": sum(r.evaluation.critical_regression for r in records),
        }
    b, g = summary["baseline"], summary["guarded_v1"]
    summary["promotion"] = {"candidate":"guarded_v1","promoted":g["score"] > b["score"] and g["pass_rate"] >= 0.8 and g["critical_regressions"] == 0,"score_delta":g["score"] - b["score"]}
    (ROOT / "results" / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
