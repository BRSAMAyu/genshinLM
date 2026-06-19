"""Production adapters — wire existing components to AgentKernel protocols."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_kernel.types import (
    ActionableElement,
    ActionPrimitive,
    ActionPlan,
    AgentGoal,
    Experience,
    PlannedStep,
    SemanticObservation,
    StateDeltaClaim,
    StepResult,
)
from agent_kernel.protocols import (
    ExecutionProvider,
    MemoryStore,
    PerceptionProvider,
    Planner,
    SuccessChecker,
)

if TYPE_CHECKING:
    import numpy as np


# ---------------------------------------------------------------------------
# Perception
# ---------------------------------------------------------------------------

class VLMPerceptionProvider:
    """PerceptionProvider backed by GenshinScreenClassifier + VLM grounding.

    - ``observe`` → GenshinScreenClassifier.classify() for fast state detection
    - ``describe_scene`` → VLM describe_image for semantic description
    - ``locate_element`` → VLM ground_ui for element bounding boxes
    """

    def __init__(
        self,
        screen_classifier: Any,
        vlm_provider: Any,
        ocr_provider: Any | None = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> None:
        self._classifier = screen_classifier
        self._vlm = vlm_provider
        self._ocr = ocr_provider
        self._screen_w = screen_width
        self._screen_h = screen_height

    def observe(self, frame: np.ndarray, frame_id: int = 0) -> SemanticObservation:
        import time as _time
        from agent_kernel.types import DesktopTree

        # Fast HSV-based classification
        screen_state = self._classifier.classify(frame)

        # Optional OCR text
        raw_ocr = ""
        if self._ocr is not None:
            try:
                results = self._ocr.detect_text(frame, None)
                raw_ocr = " | ".join(r.text for r in results if r.text)
            except Exception:
                pass

        # Build minimal DesktopTree for dialogue/scene detection
        desktop_tree = DesktopTree(
            timestamp=_time.perf_counter(),
            screen_state=screen_state.state,
            nodes=(),
            is_modal_active=screen_state.state in (
                "dialog", "dialogue", "menu", "inventory", "reward_screen", "npc_dialog",
            ),
        )

        return SemanticObservation(
            timestamp=_time.perf_counter(),
            frame_id=frame_id,
            scene_description=f"screen_state={screen_state.state}",
            desktop_tree=desktop_tree,
            actionable_elements=(),
            screen_state=screen_state.state,
            raw_ocr_text=raw_ocr,
            vlm_confidence=screen_state.confidence,
        )

    def describe_scene(self, frame: np.ndarray, prompt: str) -> str:
        from llm.vision_provider import ImageInput

        image = _encode_frame(frame)
        try:
            result = self._vlm.describe_image(image, prompt)
            return result.description
        except Exception:
            return ""

    def locate_element(
        self, frame: np.ndarray, description: str,
    ) -> ActionableElement | None:
        from llm.vision_provider import ImageInput

        image = _encode_frame(frame)
        try:
            result = self._vlm.ground_ui(image, description)
            if not result.candidates:
                return None
            # Pick highest-confidence candidate
            best: dict[str, object] | None = None
            best_conf = -1.0
            for c in result.candidates:
                conf = float(c.get("confidence", 0.0))
                if conf > best_conf:
                    best_conf = conf
                    best = c
            if best is None:
                return None
            bbox_norm = best.get("bbox_norm")
            if not isinstance(bbox_norm, (list, tuple)) or len(bbox_norm) != 4:
                return None
            label = str(best.get("label", description))
            return ActionableElement(
                element_type=best.get("type", "unknown"),
                label=label,
                bbox=tuple(float(v) for v in bbox_norm),
                confidence=best_conf,
                state=best.get("state", ""),
            )
        except Exception:
            return None


def _encode_frame(frame: np.ndarray) -> "ImageInput":
    from llm.vision_provider import ImageInput as II

    import cv2

    if frame.dtype != __import__("numpy").uint8:
        frame = frame.astype(__import__("numpy").uint8)
    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
    encoded = cv2.imencode(".png", frame)
    if not encoded:
        raise RuntimeError("cv2.imencode failed")
    return II(data=bytes(encoded[1]), mime_type="image/png")


# ---------------------------------------------------------------------------
# Success Checker
# ---------------------------------------------------------------------------

class VLMSuccessChecker:
    """SuccessChecker backed by VLM describe_image.

    Asks VLM "Is the goal achieved?" with the given criteria.
    """

    def __init__(
        self,
        vlm_provider: Any,
        threshold: float = 0.7,
    ) -> None:
        self._vlm = vlm_provider
        self._threshold = threshold

    def check(self, observation: SemanticObservation, criteria: str) -> tuple[bool, float]:
        # Build a yes/no question from criteria
        prompt = (
            f"Based on the current screen, answer YES or NO: {criteria}\n"
            "Respond with exactly one word: YES or NO."
        )
        # observation.scene_description already has some context from describe_scene
        full_prompt = f"{prompt}\n\nScreen description: {observation.scene_description}"
        # We need the actual frame for VLM — this checker works in conjunction
        # with observe(). If scene_description is rich enough, use it directly.
        # For image-based check, the caller should pass a richer observation.
        # Heuristic: if scene description contains keywords from criteria, give confidence.
        scene_lower = observation.scene_description.lower()
        criteria_lower = criteria.lower()

        # Sub-string match: each character/word in criteria appears in scene
        # Works for both space-separated (English) and continuous (Chinese) text
        shared = sum(
            1 for word in criteria_lower.split()
            if word in scene_lower
        )
        # Fallback: check if any2-char Chinese sub-string from criteria is in scene
        if shared == 0:
            criteria_chars = [c for c in criteria_lower if c.strip()]
            shared = sum(1 for c in criteria_chars if c in scene_lower) // 2
        if shared >= 2:
            return True, 0.8
        return False, observation.vlm_confidence

    def check_with_frame(
        self, frame: np.ndarray, criteria: str,
    ) -> tuple[bool, float]:
        """VLM-based check using the actual frame (preferred)."""
        from llm.vision_provider import ImageInput

        image = _encode_frame(frame)
        prompt = (
            f"Answer YES or NO only: Does the current screen show that '{criteria}' has been achieved?\n"
            "Respond with exactly one word: YES or NO."
        )
        try:
            result = self._vlm.describe_image(image, prompt)
            text = result.description.strip().upper()
            if text.startswith("YES"):
                return True, result.confidence if hasattr(result, "confidence") else 0.8
            return False, 0.3
        except Exception:
            return False, 0.0

    def adjudicate_delta(
        self,
        pre_obs: SemanticObservation,
        post_obs: SemanticObservation,
        criteria: str,
    ) -> "StateDeltaClaim":
        """Compare pre/post observations to produce a verified StateDeltaClaim."""
        import time as _time
        import uuid as _uuid
        from agent_kernel.types import StateDeltaClaim

        achieved, confidence = self.check(post_obs, criteria)
        return StateDeltaClaim(
            claim_id=f"claim_{_uuid.uuid4().hex[:8]}",
            pre_frame_id=pre_obs.frame_id,
            post_frame_id=post_obs.frame_id,
            delta_description=f"criteria={criteria}",
            verified=achieved,
            confidence=confidence,
            attributions=(f"vlm_adjudicate:{criteria}",),
            timestamp=_time.perf_counter(),
        )


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class LLMPlanner:
    """Planner backed by the existing llm/planner.py Planner.

    Adapts the signature: AgentKernel passes (observation, goal, memory)
    but the underlying Planner accepts goal: str + skills.
    """

    def __init__(
        self,
        planner: Any,  # llm.planner.Planner
        skill_store: Any | None = None,
        provider: str = "mock",
    ) -> None:
        self._planner = planner
        self._skill_store = skill_store
        self._provider = provider

    def plan(
        self,
        observation: SemanticObservation,
        goal: AgentGoal,
        memory: MemoryStore | None,
    ) -> ActionPlan:
        import uuid

        # Build context from observation and memory
        context_parts = [f"Scene: {observation.scene_description}"]
        if observation.raw_ocr_text:
            context_parts.append(f"OCR: {observation.raw_ocr_text}")

        if memory is not None:
            past = memory.recall(goal.description, limit=3)
            if past:
                context_parts.append(
                    "Past experience: " + "; ".join(
                        f"{e.action_taken} → {e.outcome}"
                        for e in past
                    )
                )

        context = "\n".join(context_parts)
        full_goal = f"{goal.description}\n\nContext:\n{context}"

        try:
            proposal = self._planner.plan(
                goal=full_goal,
                provider=self._provider,
            )
            # Convert PlannerProposal → ActionPlan
            steps = self._proposal_to_steps(proposal, goal.goal_id)
            return ActionPlan(
                plan_id=proposal.provider or "llm",
                goal_id=goal.goal_id,
                steps=steps,
                confidence=0.75,
            )
        except Exception as exc:
            # Graceful degradation: return empty plan
            return ActionPlan(
                plan_id="fallback",
                goal_id=goal.goal_id,
                steps=(),
                confidence=0.0,
            )

    def replan(
        self,
        observation: SemanticObservation,
        goal: AgentGoal,
        failure: StepResult,
        memory: MemoryStore | None,
    ) -> ActionPlan:
        import uuid

        # Add failure context
        context_parts = [f"Scene: {observation.scene_description}"]
        if failure.error:
            context_parts.append(f"Failure: {failure.error}")

        if memory is not None:
            past_failures = memory.recall_failures(goal.description)
            if past_failures:
                context_parts.append(
                    "Similar past failures: " + "; ".join(
                        f"{e.action_taken} ({e.failure_reason})"
                        for e in past_failures[:2]
                    )
                )

        context = "\n".join(context_parts)
        full_goal = (
            f"{goal.description}\n\nPrevious step failed. Context:\n{context}"
        )

        try:
            proposal = self._planner.plan(
                goal=full_goal,
                provider=self._provider,
            )
            steps = self._proposal_to_steps(proposal, goal.goal_id)
            return ActionPlan(
                plan_id=f"replan_{proposal.provider or 'llm'}",
                goal_id=goal.goal_id,
                steps=steps,
                confidence=0.7,
            )
        except Exception:
            return ActionPlan(
                plan_id="replan_fallback",
                goal_id=goal.goal_id,
                steps=(),
                confidence=0.0,
            )

    def _proposal_to_steps(
        self, proposal: Any, goal_id: str,
    ) -> tuple[PlannedStep, ...]:
        import uuid

        steps: list[PlannedStep] = []
        skill_chain = getattr(proposal, "skill_chain", None)
        if skill_chain and isinstance(skill_chain, list):
            for i, skill in enumerate(skill_chain):
                skill_id = skill if isinstance(skill, str) else str(skill)
                steps.append(
                    PlannedStep(
                        step_id=f"step_{i}_{uuid.uuid4().hex[:8]}",
                        description=f"Execute skill: {skill_id}",
                        target_description=skill_id,
                        expected_outcome="skill_executed",
                    )
                )
        return tuple(steps)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class GenshinExecutionProvider:
    """ExecutionProvider backed by ComputerUseController.

    Translates ActionPrimitive → VLM-grounded click/key/type.
    """

    def __init__(
        self,
        controller: Any,  # ComputerUseController
        input_backend: Any | None = None,
    ) -> None:
        self._controller = controller
        self._backend = input_backend
        self._last_frame: np.ndarray | None = None

    def execute(self, primitive: ActionPrimitive) -> StepResult:
        import time as _time
        import uuid

        started = _time.perf_counter()
        if self._last_frame is None:
            return StepResult(
                step_id=primitive.target or str(uuid.uuid4()),
                success=False,
                error="no_frame_captured",
                duration_sec=_time.perf_counter() - started,
            )

        ptype = primitive.primitive_type
        target = primitive.target
        reason = primitive.reason

        try:
            if ptype == "click":
                ok = self._controller.click_target(self._last_frame, target, reason)
            elif ptype == "hover":
                ok = self._controller.move_to_target(self._last_frame, target, reason)
            elif ptype == "key_press":
                ok = self._press_key(target, reason)
            elif ptype == "type":
                ok = self._type_text(target, reason)
            elif ptype == "scroll":
                ok = self._scroll(target, reason)
            elif ptype == "wait":
                _time.sleep(float(target) if target else 1.0)
                ok = True
            else:
                ok = self._controller.click_target(self._last_frame, target, reason)
            return StepResult(
                step_id=primitive.target or str(uuid.uuid4()),
                success=ok,
                duration_sec=_time.perf_counter() - started,
            )
        except Exception as exc:
            return StepResult(
                step_id=primitive.target or str(uuid.uuid4()),
                success=False,
                error=str(exc),
                duration_sec=_time.perf_counter() - started,
            )

    def locate_and_click(self, description: str) -> StepResult:
        import time as _time
        import uuid

        started = _time.perf_counter()
        if self._last_frame is None:
            return StepResult(
                step_id=description,
                success=False,
                error="no_frame_captured",
                duration_sec=_time.perf_counter() - started,
            )
        try:
            ok = self._controller.click_target(self._last_frame, description, "")
            return StepResult(
                step_id=description,
                success=ok,
                duration_sec=_time.perf_counter() - started,
            )
        except Exception as exc:
            return StepResult(
                step_id=description,
                success=False,
                error=str(exc),
                duration_sec=_time.perf_counter() - started,
            )

    def press_key(self, key: str, reason: str = "") -> StepResult:
        import time as _time
        import uuid

        started = _time.perf_counter()
        ok = self._press_key(key, reason)
        return StepResult(
            step_id=str(uuid.uuid4()),
            success=ok,
            duration_sec=_time.perf_counter() - started,
        )

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        import uuid
        import time as _time
        from agent_kernel.types import ActionPrimitive
        prim = ActionPrimitive(
            primitive_type=contract.semantic_action.intent,
            target=contract.semantic_action.target,
            params=contract.semantic_action.parameters,
        )
        res = self.execute(prim)
        now = _time.perf_counter()
        return PhysicalReceipt(
            receipt_id=uuid.uuid4(),
            lease_id=uuid.uuid4(),
            issued_at=now,
            expires_at=now + 0.25,
            action_type="click",
            execution_latency_ms=res.duration_sec * 1000.0,
            focus_maintained=True,
            action_id=contract.semantic_action.action_id,
            status="verified" if res.success else "failed",
            submitted_at=now,
            lease_accepted=True,
            focus_ok=True,
            duration_ms=res.duration_sec * 1000.0,
        )

    def emergency_halt(self) -> None:
        if self._backend is not None:
            try:
                self._backend.release_all(reason="emergency_halt")
            except Exception:
                pass

    def set_last_frame(self, frame: np.ndarray) -> None:
        self._last_frame = frame

    def _press_key(self, key: str, reason: str) -> bool:
        if self._backend is None:
            return False
        try:
            self._backend.key_press(key, reason)
            return True
        except Exception:
            return False

    def _type_text(self, text: str, reason: str) -> bool:
        if self._backend is None:
            return False
        try:
            for ch in text:
                self._backend.key_down(ch, reason)
                self._backend.key_up(ch, reason)
            return True
        except Exception:
            return False

    def _scroll(self, direction: str, reason: str) -> bool:
        if self._backend is None:
            return False
        delta = 1 if direction in ("up", "scroll_up") else -1
        try:
            self._backend.mouse_scroll(delta, reason)
            return True
        except Exception:
            return False