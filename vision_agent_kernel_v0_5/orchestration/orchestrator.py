from __future__ import annotations

import threading

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import SkillResult
from orchestration.graph import (
    ACQUIRE_TARGET,
    COMPLETE,
    EXECUTE_VISUAL_ACTION_BLOCK,
    FAILED,
    INIT,
    INTERRUPTED,
    ENTER_TARGET_REGION,
    LOAD_TASK,
    RECOVER,
    TRACK_AND_APPROACH,
    VERIFY_SUCCESS,
    OrchestrationGraph,
    StateTransition,
)
from orchestration.skill_base import Skill


class Orchestrator:
    def __init__(
        self,
        state_bus: StateBus,
        skills: dict[str, Skill],
        graph: OrchestrationGraph | None = None,
        timebase: Timebase | None = None,
        tick_seconds: float = 0.05,
    ) -> None:
        self._state_bus = state_bus
        self._skills = skills
        self._graph = graph or OrchestrationGraph()
        self._timebase = timebase or Timebase()
        self._tick_seconds = tick_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = INIT
        self._transitions: list[StateTransition] = []
        self._results: list[SkillResult] = []

    @property
    def state(self) -> str:
        return self._state

    def transitions_snapshot(self) -> list[StateTransition]:
        return list(self._transitions)

    def results_snapshot(self) -> list[SkillResult]:
        return list(self._results)

    def force_state(self, state: str, reason: str = "forced") -> None:
        transition = StateTransition(self._state, state, reason)
        self._apply_transition(transition)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            print("[Orchestrator] start ignored; already running", flush=True)
            return
        print("[Orchestrator] starting orchestrator loop", flush=True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="orchestrator", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        print("[Orchestrator] stop requested", flush=True)
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def run_once(self) -> StateTransition:
        interrupt = self._state_bus.next_interrupt(timeout=0.0)
        if interrupt is not None:
            transition = self._graph.next_for_interrupt(self._state, interrupt)
            self._apply_transition(transition)
            return transition

        skill = self._skill_for_state(self._state)
        result = skill.run()
        self._results.append(result)
        transition = self._graph.next_for_skill_result(self._state, result)
        self._apply_transition(transition)
        return transition

    def _run_loop(self) -> None:
        print("[Orchestrator] loop entered", flush=True)
        try:
            while not self._stop_event.is_set() and self._state not in {COMPLETE, FAILED, INTERRUPTED}:
                self.run_once()
                self._stop_event.wait(self._tick_seconds)
        finally:
            print(f"[Orchestrator] loop exited state={self._state}", flush=True)

    def _skill_for_state(self, state: str) -> Skill:
        if state == INIT:
            return self._NoopSkill("InitBootstrap", self._timebase)
        mapping = {
            LOAD_TASK: "load_task",
            ENTER_TARGET_REGION: "enter_target_region",
            ACQUIRE_TARGET: "acquire_target",
            TRACK_AND_APPROACH: "track_and_approach",
            EXECUTE_VISUAL_ACTION_BLOCK: "execute_visual_action_block",
            VERIFY_SUCCESS: "verify_success",
            RECOVER: "recover",
        }
        key = mapping.get(state)
        if state in {LOAD_TASK, ENTER_TARGET_REGION} and (key is None or key not in self._skills):
            return self._NoopSkill(state.title().replace("_", ""), self._timebase)
        if key is None or key not in self._skills:
            return self._NoopSkill("UnknownState", self._timebase, status="FAILED", failure_code="UNKNOWN_STATE")
        return self._skills[key]

    def _apply_transition(self, transition: StateTransition) -> None:
        if transition.next_state != self._state:
            print(
                "[Orchestrator] "
                f"{transition.previous_state} -> {transition.next_state} reason={transition.reason}",
                flush=True,
            )
        self._state = transition.next_state
        self._state_bus.current_mode.put(self._state)
        self._transitions.append(transition)

    class _NoopSkill:
        def __init__(
            self,
            name: str,
            timebase: Timebase,
            status: str = "SUCCESS",
            failure_code: str | None = None,
        ) -> None:
            self.name = name
            self._timebase = timebase
            self._status = status
            self._failure_code = failure_code

        def run(self) -> SkillResult:
            now = self._timebase.now()
            return SkillResult(
                skill_name=self.name,
                status=self._status,
                failure_code=self._failure_code,
                started_at=now,
                finished_at=now,
                payload={},
            )
