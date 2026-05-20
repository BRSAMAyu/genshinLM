from __future__ import annotations

import threading
import uuid
from typing import Protocol

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from perception.capture_base import FramePacket

from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from benchmarks.reflex_gauntlet.scenario import (
    ReflexScenario,
    compute_danger_score_for_frame,
    create_frame_for_scenario,
)
from reflex.scheduler import PreemptionToken, ReflexScheduler, ResumeContract


class SyntheticCapturer:
    """Synthetic screen capturer that yields pre-built frames on demand."""

    def __init__(self, frames: list[FramePacket]) -> None:
        self._frames = list(frames)
        self._index = 0
        self._started = False

    def start(self) -> None:
        self._started = True

    def get_latest_frame(self) -> FramePacket | None:
        if not self._started:
            return None
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def stop(self) -> None:
        self._started = False


class ReflexGauntletRunner:
    """Runs a single reflex scenario and collects metrics."""

    def __init__(
        self,
        scenario: ReflexScenario,
        scheduler: ReflexScheduler | None = None,
        timebase: Timebase | None = None,
    ) -> None:
        self._scenario = scenario
        self._timebase = timebase or Timebase()
        self._scheduler = scheduler or ReflexScheduler(
            danger_threshold=0.5,
            cooldown_frames=10,
            timebase=self._timebase,
        )

    def run(self) -> BenchmarkResult:
        """Execute the scenario and collect timing metrics."""
        total_frames = (
            self._scenario.danger_delay_frames
            + self._scenario.danger_duration_frames
            + 30  # extra frames for recovery observation
        )
        if total_frames < 1:
            total_frames = 40

        evidence_ids: list[str] = []
        dodges = 0
        max_consecutive = 0
        current_consecutive = 0
        active_token: PreemptionToken | None = None
        resume_contracts: list[ResumeContract] = []

        t_danger_start: float | None = None
        t_first_observation_after_danger: float | None = None
        t_first_interrupt: float | None = None
        t_lease_issued: float | None = None
        t_danger_cleared: float | None = None

        frame_to_observation_ms = 0.0
        observation_to_interrupt_ms = 0.0
        interrupt_to_lease_ms = 0.0
        danger_clear_time_ms = 0.0

        for frame_id in range(total_frames):
            danger_active = (
                frame_id >= self._scenario.danger_delay_frames
                and frame_id
                < self._scenario.danger_delay_frames + self._scenario.danger_duration_frames
            )

            # Create synthetic frame
            frame = create_frame_for_scenario(
                self._scenario, frame_id, self._timebase, danger_active
            )

            # Compute danger score
            danger_score = compute_danger_score_for_frame(
                self._scenario, frame_id, danger_active
            )

            # Simulate observation publish
            t_obs = self._timebase.now()
            observation = Observation(
                frame_id=frame_id,
                t_capture=frame.timestamp,
                t_processed=t_obs,
                latency_ms=(t_obs - frame.timestamp) * 1000.0,
                viewport_size=(640, 360),
                target_track=None,
                obstacle_field=None,
                ui_state=None,
                visual_triggers={"danger_active": danger_active},
                os_focus=FocusState(focused=True),
            )

            if t_danger_start is None and danger_active:
                t_danger_start = self._timebase.now()
                t_first_observation_after_danger = t_obs
                frame_to_observation_ms = (t_obs - frame.timestamp) * 1000.0

            # Evaluate reflex
            token = self._scheduler.evaluate(danger_score, self._scenario.danger_type, frame_id)
            if token is not None:
                dodges += 1
                current_consecutive += 1
                if current_consecutive > max_consecutive:
                    max_consecutive = current_consecutive
                active_token = token
                evidence_ids.append(f"evidence_preempt_{token.token_id}_frame_{frame_id}")

                if t_first_interrupt is None and t_danger_start is not None:
                    t_first_interrupt = self._timebase.now()
                    observation_to_interrupt_ms = (
                        (t_first_interrupt - t_first_observation_after_danger) * 1000.0
                        if t_first_observation_after_danger is not None
                        else 0.0
                    )
                    t_lease_issued = self._timebase.now()
                    interrupt_to_lease_ms = (t_lease_issued - t_first_interrupt) * 1000.0

                # Build interrupt
                interrupt = self._scheduler.make_interrupt(token)

            if not danger_active:
                current_consecutive = 0

            # Check danger clear when we have an active token and danger is gone
            if active_token is not None and not danger_active:
                resume = self._scheduler.verify_danger_cleared(
                    active_token, danger_score, evidence_ids=[f"clear_{frame_id}"]
                )
                if resume is not None:
                    resume_contracts.append(resume)
                    evidence_ids.append(f"evidence_resume_{resume.contract_id}_frame_{frame_id}")
                    if t_danger_cleared is None and t_danger_start is not None:
                        t_danger_cleared = self._timebase.now()
                        danger_clear_time_ms = (t_danger_cleared - t_danger_start) * 1000.0
                    active_token = None

        # Compute metrics
        total_clear_checks = self._scheduler.clear_verifier._total_checks
        false_clear_rate = (
            self._scheduler.clear_verifier.false_clear_count / total_clear_checks
            if total_clear_checks > 0
            else 0.0
        )
        resume_success = 1.0 if resume_contracts else 0.0
        dodge_ok = dodges >= self._scenario.expected_dodges
        false_clear_ok = false_clear_rate <= 0.1
        task_success = dodge_ok and false_clear_ok
        evidence_coverage = len(evidence_ids) / max(dodges * 2, 1)

        metrics = BenchmarkMetrics(
            frame_to_observation_ms=frame_to_observation_ms,
            observation_to_interrupt_ms=observation_to_interrupt_ms,
            interrupt_to_lease_ms=interrupt_to_lease_ms,
            danger_clear_time_ms=danger_clear_time_ms,
            danger_false_clear_rate=false_clear_rate,
            resume_success_rate=resume_success,
            max_consecutive_dodges=max_consecutive,
            final_task_success=task_success,
            evidence_coverage=evidence_coverage,
        )

        return BenchmarkResult(
            benchmark_id=f"reflex_{self._scenario.name}",
            run_id=str(uuid.uuid4())[:8],
            suite_name="reflex_gauntlet",
            scenario_name=self._scenario.name,
            passed=task_success,
            metrics=metrics,
            evidence_ids=evidence_ids,
            report={
                "dodges": dodges,
                "expected_dodges": self._scenario.expected_dodges,
                "resume_contracts": len(resume_contracts),
                "total_frames": total_frames,
            },
        )
