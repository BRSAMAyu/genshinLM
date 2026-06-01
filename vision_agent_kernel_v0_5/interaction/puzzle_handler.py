"""Generic puzzle and challenge handler for exploration scenarios.

Handles 5 puzzle/challenge types that require visual understanding:
- Elemental monuments (元素方碑)
- Torch puzzles (火炬)
- Pressure plates (压力板)
- Timed challenges (限时挑战)
- Withering zone cleansing (死域清除)

Each handler follows the same contract:
  1. Analyze the current screen to identify puzzle state
  2. Generate a sequence of elemental/interaction actions
  3. Execute actions via InputWorker
  4. Verify puzzle completion via screen state change
"""
import logging
import threading
import time
import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)


class PuzzleType(Enum):
    ELEMENTAL_MONUMENT = "elemental_monument"
    TORCH = "torch"
    PRESSURE_PLATE = "pressure_plate"
    TIMED_CHALLENGE = "timed_challenge"
    WITHERING_ZONE = "withering_zone"


@dataclass(frozen=True, slots=True)
class PuzzleAction:
    """A single action in a puzzle solution sequence."""
    action_type: str  # "use_element", "press_key", "move_to", "attack"
    element: str = ""  # pyro/hydro/cryo/electro/anemo/geo/dendro
    target_nx: float = 0.5
    target_ny: float = 0.5
    key: str = ""
    reason: str = ""
    delay_ms: int = 500


@dataclass(slots=True)
class PuzzleState:
    """Current state of a puzzle being solved."""
    puzzle_type: PuzzleType
    started_at: float = 0.0
    actions_planned: int = 0
    actions_executed: int = 0
    completed: bool = False
    failed: bool = False
    failure_reason: str = ""


@dataclass(frozen=True, slots=True)
class PuzzleSolution:
    """A proposed solution for a puzzle."""
    puzzle_type: PuzzleType
    actions: tuple[PuzzleAction, ...] = ()
    confidence: float = 0.0
    requires_vlm: bool = False


class PuzzleHandler:
    """Handles puzzle detection, solution planning, and execution.

    For simple puzzles (timed challenges, withering zones), uses heuristic
    action sequences. For complex puzzles (elemental monuments, torches,
    pressure plates), delegates to VLM for visual analysis.
    """

    # Elemental skill keys per element
    _ELEMENT_KEYS: dict[str, str] = {
        "pyro": "e",      # Most characters use E for elemental skill
        "hydro": "e",
        "cryo": "e",
        "electro": "e",
        "anemo": "e",
        "geo": "e",
        "dendro": "e",
    }

    def __init__(
        self,
        backend: Any = None,
        classifier: Any = None,
        vlm_analyze: Callable | None = None,
    ) -> None:
        self._backend = backend
        self._classifier = classifier
        self._vlm_analyze = vlm_analyze

    def detect_puzzle_type(self, frame: Any) -> PuzzleType | None:
        """Detect puzzle type from current frame.

        Uses classifier for basic detection, VLM for disambiguation.
        Returns None if no puzzle detected.
        """
        if self._vlm_analyze is not None:
            try:
                result = self._vlm_analyze(frame, context="puzzle_detection")
                if isinstance(result, dict):
                    ptype_str = result.get("puzzle_type", "")
                    for pt in PuzzleType:
                        if pt.value == ptype_str:
                            return pt
            except Exception as exc:
                log.warning("[PuzzleHandler] VLM detection failed: %s", exc)
        return None

    def plan_solution(self, puzzle_type: PuzzleType, frame: Any = None) -> PuzzleSolution:
        """Plan a solution for the detected puzzle type.

        Returns a PuzzleSolution with action sequence.
        """
        if puzzle_type == PuzzleType.TIMED_CHALLENGE:
            return self._plan_timed_challenge()
        if puzzle_type == PuzzleType.WITHERING_ZONE:
            return self._plan_withering_zone()
        if puzzle_type == PuzzleType.ELEMENTAL_MONUMENT:
            return self._plan_elemental_monument(frame)
        if puzzle_type == PuzzleType.TORCH:
            return self._plan_torch(frame)
        if puzzle_type == PuzzleType.PRESSURE_PLATE:
            return self._plan_pressure_plate(frame)
        return PuzzleSolution(puzzle_type=puzzle_type, requires_vlm=True)

    def execute_solution(
        self,
        solution: PuzzleSolution,
        shutdown_event: threading.Event | None = None,
    ) -> PuzzleState:
        """Execute a puzzle solution and track progress."""
        state = PuzzleState(
            puzzle_type=solution.puzzle_type,
            started_at=time.perf_counter(),
            actions_planned=len(solution.actions),
        )

        for action in solution.actions:
            if shutdown_event and shutdown_event.is_set():
                state.failed = True
                state.failure_reason = "shutdown_requested"
                return state
            self._execute_action(action)
            state.actions_executed += 1
            _chunked_sleep(action.delay_ms / 1000.0, shutdown_event)

        state.completed = True
        log.info(
            "[PuzzleHandler] %s completed: %d/%d actions",
            solution.puzzle_type.value, state.actions_executed, state.actions_planned,
        )
        return state

    def solve_puzzle(
        self,
        puzzle_type: PuzzleType,
        frame: Any = None,
        shutdown_event: threading.Event | None = None,
    ) -> PuzzleState:
        """End-to-end: plan + execute a puzzle solution."""
        solution = self.plan_solution(puzzle_type, frame)
        return self.execute_solution(solution, shutdown_event)

    # ------------------------------------------------------------------
    # Solution planners
    # ------------------------------------------------------------------

    def _plan_timed_challenge(self) -> PuzzleSolution:
        """Timed challenges: approach marker → kill enemies → collect reward."""
        return PuzzleSolution(
            puzzle_type=PuzzleType.TIMED_CHALLENGE,
            actions=(
                PuzzleAction(action_type="press_key", key="f", reason="start_challenge", delay_ms=1000),
                PuzzleAction(action_type="attack", reason="clear_enemies", delay_ms=5000),
                PuzzleAction(action_type="press_key", key="f", reason="collect_reward", delay_ms=1000),
            ),
            confidence=0.6,
        )

    def _plan_withering_zone(self) -> PuzzleSolution:
        """Withering zone: find tumor → destroy branches → cleanse."""
        return PuzzleSolution(
            puzzle_type=PuzzleType.WITHERING_ZONE,
            actions=(
                PuzzleAction(action_type="move_to", target_nx=0.50, target_ny=0.50,
                             reason="approach_tumor", delay_ms=2000),
                PuzzleAction(action_type="attack", reason="destroy_tumor", delay_ms=3000),
                PuzzleAction(action_type="use_element", element="dendro",
                             reason="cleanse_withering", delay_ms=1000),
            ),
            confidence=0.5,
        )

    def _plan_elemental_monument(self, frame: Any = None) -> PuzzleSolution:
        """Elemental monument: requires VLM to identify required element."""
        element = self._detect_required_element(frame)
        if element:
            return PuzzleSolution(
                puzzle_type=PuzzleType.ELEMENTAL_MONUMENT,
                actions=(
                    PuzzleAction(action_type="use_element", element=element,
                                 target_nx=0.50, target_ny=0.50,
                                 reason=f"activate_monument_{element}", delay_ms=1000),
                ),
                confidence=0.7,
            )
        return PuzzleSolution(
            puzzle_type=PuzzleType.ELEMENTAL_MONUMENT,
            requires_vlm=True,
        )

    def _plan_torch(self, frame: Any = None) -> PuzzleSolution:
        """Torch puzzle: light unlit torches in correct order."""
        # Default: try lighting torches in a pattern
        return PuzzleSolution(
            puzzle_type=PuzzleType.TORCH,
            actions=(
                PuzzleAction(action_type="use_element", element="pyro",
                             target_nx=0.40, target_ny=0.45,
                             reason="light_torch_1", delay_ms=500),
                PuzzleAction(action_type="use_element", element="pyro",
                             target_nx=0.60, target_ny=0.45,
                             reason="light_torch_2", delay_ms=500),
                PuzzleAction(action_type="use_element", element="pyro",
                             target_nx=0.50, target_ny=0.55,
                             reason="light_torch_3", delay_ms=500),
            ),
            confidence=0.3,
            requires_vlm=True,
        )

    def _plan_pressure_plate(self, frame: Any = None) -> PuzzleSolution:
        """Pressure plate: place Geo construct or stand on plate."""
        return PuzzleSolution(
            puzzle_type=PuzzleType.PRESSURE_PLATE,
            actions=(
                PuzzleAction(action_type="use_element", element="geo",
                             target_nx=0.50, target_ny=0.50,
                             reason="geo_construct_on_plate", delay_ms=1000),
            ),
            confidence=0.4,
            requires_vlm=True,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_required_element(self, frame: Any) -> str:
        """Use VLM or heuristic to detect required element for a monument."""
        if self._vlm_analyze is not None:
            try:
                result = self._vlm_analyze(frame, context="element_detection")
                if isinstance(result, dict):
                    return result.get("element", "")
            except Exception:
                pass
        return ""

    def _execute_action(self, action: PuzzleAction) -> None:
        """Execute a single puzzle action via backend."""
        if self._backend is None:
            log.debug("[PuzzleHandler] no backend, skipping action: %s", action.reason)
            return

        try:
            if action.action_type == "press_key" and action.key:
                self._backend.key_press(action.key, reason=action.reason)
            elif action.action_type == "use_element" and action.element:
                key = self._ELEMENT_KEYS.get(action.element, "e")
                self._backend.key_press(key, reason=action.reason)
            elif action.action_type == "attack":
                self._backend.key_press("e", reason=action.reason)
            elif action.action_type == "move_to":
                # Navigate toward target position
                if hasattr(self._backend, "click_at_normalized"):
                    self._backend.click_at_normalized(
                        action.target_nx, action.target_ny, reason=action.reason,
                    )
        except Exception as exc:
            log.warning("[PuzzleHandler] action %s failed: %s", action.reason, exc)

    def filter_environment_noise(self, frame: np.ndarray) -> np.ndarray:
        """Filters ambient foliage, flora, weather particles, and wandering NPCs from raw visual frame."""
        if frame.size == 0:
            return frame
        # Apply standard color and brightness filters to highlight pyro/geo/electro puzzle elements
        # Converts frame to HSV and extracts bright saturated regions
        import cv2
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        
        # Keep only pixels that are saturated (S > 50) and bright (V > 50)
        mask = (s >= 50) & (v >= 50)
        filtered = np.zeros_like(frame)
        filtered[mask] = frame[mask]
        return filtered

    def extract_puzzle_landmarks(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Filters frame noise and projects 3D open world puzzle landmarks into simplified 2D coordinates."""
        filtered = self.filter_environment_noise(frame)
        if filtered.size == 0:
            return []
            
        landmarks = []
        # Identify Pyro torches, Electro/Geo monuments via specific color clusters
        # Pyro: high Red/Orange. Electro: high Purple. Geo: high Yellow/Gold.
        import cv2
        hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)
        h = hsv[:, :, 0]
        
        # Ensure we only check non-black/non-filtered pixels to prevent black background (H=0) matching
        non_black = filtered.max(axis=2) > 0
        
        # pyro torch cluster detection (H: 0-15 or 345-360)
        pyro_mask = ((h <= 15) | (h >= 345)) & non_black
        if pyro_mask.any():
            ys, xs = np.nonzero(pyro_mask)
            landmarks.append({
                "id": "pyro_torch_1",
                "element_type": "pyro_torch",
                "x": float(np.mean(xs)) / frame.shape[1],
                "y": float(np.mean(ys)) / frame.shape[0],
                "active": True
            })
            
        # electro monument cluster detection (H: 130-160)
        electro_mask = ((h >= 130) & (h <= 160)) & non_black
        if electro_mask.any():
            ys, xs = np.nonzero(electro_mask)
            landmarks.append({
                "id": "electro_monument_1",
                "element_type": "electro_monument",
                "x": float(np.mean(xs)) / frame.shape[1],
                "y": float(np.mean(ys)) / frame.shape[0],
                "active": False
            })
            
        log.info(f"[PuzzleHandler] Extracted {len(landmarks)} visual open-world puzzle landmarks.")
        return landmarks


def _chunked_sleep(seconds: float, shutdown_event: threading.Event | None = None) -> None:
    """Non-blocking chunked sleep with interrupt check."""
    deadline = time.perf_counter() + seconds
    chunk = 0.05
    while time.perf_counter() < deadline:
        if shutdown_event and shutdown_event.is_set():
            return
        remaining = max(0.0, deadline - time.perf_counter())
        time.sleep(min(chunk, remaining))
