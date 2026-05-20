from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease, Observation, SkillResult
from execution.input_worker import InputWorker


class VisualActionBlockInterrupted(RuntimeError):
    def __init__(self, interrupt: Interrupt) -> None:
        self.interrupt = interrupt
        super().__init__(f"visual action block interrupted: {interrupt.code}")


class VisualActionBlockTimeout(RuntimeError):
    pass


TelemetrySink = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class VisualActionStep:
    type: str
    key: str | None = None
    lease_ms: int = 120
    trigger: str | None = None
    timeout_ms: int = 1000
    min_confidence: float = 0.0
    intent: str | None = None


@dataclass(frozen=True, slots=True)
class VisualActionBlock:
    name: str
    steps: list[VisualActionStep]
    precondition: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


class VisualActionBlockExecutor:
    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        timebase: Timebase | None = None,
        wait_chunk_ms: int = 50,
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        if wait_chunk_ms <= 0 or wait_chunk_ms > 100:
            raise ValueError("wait_chunk_ms must be in 1..100")
        self._state_bus = state_bus
        self._input_worker = input_worker
        self._timebase = timebase or Timebase()
        self._wait_chunk_sec = wait_chunk_ms / 1000.0
        self._telemetry_sink = telemetry_sink

    def execute(self, block: VisualActionBlock) -> SkillResult:
        started_at = self._timebase.now()
        final_payload: dict[str, Any] = {}
        print(f"[VisualActionBlock] start name={block.name}", flush=True)
        try:
            self._check_interrupt()
            self._check_preconditions(block)
            for index, step in enumerate(block.steps):
                self._check_interrupt()
                self._emit_telemetry(
                    "action_block_step_start",
                    {"block": block.name, "step_index": index, "step_type": step.type},
                )
                self._emit_telemetry(
                    "combo_step_start",
                    {"block": block.name, "step_index": index, "step_type": step.type},
                )
                print(
                    "[VisualActionBlock] "
                    f"name={block.name} step_index={index} type={step.type}",
                    flush=True,
                )
                if step.type == "press_key":
                    self._press_key(block.name, step)
                elif step.type == "wait_visual_trigger":
                    self._wait_visual_trigger(step)
                elif step.type == "emit_action_intent":
                    emitted = self._emit_action_intent(block.name, step)
                    final_payload.setdefault("emitted_intents", []).append(emitted)
                elif step.type in {"branch_on_visual_state", "retry_until", "fallback_basic_loop", "pause_and_reacquire"}:
                    final_payload.setdefault("combo_steps", []).append({"step_index": index, "type": step.type, "status": "dry_run_supported"})
                else:
                    raise ValueError(f"unsupported visual action step type: {step.type}")
                self._emit_telemetry(
                    "action_block_step_success",
                    {"block": block.name, "step_index": index, "step_type": step.type},
                )
                self._emit_telemetry(
                    "combo_step_success",
                    {"block": block.name, "step_index": index, "step_type": step.type},
                )
            final_payload["final_ui_state_estimate"] = self._final_ui_state()
            status = "SUCCESS"
            failure_code = None
        except VisualActionBlockInterrupted as exc:
            final_payload["interrupt"] = {
                "code": exc.interrupt.code,
                "priority": exc.interrupt.priority,
                "source": exc.interrupt.source,
                "payload": exc.interrupt.payload,
            }
            final_payload["final_ui_state_estimate"] = self._final_ui_state()
            status = "CANCELLED"
            failure_code = exc.interrupt.code
            self._emit_telemetry(
                "combo_interrupted",
                {"block": block.name, "interrupt": exc.interrupt.code, "priority": exc.interrupt.priority},
            )
        except VisualActionBlockTimeout as exc:
            self._emit_telemetry(
                "action_block_timeout",
                {"block": block.name, "failure_code": str(exc)},
            )
            self._emit_telemetry(
                "combo_step_timeout",
                {"block": block.name, "failure_code": str(exc)},
            )
            final_payload["final_ui_state_estimate"] = self._final_ui_state()
            status = "TIMEOUT"
            failure_code = str(exc)
        except Exception as exc:
            final_payload["final_ui_state_estimate"] = self._final_ui_state()
            status = "FAILED"
            failure_code = repr(exc)
        finished_at = self._timebase.now()
        result = SkillResult(
            skill_name=block.name,
            status=status,
            failure_code=failure_code,
            started_at=started_at,
            finished_at=finished_at,
            payload=final_payload,
        )
        self._emit_telemetry(
            "skill_result",
            {
                "skill_name": result.skill_name,
                "status": result.status,
                "failure_code": result.failure_code,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "payload": result.payload,
            },
        )
        print(f"[VisualActionBlock] finished result={result}", flush=True)
        return result

    def _press_key(self, block_name: str, step: VisualActionStep) -> None:
        if step.key is None:
            raise ValueError("press_key step requires key")
        now = self._timebase.now()
        lease = InputLease(
            lease_id=str(uuid.uuid4()),
            owner=f"visual_action_block:{block_name}",
            priority=30,
            key_states={step.key: "DOWN"},
            mouse_delta=None,
            created_at=now,
            expires_at=now + step.lease_ms / 1000.0,
            reason=f"visual_action_block:{block_name}:press_key:{step.key}",
        )
        if not self._input_worker.submit_lease(lease):
            raise RuntimeError("input worker rejected lease command")

    def _wait_visual_trigger(self, step: VisualActionStep) -> None:
        if step.trigger is None:
            raise ValueError("wait_visual_trigger step requires trigger")
        deadline = self._timebase.now() + step.timeout_ms / 1000.0
        while self._timebase.now() < deadline:
            self._check_interrupt()
            observation = self._state_bus.latest_observation.get()
            if observation is not None and observation.visual_triggers.get(step.trigger, False):
                self._emit_telemetry(
                    "visual_trigger_detected",
                    {"trigger": step.trigger, "frame_id": observation.frame_id},
                )
                print(
                    "[VisualActionBlock] "
                    f"trigger satisfied trigger={step.trigger}",
                    flush=True,
                )
                return
            remaining = max(0.0, deadline - self._timebase.now())
            time.sleep(min(self._wait_chunk_sec, remaining))
        raise VisualActionBlockTimeout(f"timeout waiting for trigger {step.trigger}")

    def _emit_action_intent(self, block_name: str, step: VisualActionStep) -> str:
        intent = step.intent or "ACTION_TRIGGERED"
        backend = self._input_worker.backend
        action_intent = getattr(backend, "action_intent", None)
        if callable(action_intent):
            action_intent(intent, reason=f"visual_action_block:{block_name}")
        else:
            print(
                "[VisualActionBlock] "
                f"action_intent intent={intent} reason=visual_action_block:{block_name}",
                flush=True,
            )
        print(intent, flush=True)
        return intent

    def _check_preconditions(self, block: VisualActionBlock) -> None:
        observation = self._state_bus.latest_observation.get()
        for trigger in block.precondition:
            if observation is None or not observation.visual_triggers.get(trigger, False):
                raise RuntimeError(f"precondition not satisfied: {trigger}")

    def _check_interrupt(self) -> None:
        deferred: list[Interrupt] = []
        interrupt = self._state_bus.next_interrupt(timeout=0.0)
        while interrupt is not None:
            if interrupt.priority <= 1 or interrupt.code == "TARGET_LOST":
                for item in deferred:
                    self._state_bus.publish_interrupt(item)
                print(
                    "[VisualActionBlock] "
                    f"preempted by interrupt code={interrupt.code} priority={interrupt.priority}",
                    flush=True,
                )
                raise VisualActionBlockInterrupted(interrupt)
            deferred.append(interrupt)
            interrupt = self._state_bus.next_interrupt(timeout=0.0)
        for item in deferred:
            self._state_bus.publish_interrupt(item)

    def _final_ui_state(self) -> dict[str, Any]:
        observation = self._state_bus.latest_observation.get()
        if observation is None or observation.ui_state is None:
            return {"available": False}
        return {
            "available": True,
            "frame_id": observation.ui_state.frame_id,
            "state": observation.ui_state.state,
            "confidence": observation.ui_state.confidence,
            "payload": observation.ui_state.payload,
        }

    def _emit_telemetry(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"timestamp": self._timebase.now(), "event": event_type, **payload}
        print(f"[VisualActionBlockTelemetry] {event}", flush=True)
        if self._telemetry_sink is not None:
            self._telemetry_sink(event_type, event)
