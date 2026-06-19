"""Game-agnostic puzzle controller (ROADMAP Phase 4).

Puzzles are the highest-precision domain: alignment / placement / sequence
challenges where a single shot is rarely pixel-perfect. The core principle (from
ROADMAP) is that precision comes from *iteration*, not from one-shot accuracy:

    PROPOSE  (VLM/strategy names the target) ->
    REFINE   (local detector/OCR sharpens the pixel target) ->
    ACT      (move/click toward it) ->
    OBSERVE  (re-read the world) ->
    ADJUST   (close the error loop until within tolerance)

This controller is game-agnostic. A capsule feeds a :class:`PuzzleView` from
perception (+ the VLM via the protocol for PROPOSE); the sim feeds a simulated
view. It emits :class:`PuzzleAction`s and converges by closing the error loop,
not by guessing once.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PuzzleView:
    """What the puzzle agent sees this tick.

    ``current`` is the agent's current placement/state; ``target`` is the goal
    placement it must reach. Both are 2D positions (e.g. a movable piece, a
    camera alignment, a click point). ``error`` is the signed vector from current
    to target when measurable; the controller closes it to within ``tolerance``.
    """

    stage: str = "explore"  # explore | propose | refine | act | verify | solved | stuck
    current: tuple[float, float] = (0.0, 0.0)
    target: tuple[float, float] | None = None
    tolerance: float = 2.0
    error: tuple[float, float] | None = None
    attempts_this_phase: int = 0


@dataclass(frozen=True, slots=True)
class PuzzleAction:
    kind: str  # propose | refine | act | verify | done | escalate
    delta: tuple[float, float] = (0.0, 0.0)
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PuzzleControllerConfig:
    # When closing the error loop, step a fraction of the remaining error each
    # tick (under-shoot) so imprecision doesn't overshoot, then snap in tolerance.
    # The step is clamped to <= the remaining error magnitude, so ``min_step``
    # can never cause an overshoot when tolerance is sub-min_step.
    step_gain: float = 0.6
    min_step: float = 0.5
    # Total iteration cap (the sim feeds its global attempt counter here).
    max_attempts: int = 25
    # If we've made many micro-steps without converging, escalate (hand to
    # recovery / relocalize / ask the VLM to re-propose). Escalate is terminal
    # for this controller: the CALLER must ``reset()`` and re-run PROPOSE
    # (e.g. ask the cloud VLM to re-name the target) — on its own, escalate
    # just re-observes and will escalate again until max_attempts times out.
    stuck_no_progress_threshold: int = 6


class PuzzleController:
    """Iterative perceive-propose-refine-act-verify loop."""

    def __init__(self, config: PuzzleControllerConfig | None = None) -> None:
        self._cfg = config or PuzzleControllerConfig()
        self._no_progress = 0
        self._best_error_mag = float("inf")

    def reset(self) -> None:
        self._no_progress = 0
        self._best_error_mag = float("inf")

    def decide(self, view: PuzzleView) -> PuzzleAction:
        cfg = self._cfg

        # No target yet -> ask the proposer (VLM/strategy) to name one.
        if view.target is None:
            return PuzzleAction("propose", reason="no target — request proposal")

        if view.error is None:
            return PuzzleAction("refine", reason="sharpen target measurement")

        err_x, err_y = view.error
        mag = (err_x * err_x + err_y * err_y) ** 0.5

        # Converged -> verify (the env confirms solution on the verify tick).
        if mag <= view.tolerance:
            return PuzzleAction("verify", reason="within tolerance")

        # Track convergence; if we stall, escalate rather than micro-step forever.
        if mag < self._best_error_mag - 1e-6:
            self._best_error_mag = mag
            self._no_progress = 0
        else:
            self._no_progress += 1
        if self._no_progress >= cfg.stuck_no_progress_threshold or view.attempts_this_phase >= cfg.max_attempts:
            return PuzzleAction("escalate", reason="stalled — re-propose / recover")

        # Close the error loop with an under-shooting step. Clamp to <= mag so a
        # large min_step can never overshoot the residual when tolerance is tiny.
        step = min(max(cfg.step_gain * mag, cfg.min_step), mag)
        scale = step / mag
        return PuzzleAction("act", delta=(err_x * scale, err_y * scale), reason="iterate toward target")
