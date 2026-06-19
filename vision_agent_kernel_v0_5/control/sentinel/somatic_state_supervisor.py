"""Somatic state supervisor for stamina and environmental hazard monitoring.

S-03 / S-04: Monitors stamina bar, HP, and environmental hazards (Sheer Cold,
Phlogiston, etc.) during open-world traversal. Intercepts movement when stamina
is critically low or health is in danger. Triggers emergency healing flows.

Integrates with:
- navigation/special_movement.py for stamina-consuming actions
- execution/input_worker.py for keyboard release
- interaction/ui_flows for emergency food eating
- perception/exploration_detectors.py for hazard detection
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class StaminaZone(str, Enum):
    FULL = "full"          # > 80%
    NORMAL = "normal"      # 40-80%
    LOW = "low"            # 15-40%
    CRITICAL = "critical"   # < 15%
    EMPTY = "empty"        # ~0% (drowning/falling)


class HealthZone(str, Enum):
    FULL = "full"          # > 80%
    NORMAL = "normal"      # 40-80%
    LOW = "low"            # 20-40%
    CRITICAL = "critical"  # < 20%
    DEAD = "dead"          # 0%


class HazardLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"     # Environmental damage starting
    DANGER = "danger"      # Continuous HP loss
    LETHAL = "lethal"       # Rapid HP loss


@dataclass(frozen=True, slots=True)
class VitalSigns:
    """Current physical vital signs of the character (stamina/health/hazard).

    Renamed from VitalSigns to avoid confusion with the mission-level
    VitalSigns in somatic_state.py (which tracks quests, positions, team).
    """
    stamina_ratio: float           # 0.0-1.0
    stamina_zone: StaminaZone
    health_ratio: float            # 0.0-1.0
    health_zone: HealthZone
    hazard_level: HazardLevel
    hazard_type: str | None        # e.g. "sheer_cold", "phlogiston"
    stamina_recovering: bool
    health_recovering: bool
    recovery_mode: bool
    recommended_action: str
    timestamp: float
    oxygen_ratio: float = 1.0
    stamina_buffer: float = 1.0


@dataclass(slots=True)
class SomaticConfig:
    """Configuration for somatic monitoring."""
    # Stamina thresholds
    stamina_full_threshold: float = 0.80
    stamina_normal_threshold: float = 0.40
    stamina_low_threshold: float = 0.15
    stamina_critical_threshold: float = 0.05

    # Health thresholds
    health_full_threshold: float = 0.80
    health_normal_threshold: float = 0.40
    health_low_threshold: float = 0.35
    health_critical_threshold: float = 0.20

    # Recovery timing
    food_cooldown_sec: float = 15.0
    stamina_recovery_wait_sec: float = 0.5
    health_food_threshold: float = 0.35

    # Stamina bar HSV range (yellow-green stamina bar in Genshin)
    stamina_low: tuple[int, int, int] = (25, 100, 150)
    stamina_high: tuple[int, int, int] = (35, 255, 255)

    # Health bar HSV range (green HP bar)
    health_low: tuple[int, int, int] = (55, 180, 150)
    health_high: tuple[int, int, int] = (85, 255, 255)

    # Sheer cold indicator (blue-white tint)
    sheer_cold_low: tuple[int, int, int] = (90, 30, 200)
    sheer_cold_high: tuple[int, int, int] = (120, 80, 255)

    # Phlogiston indicator (orange-red)
    phlogiston_low: tuple[int, int, int] = (0, 150, 200)
    phlogiston_high: tuple[int, int, int] = (20, 255, 255)

    # Stamina bar ROI (right side of screen, vertical bar)
    stamina_roi: tuple[float, float, float, float] = (0.88, 0.35, 0.98, 0.70)
    # Health bar ROI (right side of screen, below stamina)
    health_roi: tuple[float, float, float, float] = (0.88, 0.70, 0.98, 0.90)


class SomaticStateSupervisor:
    """Monitors stamina/HP and intercepts movement during open-world traversal.

    This closes S-03 / S-04: when stamina drops critically or HP is in danger,
    this supervisor forces the character to stop and recover. Without it, the
    agent will swim/climb until drowning or climb until falling to death.
    """

    _REF_W = 1920
    _REF_H = 1080

    def __init__(
        self,
        config: SomaticConfig | None = None,
        now_fn=None,
        state_bus: Any | None = None,
        input_worker: Any | None = None,
    ) -> None:
        self._config = config or SomaticConfig()
        self._now_fn = now_fn or time.perf_counter
        self._state_bus = state_bus
        self._input_worker = input_worker

        self._recovery_mode = False
        self._last_eat_time = 0.0
        self._last_state: VitalSigns | None = None
        self._stamina_history: list[float] = []
        self._health_history: list[float] = []
        self._frame_count = 0
        self._food_count = 5  # default food inventory buffer

    @property
    def last_state(self) -> VitalSigns | None:
        return self._last_state

    @property
    def recovery_mode(self) -> bool:
        return self._recovery_mode

    @property
    def hazard_level(self) -> HazardLevel:
        if self._last_state is None:
            return HazardLevel.SAFE
        return self._last_state.hazard_level

    def check_frame(
        self,
        frame,
        frame_id: int = 0,
    ) -> VitalSigns:
        """Analyze a frame and return the current somatic state.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID (for timestamping)

        Returns:
            VitalSigns with current character status and recommended action
        """
        self._frame_count = frame_id
        now = self._now_fn()

        if cv2 is None or frame is None or frame.size == 0:
            return self._default_state(now)

        # Detect bar ratios
        stamina_ratio = self._detect_stamina_bar(frame)
        health_ratio = self._detect_health_bar(frame)
        oxygen_ratio = self._detect_oxygen_bar(frame)

        # Track history for recovery detection
        self._stamina_history.append(stamina_ratio)
        self._health_history.append(health_ratio)
        if len(self._stamina_history) > 30:
            self._stamina_history = self._stamina_history[-30:]
        if len(self._health_history) > 30:
            self._health_history = self._health_history[-30:]

        # Compute predictive stamina buffer
        stamina_buffer = stamina_ratio
        if len(self._stamina_history) >= 2:
            stamina_buffer = stamina_ratio + (self._stamina_history[-1] - self._stamina_history[-2]) * 2.0
        stamina_buffer = min(max(stamina_buffer, 0.0), 1.0)

        # Detect environmental hazards
        hazard_level, hazard_type = self._detect_hazards(frame)

        # Classify zones
        stamina_zone = self._classify_stamina_zone(stamina_ratio)
        health_zone = self._classify_health_zone(health_ratio)

        # Determine recovery states
        stamina_recovering = self._detect_stamina_recovery()
        health_recovering = self._detect_health_recovery()

        # Determine recommended action
        action = self._determine_action(
            stamina_ratio, stamina_zone,
            health_ratio, health_zone,
            hazard_level, stamina_recovering,
        )

        state = VitalSigns(
            stamina_ratio=stamina_ratio,
            stamina_zone=stamina_zone,
            health_ratio=health_ratio,
            health_zone=health_zone,
            hazard_level=hazard_level,
            hazard_type=hazard_type,
            stamina_recovering=stamina_recovering,
            health_recovering=health_recovering,
            recovery_mode=self._recovery_mode,
            recommended_action=action,
            timestamp=now,
            oxygen_ratio=oxygen_ratio,
            stamina_buffer=stamina_buffer,
        )

        self._last_state = state

        # Log warnings
        if stamina_zone == StaminaZone.CRITICAL:
            log.warning("[Somatic] STAMINA CRITICAL: %.1f%% — forcing halt", stamina_ratio * 100)
        elif stamina_zone == StaminaZone.LOW:
            log.info("[Somatic] stamina low: %.1f%%", stamina_ratio * 100)

        if health_zone in (HealthZone.CRITICAL, HealthZone.LOW):
            log.warning("[Somatic] HEALTH %s: %.1f%%", health_zone.value, health_ratio * 100)

        if hazard_level == HazardLevel.DANGER:
            log.warning("[Somatic] ENVIRONMENTAL HAZARD: %s", hazard_type or "unknown")

        return state

    def monitor_and_intercept(
        self,
        backend,
        frame,
        frame_id: int = 0,
    ) -> tuple[VitalSigns, bool]:
        """Full monitoring loop: check frame and intercept if needed.

        Returns (state, intercepted) where intercepted=True means we already
        took protective action (halted movement or triggered healing).
        """
        state = self.check_frame(frame, frame_id)
        intercepted = False

        # Stamina critical: force halt immediately and deploy wind glider if mid-climb/swimming
        if state.stamina_zone in (StaminaZone.CRITICAL, StaminaZone.EMPTY):
            log.warning("[Somatic] Stamina critical — halting movement")
            self._halt_all_movement(backend)
            
            # Resolve Gap 21: High-altitude Stamina Deprivation Wind-Glider deployment
            if state.stamina_ratio < 0.15:
                log.warning("[Somatic] Mid-climb exhaustion threat! Triggering wind glider landing fallback.")
                try:
                    # Let go of wall by pressing X, then double tap Space to glide
                    backend.key_down("x", reason="let_go_of_wall")
                    self._chunked_sleep(0.05)
                    backend.key_up("x")
                    self._chunked_sleep(0.15)
                    backend.key_down("space", reason="deploy_glider_tap1")
                    self._chunked_sleep(0.05)
                    backend.key_up("space")
                    self._chunked_sleep(0.1)
                    backend.key_down("space", reason="deploy_glider_tap2")
                    self._chunked_sleep(0.05)
                    backend.key_up("space")
                except Exception as e:
                    log.error("[Somatic] failed to deploy wind glider: %s", e)

            self._recovery_mode = True
            intercepted = True

        if self._recovery_mode:
            if state.stamina_zone in (StaminaZone.FULL, StaminaZone.NORMAL):
                log.info("[Somatic] Stamina recovered (%.1f%%) — releasing recovery mode", state.stamina_ratio * 100)
                self._recovery_mode = False
            else:
                self._chunked_sleep(self._config.stamina_recovery_wait_sec)
                intercepted = True

        # Health critical: trigger emergency healing
        if state.health_zone == HealthZone.CRITICAL:
            now = self._now_fn()
            if now - self._last_eat_time > self._config.food_cooldown_sec:
                log.warning("[Somatic] Health critical — triggering emergency healing")
                self._execute_emergency_healing(backend)
                self._last_eat_time = now
                intercepted = True

        return state, intercepted

    def _halt_all_movement(self, backend) -> None:
        """Immediately release all movement keys."""
        keys = ("w", "a", "s", "d", "space", "shift")
        for key in keys:
            try:
                if hasattr(backend, "key_up"):
                    backend.key_up(key, reason="somatic_stamina_halt")
                elif hasattr(backend, "release_key"):
                    backend.release_key(key, reason="somatic_stamina_halt")
            except Exception as exc:
                log.debug("[Somatic] key release failed for %s: %s", key, exc)

    def _execute_emergency_healing(self, backend) -> None:
        """Trigger emergency food eating via UIFlow or Teleport to Statue if depleted."""
        # Resolve Gap 18: Backpack Food Exhaustion check
        if hasattr(self, "_food_count") and self._food_count <= 0:
            log.warning("[Somatic] Emergency food supply depleted! Bypassing backpack and triggering emergency teleport recovery.")
            try:
                backend.key_down("m", reason="emergency_statue_teleport")
                self._chunked_sleep(0.3)
                backend.key_up("m")
                self._chunked_sleep(1.0)
                rect = backend.client_rect()
                backend.click_at(rect.center[0], rect.center[1], reason="teleport_statue_selection")
                self._chunked_sleep(0.5)
                backend.key_down("enter", reason="confirm_statue_teleport")
                self._chunked_sleep(0.1)
                backend.key_up("enter")
            except Exception as e:
                log.error("[Somatic] Emergency statue teleport failed: %s", e)
            return

        log.info("[Somatic] executing emergency food flow")
        try:
            from interaction.ui_flows import get_flow
            from interaction.ui_flow_engine import UIFlowExecutor

            flow = get_flow("food_use_from_backpack")
            # Use shared StateBus and InputWorker from initialization, not independent ones
            if self._state_bus is not None and self._input_worker is not None:
                executor = UIFlowExecutor(state_bus=self._state_bus, input_worker=self._input_worker)
            else:
                from execution.input_worker import InputWorker
                from core.state_bus import StateBus
                fallback_bus = StateBus()
                worker = InputWorker(backend=backend, state_bus=fallback_bus)
                executor = UIFlowExecutor(state_bus=fallback_bus, input_worker=worker)
            result = executor.execute(flow)
            log.info("[Somatic] food flow result: %s", result.status)
            if result.status == "FAILED" or result.failure_code == "RESOURCE_DEPLETED":
                self._food_count = 0
        except Exception as exc:
            log.error("[Somatic] emergency healing failed: %s", exc)

    def _detect_stamina_bar(self, frame) -> float:
        """Detect stamina bar fill ratio via HSV masking."""
        if cv2 is None:
            return 0.8

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1 = int(self._config.stamina_roi[0] * sx * self._REF_W)
        y1 = int(self._config.stamina_roi[1] * sy * self._REF_H)
        x2 = int(self._config.stamina_roi[2] * sx * self._REF_W)
        y2 = int(self._config.stamina_roi[3] * sy * self._REF_H)

        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        if x1 >= x2 or y1 >= y2:
            return 0.8

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.8

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        s_low, s_high = self._config.stamina_low, self._config.stamina_high
        low_np = __import__('numpy').array(s_low)
        high_np = __import__('numpy').array(s_high)
        mask = cv2.inRange(hsv, low_np, high_np)
        filled_pixels = cv2.countNonZero(mask)
        total_pixels = (x2 - x1) * (y2 - y1)
        ratio = filled_pixels / max(total_pixels, 1)
        return min(max(ratio, 0.0), 1.0)

    def _detect_health_bar(self, frame) -> float:
        """Detect health bar fill ratio via HSV masking."""
        if cv2 is None:
            return 0.75

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1 = int(self._config.health_roi[0] * sx * self._REF_W)
        y1 = int(self._config.health_roi[1] * sy * self._REF_H)
        x2 = int(self._config.health_roi[2] * sx * self._REF_W)
        y2 = int(self._config.health_roi[3] * sy * self._REF_H)

        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        if x1 >= x2 or y1 >= y2:
            return 0.75

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.75

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_low, h_high = self._config.health_low, self._config.health_high
        low_np = __import__('numpy').array(h_low)
        high_np = __import__('numpy').array(h_high)
        mask = cv2.inRange(hsv, low_np, high_np)
        filled_pixels = cv2.countNonZero(mask)
        total_pixels = (x2 - x1) * (y2 - y1)
        ratio = filled_pixels / max(total_pixels, 1)
        return min(max(ratio, 0.0), 1.0)

    def _detect_hazards(self, frame) -> tuple[HazardLevel, str | None]:
        """Detect environmental hazard indicators (Sheer Cold, Phlogiston)."""
        if cv2 is None:
            return HazardLevel.SAFE, None

        h, w = frame.shape[:2]
        # Sample center area for hazard effects
        cx, cy = w // 2, h // 2
        roi_size = min(w, h) // 4
        x1, y1 = cx - roi_size, cy - roi_size
        x2, y2 = cx + roi_size, cy + roi_size
        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        if x1 >= x2 or y1 >= y2:
            return HazardLevel.SAFE, None

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return HazardLevel.SAFE, None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for Sheer Cold (blue-white)
        sc_low = __import__('numpy').array(self._config.sheer_cold_low)
        sc_high = __import__('numpy').array(self._config.sheer_cold_high)
        sc_mask = cv2.inRange(hsv, sc_low, sc_high)
        sc_pixels = cv2.countNonZero(sc_mask)

        if sc_pixels > 200:
            return HazardLevel.DANGER, "sheer_cold"

        # Check for Phlogiston (orange-red)
        ph_low = __import__('numpy').array(self._config.phlogiston_low)
        ph_high = __import__('numpy').array(self._config.phlogiston_high)
        ph_mask = cv2.inRange(hsv, ph_low, ph_high)
        ph_pixels = cv2.countNonZero(ph_mask)

        if ph_pixels > 200:
            return HazardLevel.WARNING, "phlogiston"

        return HazardLevel.SAFE, None

    def _classify_stamina_zone(self, ratio: float) -> StaminaZone:
        cfg = self._config
        if ratio >= cfg.stamina_full_threshold:
            return StaminaZone.FULL
        if ratio >= cfg.stamina_normal_threshold:
            return StaminaZone.NORMAL
        if ratio >= cfg.stamina_low_threshold:
            return StaminaZone.LOW
        if ratio >= cfg.stamina_critical_threshold:
            return StaminaZone.CRITICAL
        return StaminaZone.EMPTY

    def _classify_health_zone(self, ratio: float) -> HealthZone:
        cfg = self._config
        if ratio >= cfg.health_full_threshold:
            return HealthZone.FULL
        if ratio >= cfg.health_normal_threshold:
            return HealthZone.NORMAL
        if ratio >= cfg.health_low_threshold:
            return HealthZone.LOW
        if ratio >= cfg.health_critical_threshold:
            return HealthZone.CRITICAL
        return HealthZone.DEAD

    def _detect_stamina_recovery(self) -> bool:
        if len(self._stamina_history) < 5:
            return False
        recent = self._stamina_history[-5:]
        return recent[-1] > recent[0]

    def _detect_health_recovery(self) -> bool:
        if len(self._health_history) < 5:
            return False
        recent = self._health_history[-5:]
        return recent[-1] > recent[0]

    def _determine_action(
        self,
        stamina_ratio: float,
        stamina_zone: StaminaZone,
        health_ratio: float,
        health_zone: HealthZone,
        hazard_level: HazardLevel,
        stamina_recovering: bool,
    ) -> str:
        if stamina_zone == StaminaZone.EMPTY:
            return "halt_and_wait"
        if stamina_zone == StaminaZone.CRITICAL:
            return "halt_immediately"
        if stamina_zone == StaminaZone.LOW and not stamina_recovering:
            return "prepare_to_halt"
        if health_zone == HealthZone.CRITICAL:
            return "emergency_heal"
        if health_zone == HealthZone.LOW:
            return "find_safe_spot"
        if hazard_level == HazardLevel.LETHAL:
            return "escape_hazard"
        if hazard_level == HazardLevel.DANGER:
            return "move_to_shelter"
        if stamina_zone == StaminaZone.NORMAL and stamina_recovering:
            return "wait_for_recovery"
        return "normal_traversal"

    def _detect_oxygen_bar(self, frame) -> float:
        """Detect oxygen bar fill ratio via HSV masking (blue-green oxygen bubble in Fontaine)."""
        if cv2 is None or frame is None or frame.size == 0:
            return 1.0
        # ROI is around character's side or middle right
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H
        # Sample an ROI where oxygen bubble appears (typically center-right)
        x1 = int(0.85 * sx * self._REF_W)
        y1 = int(0.50 * sy * self._REF_H)
        x2 = int(0.95 * sx * self._REF_W)
        y2 = int(0.65 * sy * self._REF_H)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 1.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Light blue / cyan oxygen mask
        low_np = __import__('numpy').array((80, 50, 100))
        high_np = __import__('numpy').array((110, 255, 255))
        mask = cv2.inRange(hsv, low_np, high_np)
        filled_pixels = cv2.countNonZero(mask)
        total_pixels = (x2 - x1) * (y2 - y1)
        ratio = filled_pixels / max(total_pixels, 1)
        # Scale to ratio (bubbles typically fill up to 15% of ROI pixels max, scale accordingly)
        return min(max(ratio / 0.15, 0.0), 1.0)

    def _default_state(self, now: float) -> VitalSigns:
        return VitalSigns(
            stamina_ratio=0.8,
            stamina_zone=StaminaZone.FULL,
            health_ratio=0.75,
            health_zone=HealthZone.FULL,
            hazard_level=HazardLevel.SAFE,
            hazard_type=None,
            stamina_recovering=False,
            health_recovering=False,
            recovery_mode=self._recovery_mode,
            recommended_action="normal_traversal",
            timestamp=now,
            oxygen_ratio=1.0,
            stamina_buffer=1.0,
        )

    def reset(self) -> None:
        """Reset supervisor state."""
        self._recovery_mode = False
        self._last_eat_time = 0.0
        self._stamina_history.clear()
        self._health_history.clear()
        self._frame_count = 0

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))