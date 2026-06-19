"""Tests for the trial-and-error harness core + navigation-sim dogfood."""
from __future__ import annotations

from harness.batch import cluster_failures, run_batch
from harness.core import Scenario, ScenarioResult, StepRecord
from harness.runner import GoalReachedScorer, ScenarioRunner
from harness.sim.nav_world import NavStackPolicy, NavWorldEnv, make_nav_scenarios
from harness.trace import TraceRecorder, read_trace


# --- core: clustering / batch / regression ---------------------------------


def _result(sid: str, passed: bool, code: str | None = None, tags=("nav",)) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=sid, passed=passed, score=1.0 if passed else 0.0,
        steps=10, failure_code=code, reason=code or "ok", tags=tags,
    )


def test_cluster_failures_groups_by_signature_and_sorts() -> None:
    results = [
        _result("a", False, "stuck"),
        _result("b", False, "stuck"),
        _result("c", False, "out_of_bounds"),
        _result("d", True),
    ]
    clusters = cluster_failures(results)
    assert clusters[0].signature == "stuck::nav"
    assert clusters[0].count == 2
    assert set(clusters[0].scenario_ids) == {"a", "b"}
    assert all("d" not in c.scenario_ids for c in clusters)  # passes excluded


def test_run_batch_computes_pass_rate_and_regressions() -> None:
    scenarios = [Scenario(scenario_id=f"s{i}", objective="o") for i in range(4)]
    # s0,s1 pass; s2,s3 fail
    outcomes = {"s0": True, "s1": True, "s2": False, "s3": False}

    def run_one(s: Scenario) -> ScenarioResult:
        return _result(s.scenario_id, outcomes[s.scenario_id], None if outcomes[s.scenario_id] else "x")

    baseline = {"s0": True, "s1": False, "s2": True, "s3": False}
    report = run_batch(scenarios, run_one, baseline=baseline)
    assert report.total == 4 and report.passed == 2
    assert report.pass_rate == 0.5
    assert "s2" in report.regressions  # passed in baseline, fails now
    assert "s1" in report.fixed        # failed in baseline, passes now


def test_trace_recorder_roundtrip(tmp_path) -> None:
    rec = TraceRecorder(tmp_path)
    scenario = Scenario(scenario_id="t1", objective="o")
    trace = [StepRecord(step=0, observation={"x": 1}, action={"forward": 1.0}, info={})]
    result = _result("t1", True)
    path = rec.record(scenario, trace, result)
    header, steps = read_trace(path)
    assert header["result"]["passed"] is True
    assert len(steps) == 1 and steps[0]["action"]["forward"] == 1.0


def test_runner_timeout_marks_failure() -> None:
    class _ForeverEnv:
        def reset(self, scenario): return {"t": 0.0}
        def step(self, action): return {"t": 0.0}, False, {"success": False}

    class _NoopPolicy:
        def reset(self, scenario): pass
        def act(self, obs): return {}

    clock = iter([0.0, 0.0, 100.0])  # third read exceeds timeout
    runner = ScenarioRunner(_ForeverEnv(), _NoopPolicy(), clock=lambda: next(clock))
    result = runner.run(Scenario(scenario_id="z", objective="o", max_steps=10, timeout_sec=1.0))
    assert not result.passed and result.failure_code == "timeout"


# --- dogfood: real pose+nav stack in the simulator -------------------------


def test_single_easy_navigation_succeeds() -> None:
    env = NavWorldEnv()
    policy = NavStackPolicy()
    runner = ScenarioRunner(env, policy)
    scenario = Scenario(
        scenario_id="easy", objective="reach target",
        setup={"start": [0.0, 0.0], "heading": 0.0, "target": [0.0, 25.0],
               "arrival_radius": 1.5, "speed": 5.0, "flow_noise": 0.02, "bounds": 200.0, "seed": 1},
        max_steps=400, timeout_sec=30.0, tags=("nav",),
    )
    result = runner.run(scenario)
    assert result.passed, f"expected arrival, got {result.failure_code}: {result.reason}"


def test_navigation_batch_reaches_target_majority() -> None:
    scenarios = make_nav_scenarios(20, seed=7, flow_noise=0.03)

    def run_one(s: Scenario) -> ScenarioResult:
        return ScenarioRunner(NavWorldEnv(), NavStackPolicy()).run(s)

    report = run_batch(scenarios, run_one)
    # The real Phase-0 nav loop should reach most targets under modest noise.
    assert report.pass_rate >= 0.7, (
        f"pass_rate={report.pass_rate:.2f}; clusters={[(c.signature, c.count) for c in report.clusters]}"
    )
