"""Compatibility shim for directly executed scripts.

Production workers copy atlas/production_policy.py next to the runtime script. Local
and CI executions resolve this shim from scripts/ and reuse the canonical package
implementation.
"""
from atlas.production_policy import PolicyDecision, assert_external_action_allowed, evaluate_candidate, load_policy, preflight

__all__ = [
    "PolicyDecision",
    "assert_external_action_allowed",
    "evaluate_candidate",
    "load_policy",
    "preflight",
]
