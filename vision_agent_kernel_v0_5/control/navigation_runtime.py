from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from core.types import InputLease

if TYPE_CHECKING:
    from core.state_bus import StateBus

log = logging.getLogger(__name__)


RecoveryAction = Literal["release_all", "backstep", "jump_forward", "turn_90", "escalate"]


@dataclass(frozen=True, slots=True)
class RouteSegment:
    segment_id: str
    target_waypoint: str
    expected_bearing: float
    max_duration_s: float
    verifier: str = "navigation_progress"
    tolerance_deg: float = 5.0
    stuck_policy: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NavigationSample:
    timestamp: float
    distance_to_target: float
    heading_error_deg: float
    optical_flow: float = 1.0
    progress: float = 0.0


@dataclass(frozen=True, slots=True)
class NavigationDecision:
    status: Literal["move", "recover", "arrived", "escalate"]
    reason: str
    lease: InputLease | None = None
    recovery_actions: list[RecoveryAction] = field(default_factory=list)


class HeadingServo:
    def __init__(self, gain: float = 0.25, dead_zone_deg: float = 3.0, max_mouse_delta: float = 80.0) -> None:
        self.gain = gain
        self.dead_zone_deg = dead_zone_deg
        self.max_mouse_delta = max_mouse_delta

    def mouse_delta_for(self, heading_error_deg: float) -> tuple[float, float] | None:
        if abs(heading_error_deg) <= self.dead_zone_deg:
            return None
        dx = max(-self.max_mouse_delta, min(self.max_mouse_delta, heading_error_deg * self.gain))
        return (dx, 0.0)


class StuckDetector:
    def __init__(self, min_progress_delta: float = 0.01, min_flow: float = 0.05, window: int = 4) -> None:
        self.min_progress_delta = min_progress_delta
        self.min_flow = min_flow
        self.window = window
        self._samples: list[NavigationSample] = []

    def update(self, sample: NavigationSample) -> bool:
        self._samples.append(sample)
        self._samples = self._samples[-self.window :]
        if len(self._samples) < self.window:
            return False
        progress_delta = self._samples[-1].progress - self._samples[0].progress
        avg_flow = sum(s.optical_flow for s in self._samples) / len(self._samples)
        distance_not_improving = self._samples[-1].distance_to_target >= self._samples[0].distance_to_target
        return progress_delta < self.min_progress_delta and avg_flow < self.min_flow and distance_not_improving


class NavigationController:
    def __init__(
        self,
        servo: HeadingServo | None = None,
        stuck: StuckDetector | None = None,
        state_bus: StateBus | None = None,
    ) -> None:
        self._servo = servo or HeadingServo()
        self._stuck = stuck or StuckDetector()
        self._state_bus = state_bus
        self._recoveries = 0

    def step(self, segment: RouteSegment, sample: NavigationSample, now: float) -> NavigationDecision:
        if sample.distance_to_target <= float(segment.stuck_policy.get("arrive_distance", 1.0)):
            decision = NavigationDecision("arrived", "within_tolerance")
            self._publish_decision(decision)
            return decision
        if self._stuck.update(sample):
            self._recoveries += 1
            if self._recoveries > int(segment.stuck_policy.get("max_recoveries", 2)):
                decision = NavigationDecision("escalate", "stuck_recovery_exhausted", recovery_actions=["escalate"])
                self._publish_decision(decision)
                return decision
            decision = NavigationDecision(
                "recover",
                "stuck_detected",
                recovery_actions=["release_all", "backstep", "jump_forward", "turn_90"],
            )
            self._publish_decision(decision)
            return decision
        mouse_delta = self._servo.mouse_delta_for(sample.heading_error_deg)
        lease = InputLease(
            lease_id=f"nav:{segment.segment_id}:{int(now * 1000)}",
            owner=f"navigation:{segment.segment_id}",
            priority=25,
            key_states={"W": "DOWN"},
            mouse_delta=mouse_delta,
            created_at=now,
            expires_at=now + 0.25,
            reason=f"move_segment:{segment.segment_id}",
        )
        decision = NavigationDecision("move", "progressing", lease=lease)
        self._publish_decision(decision)
        return decision

    def _publish_decision(self, decision: NavigationDecision) -> None:
        if self._state_bus is not None:
            try:
                self._state_bus.navigation_signal.put(decision)
            except Exception as exc:
                log.warning("failed to publish navigation decision to StateBus: %s", exc)
