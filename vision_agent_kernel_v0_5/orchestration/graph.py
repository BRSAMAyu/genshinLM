from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.events import Interrupt
from core.types import SkillResult


INIT = "INIT"
LOAD_TASK = "LOAD_TASK"
ENTER_TARGET_REGION = "ENTER_TARGET_REGION"
ACQUIRE_TARGET = "ACQUIRE_TARGET"
TRACK_AND_APPROACH = "TRACK_AND_APPROACH"
EXECUTE_VISUAL_ACTION_BLOCK = "EXECUTE_VISUAL_ACTION_BLOCK"
VERIFY_SUCCESS = "VERIFY_SUCCESS"
RECOVER = "RECOVER"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous_state: str
    next_state: str
    reason: str


class OrchestrationGraph:
    def __init__(self) -> None:
        self._custom_transitions: list[tuple[str, str, str]] = []

    def register_transition(self, from_state: str, to_state: str, condition: str | Callable) -> None:
        self._custom_transitions.append((from_state, to_state, condition))

    def unregister_transition(self, from_state: str, to_state: str, condition: str | Callable) -> bool:
        before = len(self._custom_transitions)
        self._custom_transitions = [
            item for item in self._custom_transitions
            if item != (from_state, to_state, condition)
        ]
        return len(self._custom_transitions) != before

    def custom_transitions_snapshot(self) -> list[tuple[str, str, str | Callable]]:
        return list(self._custom_transitions)

    def next_for_skill_result(self, state: str, result: SkillResult) -> StateTransition:
        status = result.status
        failure = result.failure_code or ""
        if status == "CANCELLED":
            return StateTransition(state, RECOVER, f"cancelled:{failure}")
        if state == INIT:
            return StateTransition(state, LOAD_TASK, "bootstrapped")
        if state == LOAD_TASK:
            if status == "SUCCESS":
                return StateTransition(state, ENTER_TARGET_REGION, "task_loaded")
            return StateTransition(state, FAILED, failure or "task_load_failed")
        if state == ENTER_TARGET_REGION:
            if status == "SUCCESS":
                return StateTransition(state, ACQUIRE_TARGET, "target_region_entered")
            if failure == "NO_TASK_PROGRESS":
                return StateTransition(state, RECOVER, failure)
            return StateTransition(state, FAILED, failure or "enter_region_failed")
        if state == ACQUIRE_TARGET:
            if status == "SUCCESS":
                return StateTransition(state, TRACK_AND_APPROACH, "target_acquired")
            return StateTransition(state, RECOVER, failure or "target_not_found")
        if state == TRACK_AND_APPROACH:
            if status == "SUCCESS":
                return StateTransition(state, EXECUTE_VISUAL_ACTION_BLOCK, "in_range")
            if failure == "TARGET_LOST":
                return StateTransition(state, ACQUIRE_TARGET, failure)
            if failure in {"NO_TASK_PROGRESS", "OBSTACLE_BLOCKING"}:
                return StateTransition(state, RECOVER, failure)
            return StateTransition(state, FAILED, failure or "track_and_approach_failed")
        if state == EXECUTE_VISUAL_ACTION_BLOCK:
            if status == "SUCCESS":
                return StateTransition(state, VERIFY_SUCCESS, "action_block_success")
            if status in {"CANCELLED", "TIMEOUT"}:
                return StateTransition(state, RECOVER, failure or status)
            return StateTransition(state, FAILED, failure or "action_block_failed")
        if state == VERIFY_SUCCESS:
            if status == "SUCCESS":
                return StateTransition(state, COMPLETE, "verified")
            return StateTransition(state, RECOVER, failure or "verification_failed")
        if state == RECOVER:
            if status == "SUCCESS":
                return StateTransition(state, ACQUIRE_TARGET, "recovered")
            if failure == "RECOVERY_RETRY":
                return StateTransition(state, ACQUIRE_TARGET, failure)
            return StateTransition(state, FAILED, failure or "recovery_failed")
        for from_s, to_s, cond in self._custom_transitions:
            if state == from_s:
                if callable(cond):
                    try:
                        if cond(result):
                            return StateTransition(state, to_s, "custom_callable")
                    except Exception:
                        pass
                elif status == cond or failure == cond:
                    return StateTransition(state, to_s, f"custom:{cond}")
        return StateTransition(state, state, "terminal_or_unknown")

    def next_for_interrupt(self, state: str, interrupt: Interrupt) -> StateTransition:
        if interrupt.priority == 0:
            return StateTransition(state, INTERRUPTED, interrupt.code)
        if interrupt.priority == 1:
            return StateTransition(state, RECOVER, interrupt.code)
        if state == TRACK_AND_APPROACH and interrupt.code == "TARGET_LOST":
            return StateTransition(state, ACQUIRE_TARGET, interrupt.code)
        if state == ACQUIRE_TARGET and interrupt.code == "TARGET_LOST":
            return StateTransition(state, RECOVER, interrupt.code)
        if interrupt.code in {"TARGET_LOST", "NO_TASK_PROGRESS", "OBSTACLE_BLOCKING"}:
            return StateTransition(state, RECOVER, interrupt.code)
        return StateTransition(state, state, f"ignored_interrupt:{interrupt.code}")
