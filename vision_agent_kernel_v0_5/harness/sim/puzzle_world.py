"""Deterministic puzzle world — Phase 4 dogfood environment.

Models an alignment/placement puzzle (a movable piece that must reach a target
position) with measurement noise on the observed error. Because the observation
is noisy, the real :class:`~puzzle.puzzle_controller.PuzzleController` cannot
one-shot the target — it must iterate the propose→refine→act→verify loop,
undershooting each step and re-measuring, exactly the precision regime puzzles
live in.

The PROPOSE step is abstracted behind a deterministic stand-in here. This sim is
a *reference oracle* for the controller's convergence behaviour, not the live
stack: the controller is not yet wired to VisionLLMProvider or any capsule, and
the measured solve rate is offline-sim-only (not live-game performance). Wiring
the PROPOSE step to the cloud multimodal model + a real capsule is the separate
integration step that makes the live loop work.
"""
from __future__ import annotations

import random

from harness.core import JsonDict, Scenario
from puzzle.puzzle_controller import (
    PuzzleAction,
    PuzzleController,
    PuzzleView,
)


class PuzzleWorldEnv:
    """Implements the harness Environment protocol for alignment puzzles."""

    def __init__(self) -> None:
        self._pos = [0.0, 0.0]
        self._target: tuple[float, float] | None = None
        self._tolerance = 2.0
        self._noise = 1.0
        self._rng = random.Random(0)
        self._proposed = False
        self._attempts = 0
        self._max_attempts = 60

    def reset(self, scenario: Scenario) -> JsonDict:
        s = scenario.setup
        self._pos = [float(s["start"][0]), float(s["start"][1])]
        self._target = (float(s["target"][0]), float(s["target"][1]))
        self._tolerance = float(s.get("tolerance", 2.0))
        self._noise = float(s.get("noise", 1.0))
        self._rng = random.Random(int(s.get("seed", 0)))
        self._proposed = False
        self._attempts = 0
        self._max_attempts = int(s.get("max_attempts", 60))
        return self._observe()

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        kind = action.get("kind", "act")
        self._attempts += 1

        if kind == "propose":
            # Deterministic stand-in for the VLM naming the target. In live this
            # is the cloud multimodal call; here the env hands over the (noisy)
            # target so the controller can start refining.
            self._proposed = True
        elif kind == "act":
            dx, dy = action.get("delta", (0.0, 0.0))
            self._pos[0] += float(dx)
            self._pos[1] += float(dy)
        # refine / verify: no state change, just re-observe.

        assert self._target is not None
        true_err = (self._target[0] - self._pos[0], self._target[1] - self._pos[1])
        true_mag = (true_err[0] ** 2 + true_err[1] ** 2) ** 0.5
        solved = true_mag <= self._tolerance
        timeout = self._attempts >= self._max_attempts
        done = solved or timeout
        failure_code = None if solved else ("timeout" if timeout else None)
        progress = max(0.0, min(1.0, 1.0 - true_mag / max(self._initial_distance(), 1e-6)))
        info: JsonDict = {
            "success": solved,
            "failure_code": failure_code,
            "reason": "solved" if solved else (failure_code or "iterating"),
            "progress": progress,
            "metrics": {"true_error": true_mag, "attempts": self._attempts},
        }
        return self._observe(), done, info

    def _observe(self) -> JsonDict:
        if not self._proposed:
            return {"stage": "explore", "current": tuple(self._pos), "target": None,
                    "tolerance": self._tolerance, "error": None, "attempts": self._attempts}
        assert self._target is not None
        nx = self._rng.gauss(0.0, self._noise)
        ny = self._rng.gauss(0.0, self._noise)
        err = (self._target[0] - self._pos[0] + nx, self._target[1] - self._pos[1] + ny)
        return {
            "stage": "refine", "current": tuple(self._pos), "target": self._target,
            "tolerance": self._tolerance, "error": err, "attempts": self._attempts,
        }

    def _initial_distance(self) -> float:
        # distance at reset, for progress normalization
        return 50.0


class PuzzlePolicy:
    """Drives the real PuzzleController from PuzzleWorldEnv observations."""

    def __init__(self, controller: PuzzleController | None = None) -> None:
        self._controller = controller or PuzzleController()

    def reset(self, scenario: Scenario) -> None:
        self._controller.reset()

    def act(self, obs: JsonDict) -> JsonDict:
        view = PuzzleView(
            stage=obs.get("stage", "explore"),
            current=tuple(obs.get("current", (0.0, 0.0))),
            target=obs.get("target"),
            tolerance=obs.get("tolerance", 2.0),
            error=obs.get("error"),
            attempts_this_phase=obs.get("attempts", 0),
        )
        action: PuzzleAction = self._controller.decide(view)
        return {"kind": action.kind, "delta": action.delta}


def make_puzzle_scenarios(n: int, *, seed: int = 0) -> list[Scenario]:
    """Generate deterministic alignment-puzzle scenarios across precision tiers.

    Tiers ramp measurement noise from trivial to "single-step error can exceed
    progress" — at the top tier naive iteration oscillates, so the controller's
    under-shoot + escalate/re-propose logic is what's actually under test.
    """
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    # Representative precision tiers: trivial -> substantial noise. Above ~5 the
    # measurement sigma dwarfs the tolerance and convergence becomes a genuine
    # stochastic-approximation challenge (a real frontier, not a controller bug).
    tiers = [0.5, 1.5, 3.0, 5.0]
    for i in range(n):
        noise = tiers[i % len(tiers)]
        scenarios.append(Scenario(
            scenario_id=f"pz-{seed}-{i:03d}", objective="align piece to target",
            setup={
                "start": [rng.uniform(-40, 40), rng.uniform(-40, 40)],
                "target": [rng.uniform(-40, 40), rng.uniform(-40, 40)],
                "tolerance": 1.5, "noise": noise, "max_attempts": 50,
                "seed": rng.randint(0, 1_000_000),
            },
            max_steps=50, timeout_sec=15.0, tags=("puzzle", f"noise{noise}"),
        ))
    return scenarios
