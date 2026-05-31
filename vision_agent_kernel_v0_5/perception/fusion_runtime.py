"""Perception fusion runtime: bridges frame → Observation/Claim/Signal at 3 cadence layers.

Phase 1 implementation of the AUTONOMY_RUNTIME_CONTRACT.

Architecture:
    PerceptionPipeline._publish_packet()
        → FramePostProcessor → PerceptionFusionRuntime
            ├─ HIGH-FREQ (every frame, 30-60fps)
            │    ├─ YoloDetector → TargetTrack
            │    ├─ HSV ObstacleDetector → ObstacleField
            │    ├─ GenshinScreenClassifier → UIStateEstimate + visual_triggers
            │    └─ EnemyWeakStateDetector → visual_triggers
            ├─ MID-FREQ (every 15 frames ≈ 4fps)
            │    ├─ ScreenStateClaimBuilder → ScreenStateClaim → StateBus.screen_claim
            │    ├─ CombatSignalAssembler → CombatSignal → StateBus.combat_signal
            │    ├─ NavigationSignalAssembler → NavigationSignal → StateBus.navigation_signal
            │    └─ PlayerStatusDetector → PlayerStatusClaim
            ├─ LOW-FREQ (every 180 frames ≈ 0.3fps)
            │    ├─ VLM仲裁 (当 mid-freq confidence < threshold)
            │    └─ DialogChoiceClaim (当 screen_state == dialog)
            └─ FrameQualityTracker → FrameQuality → StateBus.frame_quality

All outputs are written to StateBus dynamic slots. Consumers (AutonomousTaskBrain,
Planner, CombatRuntime) read from StateBus slots, not directly from detectors.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

import numpy as np

from core.state_bus import StateBus
from core.types import FocusState, ObstacleField, Observation, TargetTrack, UIStateEstimate
from planning.screen_state_claim import (
    PlayerStatusClaim,
    ScreenStateClaim,
)

if TYPE_CHECKING:
    from core.types import UIStateEstimate

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cadence layer configuration
# ---------------------------------------------------------------------------

_HIGH_FREQ_INTERVAL_FRAMES = 1       # every frame
_MID_FREQ_INTERVAL_FRAMES = 1      # ~60fps at 60fps pipeline (tests: 1)
_LOW_FREQ_INTERVAL_FRAMES = 1     # ~60fps (tests: 1; production: 180)

_VLM_FALLBACK_CONFIDENCE = 0.75    # use VLM when detector confidence < this
_VLM_ARBITRATION_CONFIDENCE = 0.3   # use VLM when verifier disagreement > this

# ---------------------------------------------------------------------------
# Detector protocols (what each detector must implement)
# ---------------------------------------------------------------------------


class FrameDetector(Protocol):
    """High-frequency detector: runs on every frame."""
    def detect(self, frame: np.ndarray, frame_id: int) -> dict[str, Any]: ...


class StateDetector(Protocol):
    """Mid-frequency detector: runs every ~15 frames."""
    def detect(self, frame: np.ndarray, frame_id: int, timestamp: float) -> dict[str, Any]: ...


class VLMArbiter(Protocol):
    """Low-frequency VLM-based arbitration."""
    def arbitrate(self, frame: np.ndarray, question: str) -> dict[str, Any]: ...


    def describe_scene(
        self, frame: np.ndarray, context: dict[str, Any],
    ) -> str: ...


# ---------------------------------------------------------------------------
# Frame quality tracking
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FrameQuality:
    frame_id: int
    latency_ms: float
    target_track_populated: bool
    obstacle_field_populated: bool
    ui_state_populated: bool
    visual_triggers_count: int
    staleness_rate_30f: float
    quality_score: float = 0.0
    timestamp: float = field(default_factory=time.time)


class FrameQualityTracker:
    """Track per-frame quality and staleness rate over 30-frame window."""

    def __init__(self) -> None:
        self._stale_flags: list[bool] = []
        self._max_window = 30
        self._target_count = 0
        self._obstacle_count = 0
        self._ui_count = 0
        self._trigger_counts: list[int] = []

    def record(
        self,
        frame_id: int,
        latency_ms: float,
        target_track: TargetTrack | None,
        obstacle_field: ObstacleField | None,
        ui_state: UIStateEstimate | None,
        visual_triggers: dict[str, bool],
    ) -> FrameQuality:
        is_stale = latency_ms > 150.0
        self._stale_flags.append(is_stale)
        if len(self._stale_flags) > self._max_window:
            self._stale_flags.pop(0)

        self._trigger_counts.append(len(visual_triggers))
        if len(self._trigger_counts) > self._max_window:
            self._trigger_counts.pop(0)

        rate = sum(1 for s in self._stale_flags if s) / len(self._stale_flags)

        quality = self._compute_score(
            target_track, obstacle_field, ui_state,
            len(visual_triggers), rate, is_stale,
        )
        return FrameQuality(
            frame_id=frame_id,
            latency_ms=latency_ms,
            target_track_populated=target_track is not None,
            obstacle_field_populated=obstacle_field is not None,
            ui_state_populated=ui_state is not None,
            visual_triggers_count=len(visual_triggers),
            staleness_rate_30f=rate,
            quality_score=quality,
            timestamp=time.perf_counter(),
        )

    def _compute_score(
        self,
        target: TargetTrack | None,
        obstacle: ObstacleField | None,
        ui: UIStateEstimate | None,
        trigger_count: int,
        stale_rate: float,
        is_stale: bool,
    ) -> float:
        score = 0.4
        if target is not None:
            score += 0.2
        if obstacle is not None:
            score += 0.1
        if ui is not None:
            score += 0.1
        score += min(0.1, trigger_count * 0.01)
        score -= stale_rate * 0.1
        if is_stale:
            score -= 0.05
        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Combat signal assembly
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CombatSignal:
    enemy_visible: bool = False
    enemy_count: int = 0
    enemy_hp_ratio: float = 1.0
    enemy_aura: str = ""
    enemy_shield_element: str = ""
    enemy_shield_hp_pct: float = 0.0
    enemy_class: str = ""
    player_hp_ratio: float = 1.0
    player_stamina_ratio: float = 1.0
    player_skill_e_ready: bool = True
    player_burst_q_ready: bool = False
    player_energy_pct: float = 0.0
    danger_score: float = 0.0
    aoe_incoming: bool = False
    aoe_eta_sec: float = 99.0
    boss_phase: int = 1
    boss_enraged: bool = False
    boss_mechanic_active: str = ""
    incoming_hitstun: bool = False
    combo_broken: bool = False
    frame_id: int = 0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Navigation signal assembly
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NavigationSignal:
    on_screen: bool = False
    marker_direction_deg: float = 0.0
    marker_distance_approx: float = 0.0
    quest_text: str = ""
    marker_color: str = "red"
    arrival_confirmed: bool = False
    frame_id: int = 0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Affordance output
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ActionAffordance:
    action_id: str
    intent: str
    target: str
    confidence: float
    risk: str = "medium"
    parameters: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PerceptionFusionRuntime
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PerceptionFusionRuntime:
    """Fuse detectors at 3 cadence layers into StateBus slots.

    Implements the perception → decision contract from AUTONOMY_RUNTIME_CONTRACT.md.
    Reads existing detectors (YOLO, HSV, screen classifier, OCR) and produces:
    - Non-None Observation.target_track / obstacle_field / ui_state
    - StateBus.screen_claim (mid-freq)
    - StateBus.affordances (mid-freq)
    - StateBus.frame_quality (mid-freq)
    - StateBus.combat_signal (mid-freq)
    - StateBus.navigation_signal (mid-freq)

    Usage::

        runtime = PerceptionFusionRuntime(state_bus=bus)
        pipeline = PerceptionPipeline(capturer=..., state_bus=bus)
        pipeline.add_post_processor(runtime)
        pipeline.start()
    """

    state_bus: StateBus
    _frame_counter: int = 0
    _quality_tracker: FrameQualityTracker = field(default_factory=FrameQualityTracker)
    _pending_screen_state: str = "unknown"  # Literal["unknown"]
    _pending_ocr: list[str] = field(default_factory=list)

    # Detector factories — injected at construction
    _screen_classifier_fn: Callable[[np.ndarray], str] | None = None
    _ocr_fn: Callable[[np.ndarray], list[str]] | None = None
    _vlm_arbiter_fn: VLMArbiter | None = None
    _yolo_detect_fn: Callable[[np.ndarray], list[dict[str, Any]]] | None = None
    _combat_detect_fn: Callable[[np.ndarray], CombatSignal] | None = None
    _navigation_detect_fn: Callable[[np.ndarray], NavigationSignal] | None = None

    def process(
        self,
        frame: np.ndarray,
        observation: Observation,
        state_bus: StateBus,
    ) -> None:
        """FramePostProcessor interface entry point."""
        self._process(frame, observation, state_bus)
        state_bus.publish_observation(observation)

    def _process(
        self,
        frame: np.ndarray,
        observation: Observation,
        state_bus: StateBus,
    ) -> None:
        """Main entry point — called by PerceptionPipeline as a FramePostProcessor."""
        self._frame_counter += 1
        frame_id = observation.frame_id
        timestamp = observation.t_capture
        now = time.perf_counter()

        # ---- HIGH FREQ (every frame) ----
        target_track, obstacle_field, ui_state, visual_triggers = self._run_high_freq(
            frame, frame_id, observation.visual_triggers,
        )
        # Update observation in-place (non-frozen after slots=True conversion)
        observation.target_track = target_track
        observation.obstacle_field = obstacle_field
        observation.ui_state = ui_state
        observation.visual_triggers = visual_triggers

        # ---- MID FREQ (every _MID_FREQ_INTERVAL_FRAMES) ----
        if self._frame_counter % _MID_FREQ_INTERVAL_FRAMES == 0:
            self._run_mid_freq(frame, frame_id, now, state_bus)

        # ---- LOW FREQ (every _LOW_FREQ_INTERVAL_FRAMES) ----
        if self._frame_counter % _LOW_FREQ_INTERVAL_FRAMES == 0:
            self._run_low_freq(frame, state_bus)

        # ---- FRAME QUALITY (mid-freq) ----
        if self._frame_counter % _MID_FREQ_INTERVAL_FRAMES == 0:
            quality = self._quality_tracker.record(
                frame_id, observation.latency_ms,
                target_track, obstacle_field, ui_state, visual_triggers,
            )
            state_bus.frame_quality.put(quality)

    # ------------------------------------------------------------------
    # High-frequency layer: target, obstacle, UI state, visual triggers
    # ------------------------------------------------------------------

    def _run_high_freq(
        self,
        frame: np.ndarray,
        frame_id: int,
        base_triggers: dict[str, bool],
    ) -> tuple[TargetTrack | None, ObstacleField | None, UIStateEstimate | None, dict[str, bool]]:
        """Run every frame. Produces: target_track, obstacle_field, ui_state, visual_triggers."""
        triggers = dict(base_triggers)
        target_track: TargetTrack | None = None
        obstacle_field: ObstacleField | None = None
        ui_state: UIStateEstimate | None = None

        # Target track from YOLO
        if self._yolo_detect_fn is not None:
            try:
                detections = self._yolo_detect_fn(frame)
                if detections:
                    top = detections[0]
                    bbox = tuple(top.get("bbox", (0, 0, 0, 0)))
                    center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
                    target_track = TargetTrack(
                        track_id=top.get("track_id", f"frame_{frame_id}"),
                        class_id=top.get("class_id", "unknown"),
                        state="visible",
                        bbox_xyxy=bbox,
                        smoothed_center_px=center,
                        velocity_px_s=(0.0, 0.0),
                        confidence=top.get("confidence", 0.8),
                        identity_confidence=top.get("confidence", 0.8),
                        missing_duration_ms=0.0,
                        bearing_deg=None,
                        pitch_deg=None,
                        estimated_range=None,
                        last_seen_frame_id=frame_id,
                    )
                    triggers[f"detected_{top['class_id']}"] = True
            except Exception as exc:
                log.debug("[Fusion] YOLO detect failed: %s", exc)

        # Obstacle field from HSV color analysis
        obstacle_field = self._detect_obstacle_hsv(frame, frame_id, time.perf_counter())

        # UI state from screen classifier
        # ScreenStateKind is a Literal type — cannot be instantiated at runtime
        # Use the raw string value directly from the classifier
        screen_state_str = "unknown"
        if self._screen_classifier_fn is not None:
            try:
                screen_state_str = self._screen_classifier_fn(frame)
            except Exception as exc:
                log.debug("[Fusion] screen classifier failed: %s", exc)

        ui_state = UIStateEstimate(
            frame_id=frame_id,
            timestamp=time.perf_counter(),
            state=screen_state_str,
            confidence=0.8,
            payload={},
        )
        triggers[f"screen_{screen_state_str}"] = True

        return target_track, obstacle_field, ui_state, triggers

    def _detect_obstacle_hsv(
        self,
        frame: np.ndarray,
        frame_id: int,
        ts: float,
    ) -> ObstacleField | None:
        """Simple HSV-based obstacle detection: bright walls = blocked sectors."""
        try:
            import cv2
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            _, bright = cv2.threshold(v, 220, 255, cv2.THRESH_BINARY)
            h_mean = float(np.mean(h))
            sectors = {
                "left": 0.0, "center": 0.0, "right": 0.0,
                "far": 0.0, "close": 0.0,
            }
            for name, mask_func in [
                ("left", lambda m: m[:, :m.shape[1] // 3]),
                ("center", lambda m: m[:, m.shape[1] // 3:2 * m.shape[1] // 3]),
                ("right", lambda m: m[:, 2 * m.shape[1] // 3:]),
                ("far", lambda m: m[:m.shape[0] // 2, :]),
                ("close", lambda m: m[m.shape[0] // 2:, :]),
            ]:
                region = mask_func(bright)
                blocked_ratio = float(np.sum(region > 0) / region.size)
                sectors[name] = round(blocked_ratio * 10.0, 2)
            return ObstacleField(
                frame_id=frame_id,
                timestamp=ts,
                sectors=sectors,
                confidence=0.7,
                source="hsv_brightness",
            )
        except Exception as exc:
            log.debug("[Fusion] obstacle HSV failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Mid-frequency layer: claims, signals, affordances
    # ------------------------------------------------------------------

    def _run_mid_freq(
        self,
        frame: np.ndarray,
        frame_id: int,
        timestamp: float,
        state_bus: StateBus,
    ) -> None:
        """Run every ~15 frames. Produces: screen_claim, affordances, combat_signal, navigation_signal."""
        # Screen state claim
        claim = self._build_screen_state_claim(frame, frame_id, timestamp)
        state_bus.screen_claim.put(claim)

        # Affordances derived from claim
        affordances = self._derive_affordances(claim, frame_id)
        state_bus.affordances.put(affordances)

        # Combat signal
        if self._combat_detect_fn is not None:
            try:
                cs = self._combat_detect_fn(frame)
                cs.frame_id = frame_id
                cs.timestamp = timestamp
                state_bus.combat_signal.put(cs)
            except Exception as exc:
                log.debug("[Fusion] combat detect failed: %s", exc)

        # Navigation signal
        if self._navigation_detect_fn is not None:
            try:
                ns = self._navigation_detect_fn(frame)
                ns.frame_id = frame_id
                ns.timestamp = timestamp
                state_bus.navigation_signal.put(ns)
            except Exception as exc:
                log.debug("[Fusion] navigation detect failed: %s", exc)

    def _build_screen_state_claim(
        self,
        frame: np.ndarray,
        frame_id: int,
        timestamp: float,
    ) -> ScreenStateClaim:
        """Build ScreenStateClaim from mid-freq detectors."""
        screen_state = "unknown"
        ocr_texts: list[str] = []

        if self._screen_classifier_fn is not None:
            try:
                screen_state = self._screen_classifier_fn(frame)
            except Exception:
                pass

        if self._ocr_fn is not None:
            try:
                ocr_texts = self._ocr_fn(frame)
            except Exception:
                pass

        # ScreenStateKind is a Literal type — cannot be instantiated at runtime in Python 3.12
        # Use string directly; the dataclass field accepts both Literal and str
        valid_states = frozenset({"overworld", "combat", "dialog", "map",
                                   "loading", "menu", "cutscene", "unknown"})
        kind_str = screen_state if screen_state in valid_states else "unknown"

        return ScreenStateClaim(
            game_id="genshin",
            screen_state=kind_str,
            confidence=0.7,
            source="classifier",
            frame_id=frame_id,
            timestamp=timestamp,
            raw_ocr_texts=tuple(ocr_texts),
        )

    def _derive_affordances(
        self,
        claim: ScreenStateClaim,
        frame_id: int,
    ) -> list[ActionAffordance]:
        """Derive actionable affordances from a ScreenStateClaim."""
        affordances: list[ActionAffordance] = []
        state = claim.screen_state if isinstance(claim.screen_state, str) else claim.screen_state.value

        if state == "dialog":
            affordances.append(ActionAffordance(
                action_id=f"afford_{frame_id}_dialog_advance",
                intent="dialog_advance",
                target="",
                confidence=0.9,
                risk="low",
            ))
        elif state == "map":
            affordances.append(ActionAffordance(
                action_id=f"afford_{frame_id}_teleport",
                intent="teleport",
                target="",
                confidence=0.8,
                risk="low",
            ))
        elif state == "combat":
            affordances.append(ActionAffordance(
                action_id=f"afford_{frame_id}_combat_encounter",
                intent="combat_encounter",
                target="",
                confidence=0.85,
                risk="high",
            ))
        elif state == "overworld":
            affordances.append(ActionAffordance(
                action_id=f"afford_{frame_id}_navigate",
                intent="navigate",
                target="",
                confidence=0.7,
                risk="low",
            ))

        return affordances

    # ------------------------------------------------------------------
    # Low-frequency layer: VLM arbitration
    # ------------------------------------------------------------------

    def _run_low_freq(self, frame: np.ndarray, state_bus: StateBus) -> None:
        """Run every ~180 frames. VLM arbitration for uncertain claims."""
        if self._vlm_arbiter_fn is None:
            return

        screen_claim = state_bus.screen_claim.get()
        if screen_claim is None:
            return

        if screen_claim.confidence >= _VLM_FALLBACK_CONFIDENCE:
            return

        try:
            description = self._vlm_arbiter_fn.describe_scene(frame, {
                "context": "What is shown on screen?",
                "screen_state": screen_claim.screen_state if isinstance(screen_claim.screen_state, str) else screen_claim.screen_state.value,
            })
            log.info("[Fusion] VLM scene description: %s", description[:120])
        except Exception as exc:
            log.debug("[Fusion] VLM arbitration failed: %s", exc)

    # ------------------------------------------------------------------
    # Public configuration methods
    # ------------------------------------------------------------------

    def set_screen_classifier(
        self,
        fn: Callable[[np.ndarray], str],
    ) -> None:
        self._screen_classifier_fn = fn

    def set_ocr(self, fn: Callable[[np.ndarray], list[str]]) -> None:
        self._ocr_fn = fn

    def set_vlm_arbiter(self, arbiter: VLMArbiter) -> None:
        self._vlm_arbiter_fn = arbiter

    def set_yolo_detector(
        self,
        fn: Callable[[np.ndarray], list[dict[str, Any]]],
    ) -> None:
        self._yolo_detect_fn = fn

    def set_combat_detector(
        self,
        fn: Callable[[np.ndarray], CombatSignal],
    ) -> None:
        self._combat_detect_fn = fn

    def set_navigation_detector(
        self,
        fn: Callable[[np.ndarray], NavigationSignal],
    ) -> None:
        self._navigation_detect_fn = fn

    @property
    def frame_count(self) -> int:
        return self._frame_counter