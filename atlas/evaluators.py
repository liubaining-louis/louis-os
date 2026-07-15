from __future__ import annotations
from math import isclose
from typing import Any, Dict
from .models import Evaluation

def evaluate_import_cost(output: Dict[str, Any], expected: Dict[str, Any]) -> Evaluation:
    checks: Dict[str, bool] = {"status": output.get("status") == expected["status"]}
    if expected["status"] == "blocked":
        checks["missing_fields"] = set(expected.get("missing_fields", [])).issubset(set(output.get("missing_fields", [])))
        critical = output.get("status") != "blocked"
    else:
        checks["landed_cost"] = isclose(float(output.get("landed_cost_eur", -1)), float(expected["landed_cost_eur"]), abs_tol=0.02)
        checks["cost_per_kg"] = isclose(float(output.get("cost_per_kg_eur", -1)), float(expected["cost_per_kg_eur"]), abs_tol=0.0002)
        checks["incoterm"] = output.get("incoterm") == expected.get("incoterm")
        critical = False
    errors = [f"check_failed:{k}" for k, ok in checks.items() if not ok]
    return Evaluation(sum(checks.values()) / len(checks), all(checks.values()), checks, errors, critical)

def evaluate_supplier(output: Dict[str, Any], expected: Dict[str, Any]) -> Evaluation:
    checks = {"decision": output.get("decision") == expected["decision"], "risk": output.get("risk") == expected["risk"], "missing_documents": set(output.get("missing_documents", [])) == set(expected.get("missing_documents", []))}
    errors = [f"check_failed:{k}" for k, ok in checks.items() if not ok]
    critical = expected["decision"] != "qualified" and output.get("decision") == "qualified"
    return Evaluation(sum(checks.values()) / len(checks), all(checks.values()), checks, errors, critical)

def evaluate(workflow: str, output: Dict[str, Any], expected: Dict[str, Any]) -> Evaluation:
    if workflow == "import_cost": return evaluate_import_cost(output, expected)
    if workflow == "supplier_qualification": return evaluate_supplier(output, expected)
    raise ValueError(workflow)
