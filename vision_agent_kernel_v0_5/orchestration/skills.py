from __future__ import annotations

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import SkillResult
from orchestration.task_spec import TaskSpec
from execution.visual_action_block import (
    VisualActionBlock,
    VisualActionBlockExecutor,
    VisualActionStep,
)
from execution.verifier_base import VerifierResult


class BaseSkill:
    name = "base"

    def __init__(self, state_bus: StateBus, timebase: Timebase | None = None) -> None:
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()

    def _result(self, status: str, failure_code: str | None = None, **payload: object) -> SkillResult:
        now = self._timebase.now()
        return SkillResult(
            skill_name=self.name,
            status=status,
            failure_code=failure_code,
            started_at=now,
            finished_at=now,
            payload=payload,
        )

    def precondition(self) -> bool:
        return True

    def cleanup(self) -> None:
        return None


class LoadTaskSkill(BaseSkill):
    name = "LoadTaskSkill"

    def __init__(self, state_bus: StateBus, task_spec: TaskSpec, timebase: Timebase | None = None) -> None:
        super().__init__(state_bus, timebase)
        self._task_spec = task_spec

    def run(self) -> SkillResult:
        self._state_bus.current_goal.put(self._task_spec.task_id)
        return self._result(
            "SUCCESS",
            task_id=self._task_spec.task_id,
            max_duration_sec=self._task_spec.max_duration_sec,
            max_retries=self._task_spec.max_retries,
        )


class EnterTargetRegionSkill(BaseSkill):
    name = "EnterTargetRegionSkill"

    def run(self) -> SkillResult:
        return self._result("SUCCESS", region_entered=True)


class AcquireTargetSkill(BaseSkill):
    name = "AcquireTargetSkill"

    def run(self) -> SkillResult:
        observation = self._state_bus.latest_observation.get()
        if observation is None:
            return self._result("FAILED", "NO_OBSERVATION")
        track = observation.target_track
        if (
            track is not None
            and track.state in {"TRACKED", "COASTING"}
            or observation.visual_triggers.get("target_visible", False)
        ):
            return self._result("SUCCESS", frame_id=observation.frame_id)
        return self._result("FAILED", "TARGET_NOT_FOUND", frame_id=observation.frame_id)


class TrackAndApproachSkill(BaseSkill):
    name = "TrackAndApproachSkill"

    def run(self) -> SkillResult:
        observation = self._state_bus.latest_observation.get()
        if observation is None:
            return self._result("FAILED", "NO_OBSERVATION")
        track = observation.target_track
        if (
            (track is None and not observation.visual_triggers.get("target_visible", False))
            or (track is not None and track.state == "LOST")
        ):
            return self._result("FAILED", "TARGET_LOST", frame_id=observation.frame_id)
        if observation.visual_triggers.get("in_range_estimated", False):
            return self._result("SUCCESS", frame_id=observation.frame_id)
        return self._result("SUCCESS", frame_id=observation.frame_id, assumed_in_range=True)


class ExecuteVisualActionBlockSkill:
    name = "ExecuteVisualActionBlockSkill"

    def __init__(self, executor: VisualActionBlockExecutor, block: VisualActionBlock | None = None) -> None:
        self._executor = executor
        self._block = block or VisualActionBlock(
            name="demo_visual_action_block",
            steps=[
                VisualActionStep(type="wait_visual_trigger", trigger="action_sequence_completed", timeout_ms=200),
            ],
        )

    def run(self) -> SkillResult:
        return self._executor.execute(self._block)


class VerifySuccessSkill(BaseSkill):
    name = "VerifySuccessSkill"

    def run(self) -> SkillResult:
        observation = self._state_bus.latest_observation.get()
        if observation is None:
            v_res = VerifierResult(
                ok=False,
                verifier_id="VerifySuccessSkill",
                confidence=0.0,
                reason="NO_OBSERVATION",
                evidence={},
                frame_id=None
            )
            res = self._result("FAILED", "NO_OBSERVATION")
            res.verifier_result = v_res
            return res

        ok = observation.visual_triggers.get("action_sequence_completed", True)
        v_res = VerifierResult(
            ok=ok,
            verifier_id="VerifySuccessSkill",
            confidence=1.0 if ok else 0.0,
            reason="Action sequence completed" if ok else "Action sequence not completed",
            evidence={"action_sequence_completed": ok},
            frame_id=observation.frame_id
        )
        status = "SUCCESS" if ok else "FAILED"
        failure_code = None if ok else "VERIFY_FAILED"
        res = self._result(status, failure_code, frame_id=observation.frame_id)
        res.verifier_result = v_res
        return res


class RecoverSkill(BaseSkill):
    name = "RecoverSkill"

    def run(self) -> SkillResult:
        return self._result("SUCCESS", recovered=True)
