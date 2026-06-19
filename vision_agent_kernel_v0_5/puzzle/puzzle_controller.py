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
    # Systematic-bias fallback: a constant additive measurement bias is
    # unobservable from relative error alone — so when the error-gradient loop
    # stalls above tolerance, switch to a local SEARCH that physically probes a
    # spiral of grid points around the stall point, relying on the ground-truth
    # verify (did the mechanism activate?) instead of the biased measurement.
    search_when_stalled: bool = True
    search_spacing_factor: float = 0.8   # grid spacing = factor * tolerance (<1 => overlap)
    search_max_radius_factor: float = 6.0  # cover bias up to ~max_radius - tolerance
    # How many times the measurement may claim "within tolerance" without the env
    # confirming a solve before we conclude the measurement is biased and search.
    max_unconfirmed_verifies: int = 3


class PuzzleController:
    """Iterative perceive-propose-refine-act-verify loop."""

    def __init__(self, config: PuzzleControllerConfig | None = None) -> None:
        self._cfg = config or PuzzleControllerConfig()
        self._no_progress = 0
        self._best_error_mag = float("inf")
        self._searching = False
        self._search_index = 0
        self._search_origin: tuple[float, float] | None = None
        self._verify_stall = 0

    def reset(self) -> None:
        self._no_progress = 0
        self._best_error_mag = float("inf")
        self._searching = False
        self._search_index = 0
        self._search_origin = None
        self._verify_stall = 0

    def decide(self, view: PuzzleView) -> PuzzleAction:
        cfg = self._cfg

        # No target yet -> ask the proposer (VLM/strategy) to name one.
        if view.target is None:
            return PuzzleAction("propose", reason="no target — request proposal")

        if view.error is None:
            return PuzzleAction("refine", reason="sharpen target measurement")

        # If we're in physical-search mode (measurement gradient was unreliable),
        # keep stepping the spiral until the ground-truth verify solves it.
        if self._searching:
            return self._search_step(view)

        err_x, err_y = view.error
        mag = (err_x * err_x + err_y * err_y) ** 0.5

        # Converged (by measurement) -> verify. But if the measurement keeps
        # saying "within tolerance" while the env never confirms a solve, the
        # measurement is biased — count repeated unconfirmed verifies and fall
        # through to the physical search once they pile up.
        if mag <= view.tolerance:
            self._verify_stall += 1
            if self._verify_stall <= cfg.max_unconfirmed_verifies:
                return PuzzleAction("verify", reason="within tolerance")
            if cfg.search_when_stalled and not self._searching:
                self._searching = True
                self._search_index = 0
                self._search_origin = view.current
                return self._search_step(view)
            return PuzzleAction("escalate", reason="verify unconfirmed — re-propose")
        self._verify_stall = 0

        # Track convergence; if we stall, the measurement is likely biased
        # (a constant offset is invisible to a relative-error loop) -> switch to
        # a physical local search that trusts the ground-truth verify instead.
        if mag < self._best_error_mag - 1e-6:
            self._best_error_mag = mag
            self._no_progress = 0
        else:
            self._no_progress += 1
        if self._no_progress >= cfg.stuck_no_progress_threshold or view.attempts_this_phase >= cfg.max_attempts:
            if cfg.search_when_stalled and not self._searching:
                self._searching = True
                self._search_index = 0
                self._search_origin = view.current
                return self._search_step(view)
            self._no_progress = 0
            self._best_error_mag = float("inf")
            return PuzzleAction("escalate", reason="stalled — re-propose / recover")

        # Close the error loop with an under-shooting step. Clamp to <= mag so a
        # large min_step can never overshoot the residual when tolerance is tiny.
        step = min(max(cfg.step_gain * mag, cfg.min_step), mag)
        scale = step / mag
        return PuzzleAction("act", delta=(err_x * scale, err_y * scale), reason="iterate toward target")

    def _search_step(self, view: PuzzleView) -> PuzzleAction:
        """Spiral grid probe around the stall point.

        Moves to the next absolute grid offset (delta is relative to *current*),
        spacing < tolerance so a solved cell can't be skipped. Bounded by
        search_max_radius_factor; exhausting it escalates. The ground-truth
        verify (mechanism activated?) is the oracle, not the biased measurement.
        """
        cfg = self._cfg
        spacing = max(0.5, cfg.search_spacing_factor * view.tolerance)
        max_radius = cfg.search_max_radius_factor * max(view.tolerance, 1.0)
        offsets = _spiral_offsets(spacing, max_radius)
        if self._search_index >= len(offsets):
            # Search exhausted — give up to the caller (re-propose / recover).
            self._searching = False
            self._no_progress = 0
            self._best_error_mag = float("inf")
            return PuzzleAction("escalate", reason="search exhausted — re-propose / recover")
        origin = self._search_origin or view.current
        ox, oy = offsets[self._search_index]
        self._search_index += 1
        target_x, target_y = origin[0] + ox, origin[1] + oy
        delta = (target_x - view.current[0], target_y - view.current[1])
        return PuzzleAction("act", delta=delta, reason=f"bias-search probe {self._search_index}")


def _spiral_offsets(spacing: float, max_radius: float) -> list[tuple[float, float]]:
    """Grid offsets within ``max_radius``, ordered nearest-first from origin.

    A full square grid (side 2*max_radius, ``spacing`` apart) sorted by distance
    to the origin, so the probe that is closest to the true target is reached as
    early as possible (the stall point sits ~bias away from truth, so the answer
    is usually a few rings out). Deterministic and pure (no RNG/time), tie-broken
    by (x, y) for reproducibility. The controller relies on the ground-truth
    verify to stop as soon as a probed cell solves.
    """
    rings = max(1, int(max_radius / spacing))
    cells: list[tuple[float, float]] = []
    for i in range(-rings, rings + 1):
        for j in range(-rings, rings + 1):
            cells.append((i * spacing, j * spacing))
    cells.sort(key=lambda p: (p[0] * p[0] + p[1] * p[1], p[0], p[1]))
    return cells
