from __future__ import annotations
from typing import Any, Dict

class BaselineAgent:
    name = "baseline"

    def run(self, workflow: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if workflow == "import_cost":
            return self._import_cost(payload)
        if workflow == "supplier_qualification":
            return self._supplier(payload)
        raise ValueError(f"Workflow inconnu: {workflow}")

    def _import_cost(self, p: Dict[str, Any]) -> Dict[str, Any]:
        quantity_kg = float(p.get("quantity_kg", 0))
        fob_total = float(p.get("fob_total_eur", 0))
        freight = float(p.get("freight_eur", 0))
        insurance = float(p.get("insurance_eur", 0))
        duty_rate = float(p.get("duty_rate", 0))
        customs_base = fob_total + freight + insurance
        duty = customs_base * duty_rate
        landed = customs_base + duty
        per_kg = landed / quantity_kg if quantity_kg else None
        return {"status":"calculated","incoterm":p.get("incoterm","FOB"),"landed_cost_eur":round(landed,2),"cost_per_kg_eur":round(per_kg,4) if per_kg is not None else None,"missing_fields":[]}

    def _supplier(self, p: Dict[str, Any]) -> Dict[str, Any]:
        evidence = p.get("evidence", [])
        risk = "low" if len(evidence) >= 2 else "medium"
        return {"decision":"qualified" if evidence else "review","risk":risk,"missing_documents":[],"evidence_count":len(evidence)}

class GuardedAgent(BaselineAgent):
    name = "guarded_v1"

    def _import_cost(self, p: Dict[str, Any]) -> Dict[str, Any]:
        required = ["incoterm","quantity_kg","fob_total_eur","freight_eur","insurance_eur","duty_rate"]
        missing = [k for k in required if k not in p or p[k] in (None, "")]
        if missing:
            return {"status":"blocked","missing_fields":missing,"reason":"insufficient_data"}
        if p["incoterm"] not in {"FOB","CIF","EXW"}:
            return {"status":"blocked","missing_fields":[],"reason":"invalid_incoterm"}
        if float(p["quantity_kg"]) <= 0:
            return {"status":"blocked","missing_fields":[],"reason":"invalid_quantity"}
        return super()._import_cost(p)

    def _supplier(self, p: Dict[str, Any]) -> Dict[str, Any]:
        required_docs = set(p.get("required_documents", ["registration","bank_details","quality_certificate"]))
        provided = set(p.get("provided_documents", []))
        missing = sorted(required_docs - provided)
        evidence = p.get("evidence", [])
        primary_sources = [e for e in evidence if e.get("type") == "primary"]
        contradictions = p.get("contradictions", [])
        decision = "review" if contradictions or len(primary_sources) < 2 or missing else "qualified"
        risk_points = len(missing) + 2 * len(contradictions) + max(0, 2 - len(primary_sources))
        risk = "high" if risk_points >= 4 else "medium" if risk_points >= 1 else "low"
        return {"decision":decision,"risk":risk,"missing_documents":missing,"evidence_count":len(evidence),"primary_source_count":len(primary_sources),"contradictions":contradictions}
