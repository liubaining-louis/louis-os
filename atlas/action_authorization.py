from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Literal

AuthorizationDecision = Literal["auto_execute", "requires_approval", "forbidden"]
ActionScope = Literal["internal", "external"]


@dataclass(frozen=True)
class ProposedAction:
    action_id: str
    action_type: str
    scope: ActionScope
    estimated_cost_score: float
    human_dependency: float
    reversible: bool
    evidence_references: tuple[str, ...]

    def validate(self) -> None:
        if not self.action_id.strip() or not self.action_type.strip():
            raise ValueError("action_id and action_type are required")
        if self.scope not in {"internal", "external"}:
            raise ValueError("scope must be internal or external")
        for name in ("estimated_cost_score", "human_dependency"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not self.evidence_references:
            raise ValueError("action evidence references are required")


@dataclass(frozen=True)
class AuthorizationResult:
    action_id: str
    decision: AuthorizationDecision
    reasons: tuple[str, ...]


class ActionAuthorizationGate:
    """Classify proposed actions without executing them."""

    def __init__(
        self,
        *,
        maximum_auto_cost_score: float = 0.10,
        maximum_auto_human_dependency: float = 0.10,
        forbidden_action_types: Iterable[str] = ("payment", "purchase", "contract_signature", "credential_change"),
    ) -> None:
        for value, name in (
            (maximum_auto_cost_score, "maximum_auto_cost_score"),
            (maximum_auto_human_dependency, "maximum_auto_human_dependency"),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        self.maximum_auto_cost_score = maximum_auto_cost_score
        self.maximum_auto_human_dependency = maximum_auto_human_dependency
        self.forbidden_action_types = frozenset(item.strip() for item in forbidden_action_types if item.strip())

    def classify(self, action: ProposedAction) -> AuthorizationResult:
        action.validate()
        reasons: list[str] = []

        if action.action_type in self.forbidden_action_types:
            return AuthorizationResult(
                action_id=action.action_id,
                decision="forbidden",
                reasons=("action type is explicitly forbidden",),
            )

        if action.scope == "external":
            reasons.append("external side effect requires explicit approval")
        if not action.reversible:
            reasons.append("irreversible action requires explicit approval")
        if action.estimated_cost_score > self.maximum_auto_cost_score:
            reasons.append("estimated cost exceeds autonomous execution limit")
        if action.human_dependency > self.maximum_auto_human_dependency:
            reasons.append("human dependency exceeds autonomous execution limit")

        if reasons:
            return AuthorizationResult(
                action_id=action.action_id,
                decision="requires_approval",
                reasons=tuple(reasons),
            )

        return AuthorizationResult(
            action_id=action.action_id,
            decision="auto_execute",
            reasons=("bounded reversible internal action",),
        )

    def classify_many(self, actions: Iterable[ProposedAction]) -> list[AuthorizationResult]:
        return [self.classify(action) for action in actions]

    def write(self, results: Iterable[AuthorizationResult], output_path: str | Path) -> str:
        items = list(results)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "authorization_count": len(items),
            "authorizations": [asdict(item) for item in items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)
