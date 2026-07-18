import json
import tempfile
import unittest
from pathlib import Path

from atlas.venture_runtime import (
    CeoAgent,
    JsonlVentureMemory,
    Opportunity,
    VentureDecisionEngine,
    VentureEdge,
    VentureEvent,
    VentureGraph,
    build_dry_run_artifact,
)


def opportunity(
    opportunity_id: str,
    *,
    expected_value: float = 0.7,
    autonomy: float = 0.8,
    learning_value: float = 0.7,
    speed: float = 0.6,
    human_dependency: float = 0.1,
    cost: float = 0.2,
    risk: float = 0.2,
) -> Opportunity:
    return Opportunity(
        opportunity_id=opportunity_id,
        title=f"Opportunity {opportunity_id}",
        problem="A verified recurring customer problem",
        target_customer="European industrial SME",
        proposed_offer="Automated evidence-backed sourcing brief",
        evidence_references=[f"evidence://{opportunity_id}"],
        expected_value=expected_value,
        autonomy=autonomy,
        learning_value=learning_value,
        speed=speed,
        human_dependency=human_dependency,
        cost=cost,
        risk=risk,
    )


class VentureRuntimeTests(unittest.TestCase):
    def test_decision_engine_ranks_best_opportunity_first(self):
        engine = VentureDecisionEngine()
        ranked = engine.rank(
            [
                opportunity("weak", expected_value=0.3, autonomy=0.4),
                opportunity("strong", expected_value=0.9, autonomy=0.95),
            ]
        )

        self.assertEqual(ranked[0].opportunity.opportunity_id, "strong")
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_opportunity_requires_evidence(self):
        candidate = opportunity("missing-evidence")
        object.__setattr__(candidate, "evidence_references", [])

        with self.assertRaisesRegex(ValueError, "evidence reference"):
            candidate.validate()

    def test_ceo_rejects_high_human_dependency_and_selects_autonomous_candidate(self):
        decision = CeoAgent().decide(
            [
                opportunity("manual", human_dependency=0.8, expected_value=1.0),
                opportunity("autonomous", human_dependency=0.05, expected_value=0.7),
            ]
        )

        self.assertEqual(decision.selected_opportunity_id, "autonomous")
        self.assertIn("manual", decision.rejection_reasons)
        self.assertFalse(decision.approval_required)

    def test_memory_is_append_only_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = JsonlVentureMemory(Path(tmpdir) / "venture.jsonl")
            memory.append(
                VentureEvent(
                    event_type="opportunity_observed",
                    venture_id="venture-1",
                    payload={"opportunity_id": "a"},
                    evidence_references=["evidence://a"],
                )
            )
            memory.append(
                VentureEvent(
                    event_type="asset_built",
                    venture_id="venture-1",
                    payload={"path": "artifacts/offer.md"},
                )
            )

            events = memory.read_all()
            self.assertEqual(
                [event.event_type for event in events],
                ["opportunity_observed", "asset_built"],
            )

    def test_result_event_requires_evidence(self):
        event = VentureEvent(event_type="result_recorded", venture_id="v", payload={"result": 1})
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            event.validate()

    def test_venture_graph_is_deterministic_and_rejects_missing_endpoints(self):
        graph = VentureGraph()
        graph.add_node("o1", "opportunity", title="A")
        graph.add_node("h1", "hypothesis", statement="B")
        graph.add_edge(VentureEdge("o1", "supports", "h1", ["evidence://a"]))
        graph.add_edge(VentureEdge("o1", "supports", "h1", ["evidence://a"]))

        data = graph.to_dict()
        self.assertEqual(len(data["edges"]), 1)

        with self.assertRaisesRegex(ValueError, "endpoints"):
            graph.add_edge(VentureEdge("unknown", "supports", "h1"))

    def test_dry_run_writes_executable_json_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates = [opportunity("a"), opportunity("b", expected_value=0.4)]
            engine = VentureDecisionEngine()
            ranked = engine.rank(candidates)
            decision = CeoAgent(engine).decide(candidates)
            target = Path(tmpdir) / "dry-run.json"

            artifact = build_dry_run_artifact("venture-1", decision, ranked, target)

            self.assertTrue(target.exists())
            loaded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(loaded, artifact)
            self.assertEqual(loaded["mode"], "dry_run")
            self.assertEqual(loaded["selected_opportunity_id"], "a")
            self.assertEqual(loaded["ranking"][0]["evidence_references"], ["evidence://a"])


if __name__ == "__main__":
    unittest.main()
