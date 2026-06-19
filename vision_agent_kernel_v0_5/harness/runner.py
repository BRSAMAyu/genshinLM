"""Scenario runner + default scorer."""
from __future__ import annotations

from harness.core import (
    Environment,
    JsonDict,
    Policy,
    Scenario,
    ScenarioResult,
    Scorer,
    StepRecord,
)


class GoalReachedScorer:
    """Default scorer: success/failure come from the environment's ``info``.

    The environment reports ``info["success"]`` and ``info["failure_code"]`` on
    the terminal step. Score is 1.0 on success, else a shaped partial credit from
    ``info["progress"]`` (0..1) if the environment provides it.
    """

    def score(
        self,
        scenario: Scenario,
        trace: list[StepRecord],
        last_info: JsonDict,
        done: bool,
        steps: int,
    ) -> ScenarioResult:
        success = bool(last_info.get("success", False))
        if success:
            failure_code: str | None = None
            reason = "objective reached"
            score = 1.0
        else:
            failure_code = last_info.get("failure_code") or ("timeout" if not done else "unknown")
            reason = last_info.get("reason", failure_code)
            score = float(last_info.get("progress", 0.0))
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            passed=success,
            score=score,
            steps=steps,
            failure_code=failure_code,
            reason=reason,
            metrics=dict(last_info.get("metrics", {})),
            tags=scenario.tags,
        )


class ScenarioRunner:
    """Drives one scenario: reset → act/step loop → score.

    Termination is by environment ``done``, ``scenario.max_steps``, or wall-clock
    ``scenario.timeout_sec`` (checked via the injected monotonic ``clock``).
    """

    def __init__(
        self,
        environment: Environment,
        policy: Policy,
        scorer: Scorer | None = None,
        *,
        clock=None,
        recorder=None,
    ) -> None:
        self._env = environment
        self._policy = policy
        self._scorer = scorer or GoalReachedScorer()
        if clock is None:
            import time
            clock = time.perf_counter
        self._clock = clock
        self._recorder = recorder

    def run(self, scenario: Scenario) -> ScenarioResult:
        obs = self._env.reset(scenario)
        self._policy.reset(scenario)
        trace: list[StepRecord] = []
        start = self._clock()
        done = False
        last_info: JsonDict = {}
        steps = 0

        for step in range(scenario.max_steps):
            if self._clock() - start > scenario.timeout_sec:
                last_info = {"success": False, "failure_code": "timeout", "reason": "wall-clock timeout"}
                break
            action = self._policy.act(obs)
            next_obs, done, info = self._env.step(action)
            trace.append(StepRecord(step=step, observation=obs, action=action, info=info))
            steps = step + 1
            last_info = info
            obs = next_obs
            if done:
                break
        else:
            # max_steps exhausted without done
            last_info = {**last_info, "success": bool(last_info.get("success", False))}
            if not last_info.get("success"):
                last_info = {**last_info, "failure_code": last_info.get("failure_code") or "max_steps", "reason": "max steps exhausted"}

        result = self._scorer.score(scenario, trace, last_info, done, steps)
        if self._recorder is not None:
            ref = self._recorder.record(scenario, trace, result)
            result = ScenarioResult(
                scenario_id=result.scenario_id, passed=result.passed, score=result.score,
                steps=result.steps, failure_code=result.failure_code, reason=result.reason,
                metrics=result.metrics, tags=result.tags, trace_ref=ref,
            )
        return result
