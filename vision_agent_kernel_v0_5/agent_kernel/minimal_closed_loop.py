"""Minimal Runnable Closed-Loop simulation for the Sparkle Agent Kernel.

This module implements and wires together the complete architectural pipeline:
Companion Command -> TaskSpec -> Capsule SkillRecipe -> DesktopTree/ScreenClaim ->
ActionContract -> InputLease dry-run -> post-action ObservationClaim ->
StateDeltaClaim verified -> RuntimeOverride patch proposal -> replay/audit.
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Sequence, Dict, Tuple
from uuid import UUID

from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    CapsulePatchProposal,
    DesktopNode,
    DesktopTree,
    GoalResult,
    PhysicalReceipt,
    RuntimeOverride,
    SceneObject,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    StepResult,
    TaskSpec,
    WorldStateGraph,
    ObservationClaim,
)
from agent_kernel.protocols import (
    PerceptionProvider,
    CerebrumPlanner,
    ExecutionProvider,
    SuccessChecker,
    CompanionAgent,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
log = logging.getLogger("SparkleKernel")


# ===========================================================================
# Mock Implementations of Core Protocols
# ===========================================================================

class MockPerceptionProvider:
    """Mock Perception cortex combining template ROI anchoring and OCR clustering."""

    def __init__(self) -> None:
        self.frame_counter = 0

    def observe(self, frame: object, frame_id: int) -> SemanticObservation:
        self.frame_counter = frame_id
        # Build a mock DesktopTree indicating we are in the Katheryne dialogue state
        nodes = (
            DesktopNode("node_title", "dialog_text", "Katheryne: Ad Astra...", (0.2, 0.7, 0.8, 0.8), 0.95),
            DesktopNode("option_daily", "list_item", "Daily Commissions", (0.6, 0.4, 0.9, 0.45), 0.25, source="ocr"),  # Low confidence due to flower petals
            DesktopNode("option_dispatch", "list_item", "Expedition Dispatch", (0.6, 0.48, 0.9, 0.53), 0.9, source="ocr"),
        )
        tree = DesktopTree(
            timestamp=time.time(),
            screen_state="npc_dialog",
            nodes=nodes,
            is_modal_active=True,
            active_roi=(0.5, 0.3, 0.95, 0.8)
        )
        # 3D World state indicating player is standing in front of Katheryne landmark
        world = WorldStateGraph(
            timestamp=time.time(),
            player_position=(22.5, 14.2, 105.1),
            player_yaw=45.0,
            landmarks=(SceneObject("landmark_katheryne", "npc", "Katheryne", confidence=0.99),)
        )
        return SemanticObservation(
            timestamp=time.time(),
            frame_id=frame_id,
            screen_state="npc_dialog",
            desktop_tree=tree,
            world_state=world,
            raw_ocr_text="Daily Commissions | Expedition Dispatch",
            vlm_description="Player is in dialogue with NPC Katheryne. Menu options are present."
        )

    def parse_desktop_tree(
        self, frame: object, active_roi: tuple[float, float, float, float] | None = None
    ) -> DesktopTree:
        return self.observe(frame, self.frame_counter).desktop_tree

    def build_world_state(self, frame: object) -> WorldStateGraph:
        return self.observe(frame, self.frame_counter).world_state


class MockCerebrumPlanner:
    """Mock Cloud-First Cerebrum Planner compiling strategic actions."""

    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> Sequence[SemanticAction]:
        log.info(f"[Cerebrum] Compiling strategic actions for Goal: {goal.description} with Spec: {spec.task_id}")
        # Generates a high-level semantic action to click the daily commission menu item
        action = SemanticAction(
            action_id="action_click_daily_commission",
            kind="ui",
            intent="click_anchor",
            target="Daily Commissions",
            parameters=(("anchor_id", "option_daily"),),
            requires_physical_input=True
        )
        return [action]

    def replan_on_failure(
        self,
        failed_action: SemanticAction,
        observation: SemanticObservation,
        error_msg: str,
    ) -> Sequence[SemanticAction]:
        log.info(f"[Cerebrum] Strategic Replan triggered due to: {error_msg}")
        return []


class MockExecutionProvider:
    """Mock Execution Runtime ensuring safety focus checks and input leases."""

    def __init__(self) -> None:
        self.lease_active = False

    def execute(self, primitive: Any) -> StepResult:
        return StepResult(
            step_id=str(uuid.uuid4()),
            success=True,
            error="",
            duration_sec=0.05,
        )

    def locate_and_click(self, description: str) -> StepResult:
        return StepResult(
            step_id=description,
            success=True,
            error="",
            duration_sec=0.05,
        )

    def press_key(self, key: str, reason: str = "") -> StepResult:
        return StepResult(
            step_id=key,
            success=True,
            error="",
            duration_sec=0.02,
        )

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        action = contract.semantic_action
        log.info(f"[Execution] Securing input lease for Physical input: {action.intent} (Target: '{action.target}')")
        
        # Verify focus is maintained and lease restrictions are respected
        focus_check = True
        lease_id = uuid.uuid4()
        
        # Simulate Bezier path coordinates and DPI conversions
        log.info("[Execution] Translating contract coordinates to mouse click (safe Bezier path trajectory)...")
        time.sleep(0.05)  # Simulate execution latency
        
        return PhysicalReceipt(
            receipt_id=uuid.uuid4(),
            lease_id=lease_id,
            issued_at=time.time(),
            expires_at=time.time() + 0.25,
            action_type="click",
            execution_latency_ms=50.0,
            focus_maintained=focus_check
        )

    def emergency_halt(self) -> None:
        log.warning("[Execution] EMERGENCY HALT CALLED! Releasing all keyboard/mouse inputs.")
        self.lease_active = False


class MockSuccessChecker:
    """Mock Adjudication verifying post-action claims."""

    def adjudicate_delta(
        self, pre_obs: SemanticObservation, post_obs: SemanticObservation, criteria: str
    ) -> StateDeltaClaim:
        log.info(f"[Adjudicator] Verifying post-action Observation claims matching criteria: '{criteria}'")
        
        # Generate positive claim backing successful state transition
        claim = StateDeltaClaim(
            claim_id=f"claim_{uuid.uuid4().hex[:8]}",
            pre_frame_id=pre_obs.frame_id,
            post_frame_id=post_obs.frame_id,
            delta_description="daily_commission_menu_clicked_successfully",
            verified=True,
            confidence=0.98,
            attributions=("daily_commission_click_verify",)
        )
        return claim


class MockCompanionAgent:
    """Mock Companion dialog agent managing overrides and Capsule patching diffs."""

    def parse_override(self, user_command: str, tree: DesktopTree) -> RuntimeOverride:
        log.info(f"[Companion] Parsing natural language intervention: '{user_command}'")
        # Injects a low-confidence threshold override to the StateBus
        override = RuntimeOverride(
            override_id=f"override_{uuid.uuid4().hex[:8]}",
            target_node_id="option_daily",
            policy_overrides=(("override_threshold", "0.2"), ("force_execute", "click")),
            timestamp=time.time(),
            reason="OCR petal obstruction override"
        )
        return override

    def propose_capsule_patch(
        self, capsule_id: str, successful_override: RuntimeOverride
    ) -> CapsulePatchProposal:
        log.info(f"[Companion] Proposing permanent Capsule patch for Capsule: {capsule_id}")
        diff = (
            "--- capsules/genshin/resources/ui_anchors.yaml\n"
            "+++ capsules/genshin/resources/ui_anchors.yaml (patched)\n"
            "@@ -45,3 +45,3 @@\n"
            "   daily_commission_anchor:\n"
            "-    min_confidence: 0.60\n"
            "+    min_confidence: 0.20\n"
        )
        return CapsulePatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:8]}",
            capsule_id=capsule_id,
            target_yaml_file="capsules/genshin/resources/ui_anchors.yaml",
            yaml_diff=diff,
            proposed_overrides=successful_override.policy_overrides,
            schema_valid=True,
            user_confirmed=False
        )


# ===========================================================================
# Unified Closed-Loop Core Runner
# ===========================================================================

class SparkleClosedLoopRunner:
    """The central runtime executing the secure, closed-loop contract pipeline."""

    def __init__(self) -> None:
        self.perception = MockPerceptionProvider()
        self.planner = MockCerebrumPlanner()
        self.executor = MockExecutionProvider()
        self.checker = MockSuccessChecker()
        self.companion = MockCompanionAgent()

    def run_pipeline(self, user_natural_language: str) -> GoalResult:
        started_time = time.perf_counter()
        log.info("=== STEP 1: Capturing and Anchoring Screen (Cerebellum) ===")
        pre_obs = self.perception.observe(None, frame_id=1001)
        log.info(f"[Cerebellum] Built DesktopTree. Active Screen State: '{pre_obs.screen_state}'")
        
        # Companion intercepting low-confidence OCR block
        log.info("=== STEP 2: Companion Intervention & Runtime Override ===")
        tree = pre_obs.desktop_tree
        assert tree is not None
        
        override = self.companion.parse_override(user_natural_language, tree)
        log.info(f"[StateBus] Warm status overrides injected: {dict(override.policy_overrides)}")

        # Configure safe Task Specification
        spec = TaskSpec(
            task_id="task_verify_claim",
            objective="claim_daily_rewards",
            dialog_policy="progress_main_story",
            resource_policy="strict_safety",
            uncertainty_policy="ask_user_immediately",
            execution_mode="authorized_safe_window"
        )
        goal = AgentGoal(
            goal_id="goal_daily",
            description="Talk to Katheryne and claim commissions",
            success_criteria="daily_commission_reward_claimed"
        )

        log.info("=== STEP 3: Cloud-First Cerebrum Planning ===")
        actions = self.planner.compile_task(goal, spec)
        assert len(actions) > 0
        action = actions[0]

        log.info("=== STEP 4: Safety Action Contract Generation ===")
        # Translates SemanticAction -> ActionContract with safety checks
        contract = ActionContract(
            contract_id=f"contract_{uuid.uuid4().hex[:8]}",
            semantic_action=action,
            preconditions=("dialog_present",),
            safety_policy=(("require_focus", "True"), ("input_lease_required", "True"), ("max_lease_ms", "250")),
            verifier_contract=(("verifier_id", "daily_commission_click_verify"), ("success_criteria", "screen_state_changed")),
            timeout_ms=1000,
            risk_level="low"
        )
        log.info(f"[Contract] ActionContract built successfully. Safety constraints: {dict(contract.safety_policy)}")

        # Safety Checkpoint: Validate Contract
        log.info("[Safety] Validating ActionContract constraints...")
        # (Contracts must satisfy require_focus and lease configurations)
        assert dict(contract.safety_policy).get("require_focus") == "True"
        assert dict(contract.safety_policy).get("input_lease_required") == "True"
        log.info("[Safety] ActionContract validated successfully! Proceeding to Motor execution.")

        log.info("=== STEP 5: Motor Execution & Physical Receipt ===")
        receipt = self.executor.execute_contract(contract)
        log.info(f"[Receipt] Unforgeable Physical Receipt acquired: {receipt.receipt_id} (Focus maintained: {receipt.focus_maintained})")
        assert receipt.focus_maintained is True

        log.info("=== STEP 6: Post-action Observation & Adjudication ===")
        # Simulate new observation after click (options disappeared, reward dialog shown)
        post_nodes = (
            DesktopNode("node_title", "dialog_text", "Katheryne: Thank you, adventure...", (0.2, 0.7, 0.8, 0.8), 0.95),
        )
        post_tree = DesktopTree(
            timestamp=time.time(),
            screen_state="npc_dialog_completed",
            nodes=post_nodes,
            is_modal_active=True
        )
        post_obs = SemanticObservation(
            timestamp=time.time(),
            frame_id=1002,
            screen_state="npc_dialog_completed",
            desktop_tree=post_tree,
            raw_ocr_text="Thank you",
            vlm_description="Katheryne dialogue completed. Rewards toast is displayed."
        )
        
        # State Delta verification and attribution
        delta_claim = self.checker.adjudicate_delta(pre_obs, post_obs, goal.success_criteria)
        log.info(f"[ClaimGraph] StateDeltaClaim verified: {delta_claim.verified} (Attributed evidence: {delta_claim.attributions})")
        assert delta_claim.verified is True

        log.info("=== STEP 7: Interactive Session Wrap-up & YAML Patching ===")
        proposal = self.companion.propose_capsule_patch("genshin", override)
        log.info(f"[YAML Diff Manager] Displaying proposed YAML patch for Review:\n{proposal.yaml_diff}")
        
        # Simulating user manual diff confirmation
        log.info("[User Confirmation] User clicked 'Approve permanent save' in Companion Widget.")
        proposal_confirmed = CapsulePatchProposal(
            patch_id=proposal.patch_id,
            capsule_id=proposal.capsule_id,
            target_yaml_file=proposal.target_yaml_file,
            yaml_diff=proposal.yaml_diff,
            proposed_overrides=proposal.proposed_overrides,
            schema_valid=True,
            user_confirmed=True
        )
        log.info(f"[YAML Patch Manager] Successfully wrote patch back to '{proposal_confirmed.target_yaml_file}'!")

        return GoalResult(
            goal_id=goal.goal_id,
            achieved=True,
            steps_total=1,
            steps_succeeded=1,
            total_duration_sec=time.perf_counter() - started_time,
            verified_claims=(delta_claim,)
        )


if __name__ == "__main__":
    runner = SparkleClosedLoopRunner()
    result = runner.run_pipeline("The option 'Daily Commissions' has a low confidence because of flower petals, lower threshold to 0.2 and click it")
    print(f"\nPipeline execution result: {result}")
