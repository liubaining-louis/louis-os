from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

@dataclass
class Case:
    id: str
    workflow: str
    input: Dict[str, Any]
    expected: Dict[str, Any]

@dataclass
class Evaluation:
    score: float
    passed: bool
    checks: Dict[str, bool]
    errors: List[str]
    critical_regression: bool = False

@dataclass
class RunRecord:
    run_id: str
    timestamp: str
    workflow: str
    case_id: str
    variant: str
    output: Dict[str, Any]
    evaluation: Evaluation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
