from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from core.events import Interrupt
from core.state_bus import StateBus
from core.types import Observation, ProgressState


@dataclass(frozen=True, slots=True)
class ProgressSupervisorConfig:
    slope_window_sec: float = 2.0
    visibility_window_sec: float = 1.0
    history_window_sec: float = 5.0
    ewma_alpha: float = 0.3
    positive_slope_threshold: float = 0.05
    flat_slope_epsilon: float = 0.02
    stale_penalty: float = 8.0
    low_visibility_penalty: float = 5.0
    flat_progress_penalty: float = 2.0
    oscillation_penalty: float = 4.0
    obstacle_penalty: float = 3.0
    recovery_reward: float = 4.0
    micro_recovery: float = 10.0
    no_task_progress: float = 30.0
    escalate: float = 80.0
    target_lost_after_ms: float = 3000.0
    interrupt_cooldown_sec: float = 0.5


@dataclass(frozen=True, slots=True)
class ProgressSample:
    timestamp: float
    progress: float
    visible: bool
    center_x: float | None
    obstacle_pressure: float
    stale: bool


class ProgressSupervisor:
    def __init__(
        self,
        state_bus: StateBus | None = None,
        config: ProgressSupervisorConfig | None = None,
    ) -> None:
        self._state_bus = state_bus
        self._config = config or ProgressSupervisorConfig()
        self._samples: deque[ProgressSample] = deque()
        self._ewma_progress = 0.0
        self._frustration = 0.0
        self._last_interrupt_code: str | None = None
        self._last_interrupt_time = -1e9
        self._last_observation: Observation | None = None

    def update(self, observation: Observation) -> ProgressState:
        self._last_observation = observation
        sample = self._sample_observation(observation)
        self._samples.append(sample)
        self._trim(sample.timestamp)
        self._ewma_progress = (
            sample.progress
            if len(self._samples) == 1
            else self._config.ewma_alpha * sample.progress
            + (1.0 - self._config.ewma_alpha) * self._ewma_progress
        )
        slope = self._window_slope(sample.timestamp, self._config.slope_window_sec)
        visibility_ratio = self._visibility_ratio(sample.timestamp, self._config.visibility_window_sec)
        oscillation = self._oscillation_score(sample.timestamp, self._config.slope_window_sec)
        self._frustration = self._update_frustration(
            sample=sample,
            slope=slope,
            visibility_ratio=visibility_ratio,
            oscillation_score=oscillation,
        )
        active_interrupt = self._active_interrupt(sample.timestamp)
        state = ProgressState(
            timestamp=sample.timestamp,
            ewma_progress=self._ewma_progress,
            progress_slope_2s=slope,
            visibility_ratio_1s=visibility_ratio,
            oscillation_score=oscillation,
            frustration=self._frustration,
            trend=self._trend_for(slope),
            active_interrupt=active_interrupt,
        )
        if self._state_bus is not None:
            self._state_bus.publish_progress(state)
            if active_interrupt is not None:
                self._state_bus.publish_interrupt(active_interrupt)
        print(
            "[ProgressSupervisor] "
            f"progress={sample.progress:.3f} ewma={state.ewma_progress:.3f} "
            f"slope={state.progress_slope_2s:.3f} visibility={visibility_ratio:.3f} "
            f"oscillation={oscillation:.3f} frustration={state.frustration:.3f} "
            f"trend={state.trend}",
            flush=True,
        )
        return state

    def _sample_observation(self, observation: Observation) -> ProgressSample:
        track = observation.target_track
        visible = track is not None and track.state == "TRACKED"
        viewport_width, _ = observation.viewport_size
        center_x: float | None = None
        target_visibility_score = 1.0 if visible else 0.0
        target_centering_score = 0.0
        identity_stability_score = 0.0
        range_improvement_score = 0.0

        if track is not None:
            identity_stability_score = track.identity_confidence
            if track.estimated_range is not None:
                range_improvement_score = 1.0 / max(track.estimated_range, 1.0)
            if track.smoothed_center_px is not None:
                center_x = track.smoothed_center_px[0]
                normalized_error = abs(center_x - viewport_width / 2.0) / (viewport_width / 2.0)
                target_centering_score = max(0.0, 1.0 - normalized_error)

        obstacle_pressure = 0.0
        if observation.obstacle_field is not None:
            obstacle_pressure = max(observation.obstacle_field.sectors.values(), default=0.0)

        stale_penalty = 0.5 if observation.stale else 0.0
        obstacle_penalty = obstacle_pressure
        progress = (
            target_visibility_score
            + target_centering_score
            + range_improvement_score
            + identity_stability_score
            - obstacle_penalty
            - stale_penalty
        )
        return ProgressSample(
            timestamp=observation.t_processed,
            progress=progress,
            visible=visible,
            center_x=center_x,
            obstacle_pressure=obstacle_pressure,
            stale=observation.stale,
        )

    def _trim(self, now: float) -> None:
        cutoff = now - self._config.history_window_sec
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()

    def _window_slope(self, now: float, window_sec: float) -> float:
        window = [sample for sample in self._samples if sample.timestamp >= now - window_sec]
        if len(window) < 2:
            return 0.0
        first = window[0]
        last = window[-1]
        dt = max(last.timestamp - first.timestamp, 1e-6)
        return (last.progress - first.progress) / dt

    def _visibility_ratio(self, now: float, window_sec: float) -> float:
        window = [sample for sample in self._samples if sample.timestamp >= now - window_sec]
        if not window:
            return 0.0
        return sum(1 for sample in window if sample.visible) / len(window)

    def _oscillation_score(self, now: float, window_sec: float) -> float:
        centers = [
            sample.center_x
            for sample in self._samples
            if sample.timestamp >= now - window_sec and sample.center_x is not None
        ]
        if len(centers) < 3:
            return 0.0
        direction_changes = 0
        last_sign = 0
        for previous, current in zip(centers, centers[1:]):
            delta = current - previous
            sign = 1 if delta > 0 else -1 if delta < 0 else 0
            if sign != 0 and last_sign != 0 and sign != last_sign:
                direction_changes += 1
            if sign != 0:
                last_sign = sign
        return min(1.0, direction_changes / max(len(centers) - 2, 1))

    def _update_frustration(
        self,
        sample: ProgressSample,
        slope: float,
        visibility_ratio: float,
        oscillation_score: float,
    ) -> float:
        frustration = self._frustration
        if sample.stale:
            frustration += self._config.stale_penalty
        if visibility_ratio < 0.5:
            frustration += self._config.low_visibility_penalty
        if abs(slope) <= self._config.flat_slope_epsilon:
            frustration += self._config.flat_progress_penalty
        elif slope > self._config.positive_slope_threshold:
            frustration -= self._config.recovery_reward
        if oscillation_score > 0.5:
            frustration += self._config.oscillation_penalty
        if sample.obstacle_pressure > 0.7 and slope <= self._config.flat_slope_epsilon:
            frustration += self._config.obstacle_penalty
        return max(0.0, min(100.0, frustration))

    def _trend_for(self, slope: float) -> str:
        if slope > self._config.positive_slope_threshold:
            return "IMPROVING"
        if slope < -self._config.positive_slope_threshold:
            return "DEGRADING"
        return "FLAT"

    def _active_interrupt(self, timestamp: float) -> Interrupt | None:
        observation = self._last_observation
        track = observation.target_track if observation is not None else None
        if (
            track is not None
            and track.state == "LOST"
            and track.missing_duration_ms >= self._config.target_lost_after_ms
        ):
            return self._cooldown_interrupt(
                timestamp,
                "TARGET_LOST",
                {
                    "missing_duration_ms": track.missing_duration_ms,
                    "frustration": self._frustration,
                },
            )
        if self._frustration >= self._config.escalate:
            return self._cooldown_interrupt(
                timestamp,
                "NO_TASK_PROGRESS",
                {"frustration": self._frustration},
            )
        return None

    def _cooldown_interrupt(
        self,
        timestamp: float,
        code: str,
        payload: dict[str, float],
    ) -> Interrupt | None:
        if (
            self._last_interrupt_code == code
            and timestamp - self._last_interrupt_time < self._config.interrupt_cooldown_sec
        ):
            return None
        self._last_interrupt_code = code
        self._last_interrupt_time = timestamp
        return Interrupt(
            priority=2,
            timestamp=timestamp,
            code=code,
            source="progress_supervisor",
            payload=payload,
            recoverable=True,
        )
