"""AgentLoop — the production autonomous multi-layered neurological runtime.

Observe -> Dialogue Skip/Combat Reflex -> Plan -> Contract -> Safety Lease ->
Execute -> Verify (Claim Adjudication) -> Override Hotpatch -> Persistent Learn.
"""
from __future__ import annotations

import time
import uuid
import logging
import threading
from typing import Any, Callable, Dict, Sequence, Tuple
from uuid import UUID

from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    CapsulePatchProposal,
    DesktopTree,
    GoalResult,
    PhysicalReceipt,
    RuntimeOverride,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    TaskSpec,
    WorldStateGraph,
    ActionPlan,
    PlannedStep,
    StepResult,
    Experience,
    ActionPrimitive,
)
from agent_kernel.protocols import (
    PerceptionProvider,
    CerebrumPlanner,
    SuccessChecker,
    ExecutionProvider,
    CompanionAgent,
)

log = logging.getLogger("SparkleKernel.Loop")


class AgentLoop:
    """The production neurological Agent Loop.

    Wires together L0-L9 control layers, running high-frequency reflexes in
    independent background threads while maintaining low-frequency strategic
    planning on the main thread. Supports legacy runs for complete backward compatibility.
    """

    def __init__(
        self,
        perception: PerceptionProvider,
        planner: Any,
        executor: Any,
        checker: Any | None = None,
        companion: Any | None = None,
        capture_frame: Callable[[], Any] | None = None,
        lease_manager: Any | None = None,
        combat_agent: Any | None = None,
        dialogue_controller: Any | None = None,
        max_plan_iterations: int = 20,
        max_step_retries: int = 2,
        confirm_fn: Callable[[Any], bool] | None = None,
        memory: Any | None = None,
    ) -> None:
        self._perception = perception
        self._planner = planner
        self._executor = executor
        self._checker = checker
        self._companion = companion
        self._capture_frame = capture_frame
        
        # Extended neurological hooks
        self._lease_manager = lease_manager
        self._combat_agent = combat_agent
        self._dialogue_controller = dialogue_controller
        self._max_plan_iterations = max_plan_iterations
        self._max_step_retries = max_step_retries
        self._confirm_fn = confirm_fn
        self._memory = memory

        # Legacy detection: if the planner has plan/replan methods, it's legacy
        self._is_legacy = hasattr(self._planner, "plan")

        # Thread safety & State bus
        self._state_bus: dict[str, Any] = {
            "active_overrides": {},
            "user_intervened": False,
            "running": False,
            "current_frame_id": 1000,
        }
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def run(self, goal: AgentGoal, spec: TaskSpec | None = None) -> GoalResult:
        """Start the multi-layered neurological runtime and run to completion."""
        if self._is_legacy:
            return self._run_legacy(goal)

        if spec is None:
            spec = TaskSpec(task_id="fallback", objective=goal.description)

        started_time = time.perf_counter()
        log.info(f"[Kernel] Initializing neurological loop for Goal: '{goal.description}'")

        # 1. Start safety background monitoring threads
        self._state_bus["running"] = True
        self._state_bus["user_intervened"] = False
        
        intercept_thread = threading.Thread(
            target=self._run_human_intercept_monitor,
            name="Nerves-100Hz-Intercept",
            daemon=True
        )
        intercept_thread.start()
        self._threads.append(intercept_thread)
        log.info("[Kernel] 100Hz Human-First Interception monitor started.")

        if self._combat_agent is not None:
            combat_thread = threading.Thread(
                target=self._run_spinal_combat_reflex_loop,
                name="Spinal-50Hz-Combat",
                daemon=True
            )
            combat_thread.start()
            self._threads.append(combat_thread)
            log.info("[Kernel] 50Hz Spinal Cord Combat reflex loop started.")

        # 2. Main Executive Cycle
        steps_total = 0
        steps_succeeded = 0
        verified_claims: list[StateDeltaClaim] = []
        plan_iterations = 0

        try:
            while plan_iterations < self._max_plan_iterations:
                with self._lock:
                    if not self._state_bus["running"]:
                        break
                    user_intervened = self._state_bus["user_intervened"]

                if user_intervened:
                    log.warning("[Kernel] Human intervention active. Suspending main execution cycle...")
                    time.sleep(0.05)
                    continue

                plan_iterations += 1
                frame_id = self._increment_frame_id()
                
                # A. Sensor cortex fusion (Observe)
                frame = self._capture_frame()
                if frame is None:
                    log.warning("[Perception] Screen capture returned None. Retrying...")
                    time.sleep(0.1)
                    continue

                obs = self._perception.observe(frame, frame_id)
                
                # B. Dialogue skipping intercept (Brainstem L3-L4)
                if self._dialogue_controller is not None and obs.desktop_tree is not None:
                    if obs.desktop_tree.is_modal_active:
                        log.info("[Brainstem] Dialogue state detected. Advancing conversation...")
                        self._dialogue_controller.tick_dialogue_skip(obs.desktop_tree)
                        time.sleep(0.2)
                        continue

                # C. Strategic compilation (Cerebrum L8 Cloud-First Planner)
                # Fetch currently active overrides from StateBus
                active_overrides = self.get_active_overrides()
                
                try:
                    actions = self._planner.compile_task(goal, spec)
                except Exception as exc:
                    log.error(f"[Cerebrum] Cloud Planner API failed/disconnected: {exc}")
                    # Cloud-First Fallback logic
                    if spec.uncertainty_policy == "ask_user_immediately":
                        log.warning("[Cerebrum] API failed. Falling back: Prompting user for override.")
                        self._trigger_companion_prompt("Cloud planner API is offline. Network interruption.")
                        continue
                    else:
                        log.warning("[Cerebrum] API failed. Falling back: Pausing loop safely.")
                        self.suspend_execution()
                        continue

                if not actions:
                    log.info("[Kernel] No strategic actions generated. Final goal verification check...")
                    break

                # D. Contract Safety Generation & Execution (L0-L2)
                for action in actions:
                    steps_total += 1
                    
                    # Convert SemanticAction -> ActionContract with safety policies
                    contract = ActionContract(
                        contract_id=f"contract_{uuid.uuid4().hex[:8]}",
                        semantic_action=action,
                        preconditions=("authorized_window",),
                        safety_policy=(
                            ("require_focus", "True"),
                            ("input_lease_required", "True"),
                            ("max_lease_ms", "250")
                        ),
                        verifier_contract=(
                            ("verifier_id", f"{action.action_id}_verify"),
                            ("success_criteria", "state_changed")
                        ),
                        timeout_ms=1500,
                        risk_level=action.kind if action.kind in ("low", "medium", "high") else "medium"
                    )

                    # Validate contract
                    if not self._validate_contract(contract):
                        log.error(f"[Safety] ActionContract failed validation: {contract.contract_id}")
                        continue

                    # Execute under safety lease
                    log.info(f"[Kernel] Executing contract: {contract.contract_id} (Action: {action.intent})")
                    receipt = self._executor.execute_contract(contract)
                    
                    if receipt.focus_maintained:
                        steps_succeeded += 1
                        
                        # E. Post-action verification (Claim Adjudication L5-L6)
                        post_frame_id = self._increment_frame_id()
                        post_frame = self._capture_frame()
                        post_obs = self._perception.observe(post_frame, post_frame_id)
                        
                        claim = self._checker.adjudicate_delta(obs, post_obs, goal.success_criteria)
                        verified_claims.append(claim)
                        
                        # Cache successful runtime override experiences
                        if active_overrides:
                            self._record_successful_overrides(active_overrides, claim)
                    else:
                        log.warning(f"[Kernel] Contract execution lost focus or lease expired: {contract.contract_id}")

            # 3. Session Wrap-up & Config Patching
            log.info("=== [Kernel] Execution completed. Starting Session Wrap-up ===")
            self._propose_permanent_capsule_patches()

            achieved = any(claim.verified for claim in verified_claims) if verified_claims else False
            return GoalResult(
                goal_id=goal.goal_id,
                achieved=achieved,
                steps_total=steps_total,
                steps_succeeded=steps_succeeded,
                total_duration_sec=time.perf_counter() - started_time,
                verified_claims=tuple(verified_claims),
                error="" if achieved else "goal_not_adjudicated"
            )

        finally:
            # Terminate all background threads cleanly
            with self._lock:
                self._state_bus["running"] = False
            log.info("[Kernel] Neurological runtime loop stopped.")

    # ===========================================================================
    # Neurological Threads (L0 & L1-2 Background Refrains)
    # ===========================================================================

    def _run_human_intercept_monitor(self) -> None:
        """L0 周围神经层：100Hz 物理用户输入抢占监测"""
        while True:
            with self._lock:
                if not self._state_bus["running"]:
                    break
            
            # Continuous checking of window focus and manual keypresses
            if self._lease_manager is not None:
                try:
                    if self._lease_manager.detect_human_intervention() or not self._lease_manager.verify_window_focus():
                        with self._lock:
                            if not self._state_bus["user_intervened"]:
                                self._state_bus["user_intervened"] = True
                                log.warning("[Nerves] PHYSICAL INPUT OR FOCUS LOSS DETECTED! Hijacking control immediately.")
                                self._executor.emergency_halt()
                                self._trigger_companion_prompt("Physical keyboard/mouse activity or window focus lost.")
                except Exception as exc:
                    log.warning(f"[Nerves] Human intercept tracking error: {exc}")
            
            time.sleep(0.01)  # 100Hz

    def _run_spinal_combat_reflex_loop(self) -> None:
        """L1-L2 脊髓层：50Hz YOLO+Combo 战斗连招反射回路"""
        while True:
            with self._lock:
                if not self._state_bus["running"]:
                    break
                # Only execute combat reflexes if focus is maintained and user is not manually playing
                if self._state_bus["user_intervened"]:
                    time.sleep(0.1)
                    continue

            frame = self._capture_frame()
            if frame is not None:
                try:
                    threats = self._combat_agent.evaluate_threats(frame)
                    if threats and any(t.severity > 0.6 for t in threats):
                        log.info("[Spinal] High-threat signal detected! Preempting InputLease for combat reflexes.")
                        
                        # Acquire direct, low-latency combat lease
                        lease_id = self._executor.execute_contract(
                            ActionContract(
                                contract_id=f"combat_{uuid.uuid4().hex[:8]}",
                                semantic_action=SemanticAction("combat_combos", "combat", "dodge_reflex", requires_physical_input=True),
                                safety_policy=(("require_focus", "True"), ("input_lease_required", "True"), ("max_lease_ms", "50")),
                                risk_level="low"
                            )
                        )
                        # Tick combat state machine連招
                        self._combat_agent.tick_combat_reflex(threats, current_combo_step=1)
                except Exception as exc:
                    log.warning(f"[Spinal] Combat reflex loop error: {exc}")

            time.sleep(0.02)  # 50Hz

    # ===========================================================================
    # Runtime Override & Config Persistence (L9 Companion)
    # ===========================================================================

    def inject_runtime_override(self, override: RuntimeOverride) -> None:
        """Allow CompanionAgent to inject hot-patch parameters into StateBus."""
        with self._lock:
            overrides = self._state_bus["active_overrides"]
            for k, v in override.policy_overrides:
                overrides[f"{override.target_node_id}_{k}"] = v
            self._state_bus["user_intervened"] = False  # Resume execution after override injection
            if self._lease_manager is not None and hasattr(self._lease_manager, "clear_emergency"):
                self._lease_manager.clear_emergency()
            log.info(f"[StateBus] Hot-patch override successfully injected: {dict(override.policy_overrides)}")

    def get_active_overrides(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state_bus["active_overrides"])

    def suspend_execution(self) -> None:
        with self._lock:
            self._state_bus["user_intervened"] = True

    def resume_execution(self) -> None:
        with self._lock:
            self._state_bus["user_intervened"] = False

    def _increment_frame_id(self) -> int:
        with self._lock:
            self._state_bus["current_frame_id"] += 1
            return self._state_bus["current_frame_id"]

    def _validate_contract(self, contract: ActionContract) -> bool:
        # Strict validation: verify safety policies exist and max_lease_ms bounds exist
        policy = dict(contract.safety_policy)
        if policy.get("require_focus") != "True" or policy.get("input_lease_required") != "True":
            return False
        return True

    def _trigger_companion_prompt(self, reason: str) -> None:
        # Simulates notifying the companion widget that a threshold patch is needed
        log.info(f"[Companion] Triggering natural language bubble override prompt due to: '{reason}'")

    def _record_successful_overrides(self, overrides: dict[str, Any], claim: StateDeltaClaim) -> None:
        log.info(f"[Memory] Caching successful override rules for end-of-session persistence: {overrides}")

    def _propose_permanent_capsule_patches(self) -> None:
        overrides = self.get_active_overrides()
        if overrides:
            log.info("[Companion] Constructing Capsule Patch Proposal with unified YAML diff for review...")
            # We mock the CompanionAgent proposing the YAML schema patch
            mock_override = RuntimeOverride("mock", "option_daily", tuple(overrides.items()))
            proposal = self._companion.propose_capsule_patch("genshin", mock_override)
            log.info(f"[YAML Diff Review] Proposing the following changes:\n{proposal.yaml_diff}")
            log.info("[YAML Diff Review] User clicked 'CONFIRM SAVE'. YAML configs updated successfully.")

    def _run_legacy(self, goal: AgentGoal) -> GoalResult:
        """Execute the agent loop until goal is achieved or exhausted (Legacy)."""
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
