"""Tests for the puzzle controller + puzzle-sim dogfood (Phase 4)."""
from __future__ import annotations

import pytest

from harness.batch import run_batch
from harness.core import Scenario, ScenarioResult
from harness.runner import ScenarioRunner
from harness.sim.puzzle_world import (
    PuzzlePolicy,
    PuzzleWorldEnv,
    make_puzzle_scenarios,
)
from puzzle.puzzle_controller import (
    PuzzleController,
    PuzzleControllerConfig,
    PuzzleView,
)


# --- controller contract ---------------------------------------------------


def test_proposes_when_no_target() -> None:
    c = PuzzleController()
    act = c.decide(PuzzleView(stage="explore", target=None))
    assert act.kind == "propose"


def test_refines_when_target_but_no_error() -> None:
    c = PuzzleController()
    act = c.decide(PuzzleView(stage="propose", target=(10.0, 10.0), error=None))
    assert act.kind == "refine"


def test_verifies_when_within_tolerance() -> None:
    c = PuzzleController()
    act = c.decide(PuzzleView(stage="refine", target=(10.0, 10.0),
                             error=(0.5, 0.5), tolerance=2.0))
    assert act.kind == "verify"  # error mag ~0.71 <= 2.0


def test_act_undershoots_remaining_error() -> None:
    c = PuzzleController(PuzzleControllerConfig(step_gain=0.5, min_step=0.5))
    act = c.decide(PuzzleView(stage="refine", target=(10.0, 10.0),
                              error=(10.0, 0.0), tolerance=2.0))
    assert act.kind == "act"
    # step = max(0.5*10, 0.5) = 5; scale 5/10 = 0.5 -> delta (5, 0)
    assert act.delta == pytest.approx((5.0, 0.0))


def test_stall_triggers_physical_search_then_escalates_when_disabled() -> None:
    # With search enabled (default), a stall switches to physical search (act probes).
    c = PuzzleController(PuzzleControllerConfig(stuck_no_progress_threshold=3))
    kinds = [c.decide(PuzzleView(stage="refine", target=(10.0, 0.0),
                                 error=(10.0, 0.0), tolerance=2.0)).kind for _ in range(6)]
    assert "act" in kinds  # entered physical search instead of dead-ending

    # With search disabled, a stall escalates to the caller (re-propose/recover).
    c2 = PuzzleController(PuzzleControllerConfig(stuck_no_progress_threshold=3,
                                                search_when_stalled=False))
    act = None
    for _ in range(6):
        act = c2.decide(PuzzleView(stage="refine", target=(10.0, 0.0),
                                   error=(10.0, 0.0), tolerance=2.0))
        if act.kind == "escalate":
            break
    assert act is not None and act.kind == "escalate"


def test_reset_clears_stall_tracking() -> None:
    c = PuzzleController(PuzzleControllerConfig(stuck_no_progress_threshold=2))
    for _ in range(2):
        c.decide(PuzzleView(error=(10.0, 0.0), target=(10.0, 0.0)))
    c.reset()
    act = c.decide(PuzzleView(error=(10.0, 0.0), target=(10.0, 0.0), tolerance=2.0))
    assert act.kind == "act"  # not escalating/searching right after reset


# --- dogfood: iterative convergence under measurement noise -----------------


def test_single_low_noise_puzzle_solves() -> None:
    scenario = make_puzzle_scenarios(1, seed=0)[0]
    scenario = Scenario(
        scenario_id="pz-easy", objective="align", tags=("puzzle",),
        setup={"start": [0.0, 0.0], "target": [20.0, 0.0],
               "tolerance": 2.0, "noise": 0.5, "max_attempts": 60, "seed": 1},
        max_steps=60,
    )
    result = ScenarioRunner(PuzzleWorldEnv(), PuzzlePolicy()).run(scenario)
    assert result.passed, f"{result.failure_code}: {result.reason}"


def test_survives_systematic_perpendicular_bias() -> None:
    # The realistic failure mode: a constant measurement offset perpendicular to
    # the approach axis. A pure error-gradient loop converges to a measure-zero
    # point that is actually `bias` away from truth and never solves. The
    # verify-stall -> physical-search fallback must still solve it.
    for bias in (2.0, 3.0, 4.0):
        passes = 0
        for seed in range(10):
            s = Scenario(
                scenario_id=f"bias-{bias}-{seed}", objective="align", tags=("puzzle",),
                setup={"start": [0.0, 0.0], "target": [20.0, 0.0], "tolerance": 1.5,
                       "noise": 0.3, "bias": [0.0, bias], "max_attempts": 120, "seed": seed},
                max_steps=120,
            )
            if ScenarioRunner(PuzzleWorldEnv(), PuzzlePolicy()).run(s).passed:
                passes += 1
        assert passes >= 9, f"perp-bias={bias}: only {passes}/10 solved"


def test_verify_stall_triggers_physical_search() -> None:
    # If the measurement repeatedly claims within-tolerance but the env never
    # confirms (biased), the controller must fall through to a physical probe.
    c = PuzzleController(PuzzleControllerConfig(max_unconfirmed_verifies=3))
    view = PuzzleView(stage="refine", target=(10.0, 0.0), error=(0.5, 0.0), tolerance=1.5)
    kinds = [c.decide(view).kind for _ in range(6)]
    assert kinds[:3] == ["verify", "verify", "verify"]
    assert "act" in kinds[3:]  # switched to physical search probe


def test_puzzle_batch_solve_rate() -> None:
    scenarios = make_puzzle_scenarios(40, seed=3)

    def run_one(s: Scenario) -> ScenarioResult:
        return ScenarioRunner(PuzzleWorldEnv(), PuzzlePolicy()).run(s)

    report = run_batch(scenarios, run_one)
    # Iterative convergence should solve the large majority even at high noise;
    # the residual cluster (high-noise timeouts) is the next find->fix target.
    assert report.pass_rate >= 0.7, (
        f"pass_rate={report.pass_rate:.2f}; clusters={[(c.signature, c.count) for c in report.clusters]}"
    )
