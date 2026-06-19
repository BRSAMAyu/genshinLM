"""Tests for interaction controller, interaction sim, and the commission cycle (Phase 3)."""
from __future__ import annotations

from harness.batch import run_batch
from harness.core import Scenario, ScenarioResult
from harness.runner import ScenarioRunner
from harness.sim.commission_world import (
    CommissionPolicy,
    DailyCommissionEnv,
    make_commission_scenarios,
)
from harness.sim.interaction_world import (
    InteractionPolicy,
    InteractionEnv,
    make_interaction_scenarios,
)
from interaction.interaction_controller import InteractionController, InteractionView


# --- controller priority contract ------------------------------------------


def test_claims_reward() -> None:
    c = InteractionController()
    assert c.decide(InteractionView(screen="reward", reward_ready=True)).kind == "claim"


def test_advances_dialogue() -> None:
    c = InteractionController()
    assert c.decide(InteractionView(screen="dialogue", dialogue_active=True)).kind == "advance"


def test_interacts_on_prompt() -> None:
    c = InteractionController()
    assert c.decide(InteractionView(screen="prompt", prompt="Talk to NPC")).kind == "interact"


def test_chooses_goal_aligned_option() -> None:
    c = InteractionController()
    act = c.decide(InteractionView(
        screen="choice", choices=("Decline", "Accept the commission"),
        objective_hint="accept the commission",
    ))
    assert act.kind == "choose" and act.choice_index == 1


def test_choice_fallback_prefers_positive_over_negative() -> None:
    c = InteractionController()
    act = c.decide(InteractionView(
        screen="choice", choices=("Leave", "Continue"), objective_hint="unrelated goal text",
    ))
    assert act.choice_index == 1  # 'Continue' is positive, 'Leave' negative


# --- interaction sim dogfood -----------------------------------------------


def test_single_interaction_completes() -> None:
    scenario = make_interaction_scenarios(1, seed=1)[0]
    result = ScenarioRunner(InteractionEnv(), InteractionPolicy()).run(scenario)
    assert result.passed, f"{result.failure_code}: {result.reason}"


def test_interaction_batch_high_success() -> None:
    scenarios = make_interaction_scenarios(40, seed=2)

    def run_one(s: Scenario) -> ScenarioResult:
        return ScenarioRunner(InteractionEnv(), InteractionPolicy()).run(s)

    report = run_batch(scenarios, run_one)
    assert report.pass_rate >= 0.95, (
        f"pass_rate={report.pass_rate:.2f}; clusters={[(c.signature, c.count) for c in report.clusters]}"
    )


# --- Phase 3 exit gate: full daily-commission cycle ------------------------


def test_single_commission_cycle_completes() -> None:
    scenario = make_commission_scenarios(1, seed=1)[0]
    result = ScenarioRunner(DailyCommissionEnv(), CommissionPolicy()).run(scenario)
    assert result.passed, f"{result.failure_code}: {result.reason}"


def test_commission_cycle_exit_gate() -> None:
    # ROADMAP Phase 3 exit gate: accept -> travel -> task -> turn-in -> reward >= 90%
    scenarios = make_commission_scenarios(30, seed=7)

    def run_one(s: Scenario) -> ScenarioResult:
        return ScenarioRunner(DailyCommissionEnv(), CommissionPolicy()).run(s)

    report = run_batch(scenarios, run_one)
    assert report.pass_rate >= 0.9, (
        f"pass_rate={report.pass_rate:.2f}; clusters={[(c.signature, c.count) for c in report.clusters]}"
    )
