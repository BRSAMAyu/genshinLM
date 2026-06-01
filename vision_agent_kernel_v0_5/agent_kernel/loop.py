"""AgentLoop — the core autonomous agent cycle.

observe → plan → execute → verify → learn → repeat
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable

from agent_kernel.types import (
    ActionPlan,
    ActionPrimitive,
    AgentGoal,
    Experience,
    GoalResult,
    PlannedStep,
    SemanticObservation,
    StepResult,
)

log = logging.getLogger(__name__)


class AgentLoop:
    """Generic autonomous agent loop.

    Wiring:
      perception (PerceptionProvider) → observation
      planner (Planner) → plan
      executor (ExecutionProvider) → step result
      checker (SuccessChecker) → goal achieved?
      memory (MemoryStore) ← experience

    All dependencies are injected; no game-specific code here.
    """

    def __init__(
        self,
        perception: Any,
        planner: Any,
        executor: Any,
        checker: Any | None = None,
        memory: Any | None = None,
        capture_frame: Callable[[], Any] | None = None,
        max_plan_iterations: int = 10,
        max_step_retries: int = 2,
        confirm_fn: Callable[[ActionPlan], bool] | None = None,
    ) -> None:
        self._perception = perception
        self._planner = planner
        self._executor = executor
        self._checker = checker
        self._memory = memory
        self._capture_frame = capture_frame
        self._max_plan_iterations = max_plan_iterations
        self._max_step_retries = max_step_retries
        self._confirm_fn = confirm_fn

    def run(self, goal: AgentGoal) -> GoalResult:
        """Execute the agent loop until goal is achieved or exhausted."""
        started = time.perf_counter()
        steps_total = 0
        steps_succeeded = 0
        experiences: list[Experience] = []
        plan_iterations = 0

        while plan_iterations < self._max_plan_iterations:
            plan_iterations += 1
            frame = self._capture()
            observation = self._perception.observe(frame)

            # Check if goal already achieved
            if self._check_success(observation, goal):
                return GoalResult(
                    goal_id=goal.goal_id,
                    achieved=True,
                    steps_total=steps_total,
                    steps_succeeded=steps_succeeded,
                    total_duration_sec=time.perf_counter() - started,
                    experiences=tuple(experiences),
                )

            # Plan next actions
            plan = self._planner.plan(observation, goal, self._memory)

            # Dangerous action confirmation
            if plan.requires_confirmation and self._confirm_fn is not None:
                if not self._confirm_fn(plan):
                    log.info("[AgentLoop] plan %s rejected by user", plan.plan_id)
                    break

            # Execute plan steps
            plan_succeeded = True
            for step in plan.steps:
                steps_total += 1
                result = self._execute_step_with_retries(step, observation)
                if result.success:
                    steps_succeeded += 1
                    # Re-observe after successful step
                    frame = self._capture()
                    observation = self._perception.observe(frame)
                else:
                    plan_succeeded = False
                    # Record failure experience
                    exp = Experience(
                        goal_description=goal.description,
                        scene_description=observation.scene_description,
                        action_taken=step.description,
                        outcome="failed",
                        failure_reason=result.error,
                        duration_sec=result.duration_sec,
                        timestamp=time.perf_counter(),
                    )
                    experiences.append(exp)
                    self._record_experience(exp)

                    # Re-plan from current state
                    frame = self._capture()
                    observation = self._perception.observe(frame)
                    plan = self._planner.replan(observation, goal, result, self._memory)
                    break

            # Record successful plan experience
            if plan_succeeded:
                exp = Experience(
                    goal_description=goal.description,
                    scene_description=observation.scene_description,
                    action_taken=f"plan_{plan.plan_id}",
                    outcome="success",
                    duration_sec=time.perf_counter() - started,
                    timestamp=time.perf_counter(),
                )
                experiences.append(exp)
                self._record_experience(exp)

            # Final success check after plan execution
            frame = self._capture()
            observation = self._perception.observe(frame)
            if self._check_success(observation, goal):
                return GoalResult(
                    goal_id=goal.goal_id,
                    achieved=True,
                    steps_total=steps_total,
                    steps_succeeded=steps_succeeded,
                    total_duration_sec=time.perf_counter() - started,
                    experiences=tuple(experiences),
                )

        # Exhausted iterations
        return GoalResult(
            goal_id=goal.goal_id,
            achieved=False,
            steps_total=steps_total,
            steps_succeeded=steps_succeeded,
            total_duration_sec=time.perf_counter() - started,
            experiences=tuple(experiences),
            error="max_plan_iterations_exceeded",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _capture(self) -> Any:
        """Capture a frame from the current screen."""
        if self._capture_frame is not None:
            return self._capture_frame()
        return None

    def _check_success(self, observation: SemanticObservation, goal: AgentGoal) -> bool:
        """Check if the goal has been achieved."""
        if self._checker is None:
            return False
        try:
            achieved, confidence = self._checker.check(observation, goal.success_criteria)
            return achieved and confidence >= 0.7
        except Exception as exc:
            log.warning("[AgentLoop] success check failed: %s", exc)
            return False

    def _execute_step_with_retries(
        self, step: PlannedStep, observation: SemanticObservation,
    ) -> StepResult:
        """Execute a single step with retry logic."""
        for attempt in range(self._max_step_retries + 1):
            # Convert step description to primitive via executor
            primitive = self._step_to_primitive(step, observation)
            result = self._executor.execute(primitive)

            if result.success:
                return result

            if attempt == self._max_step_retries:
                return StepResult(
                    step_id=step.step_id,
                    success=False,
                    error=result.error or f"failed after {attempt + 1} attempts",
                    duration_sec=result.duration_sec,
                )

            # Re-observe before retry
            frame = self._capture()
            if frame is not None:
                observation = self._perception.observe(frame)

        return StepResult(step_id=step.step_id, success=False, error="retries_exhausted")

    def _step_to_primitive(
        self, step: PlannedStep, observation: SemanticObservation,
    ) -> ActionPrimitive:
        """Convert a planned step to an execution primitive.

        Uses the step's target_description for VLM-based locating.
        """
        # Determine primitive type from step description heuristics
        desc_lower = step.description.lower()
        if "click" in desc_lower or "点击" in desc_lower or "装备" in desc_lower:
            ptype = "click"
        elif "press" in desc_lower or "按键" in desc_lower or "按" in desc_lower:
            ptype = "key_press"
        elif "type" in desc_lower or "输入" in desc_lower:
            ptype = "type"
        elif "scroll" in desc_lower or "滚动" in desc_lower:
            ptype = "scroll"
        elif "wait" in desc_lower or "等待" in desc_lower:
            ptype = "wait"
        else:
            ptype = "click"  # default to click for UI interactions

        return ActionPrimitive(
            primitive_type=ptype,
            target=step.target_description,
            reason=step.description,
        )

    def _record_experience(self, experience: Experience) -> None:
        """Store experience in memory if available."""
        if self._memory is not None:
            try:
                self._memory.record(experience)
            except Exception as exc:
                log.warning("[AgentLoop] memory record failed: %s", exc)
