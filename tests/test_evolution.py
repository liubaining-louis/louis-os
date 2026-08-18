from atlas.evolution import ControlledEvolutionEngine, EvolutionProposal, EvolutionSignal


def proposal(*, reversible: bool = True, risk: str = "low") -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id="evo-001",
        problem="Revenue loop stalls after qualification",
        hypothesis="Prioritizing payment-path tasks improves conversion",
        change_scope=("atlas/task_scheduler.py",),
        reversible=reversible,
        estimated_risk=risk,
        created_at="2026-07-21T20:00:00+00:00",
    )


def test_promotes_only_measurable_improvement() -> None:
    engine = ControlledEvolutionEngine(promotion_threshold=0.02)
    result = engine.evaluate(
        proposal(),
        [
            EvolutionSignal("conversion", "revenue", 0.10, 0.13, weight=2),
            EvolutionSignal("reliability", "reliability", 0.99, 0.99),
        ],
        tests_passed=True,
        deterministic_checks_passed=True,
    )
    assert result.decision == "promote"
    assert result.weighted_improvement > 0.02
    assert result.regressions == ()


def test_rolls_back_on_any_guarded_regression() -> None:
    engine = ControlledEvolutionEngine()
    result = engine.evaluate(
        proposal(),
        [
            EvolutionSignal("revenue", "revenue", 100, 120),
            EvolutionSignal("reliability", "reliability", 0.99, 0.95),
        ],
        tests_passed=True,
        deterministic_checks_passed=True,
    )
    assert result.decision == "rollback"
    assert result.regressions == ("reliability",)


def test_rolls_back_when_tests_fail() -> None:
    engine = ControlledEvolutionEngine()
    result = engine.evaluate(
        proposal(),
        [EvolutionSignal("quality", "quality", 0.8, 0.9)],
        tests_passed=False,
        deterministic_checks_passed=True,
    )
    assert result.decision == "rollback"
    assert "test suite failed" in result.regressions


def test_holds_non_reversible_or_high_risk_change() -> None:
    engine = ControlledEvolutionEngine()
    assert engine.evaluate(
        proposal(reversible=False), [], tests_passed=True, deterministic_checks_passed=True
    ).decision == "hold"
    assert engine.evaluate(
        proposal(risk="high"), [], tests_passed=True, deterministic_checks_passed=True
    ).decision == "hold"


def test_holds_without_evidence() -> None:
    engine = ControlledEvolutionEngine()
    result = engine.evaluate(proposal(), [], tests_passed=True, deterministic_checks_passed=True)
    assert result.decision == "hold"
    assert result.regressions == ("no evaluation signals",)
