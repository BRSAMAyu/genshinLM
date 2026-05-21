from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from capsules.capsule_protocol import CapsuleContext

from perception.pipeline import FramePostProcessor

_log = logging.getLogger("HSRApp")


class HSRApp:
    app_id = "hsr"

    def __init__(self) -> None:
        self._screen_slot = None
        self._cooldown_slot = None
        self._battle_log_slot = None
        self._sp_slot = None
        self._failure_bridge = None
        self._persona_bridge = None
        self._active = False

    def install(self, context: CapsuleContext) -> None:
        # Register slots
        self._screen_slot = context.state_bus.register_slot("hsr.screen_state")
        self._cooldown_slot = context.state_bus.register_slot("hsr.cooldown_state")
        self._battle_log_slot = context.state_bus.register_slot("hsr.battle_log")
        self._sp_slot = context.state_bus.register_slot("hsr.skill_points")

        # Set defaults
        self._screen_slot.put({"state": "overworld", "confidence": 1.0})
        self._cooldown_slot.put({})
        self._battle_log_slot.put([])
        self._sp_slot.put({"current": 3, "max": 5})

        # Perception bridge
        processor = _HSRPerceptionBridge(
            screen_slot=self._screen_slot,
            cooldown_slot=self._cooldown_slot,
            battle_log_slot=self._battle_log_slot,
            sp_slot=self._sp_slot,
        )
        context.pipeline.add_post_processor(processor)

        # Skills
        from app_service.apps.hsr_skills import (
            HSRCombatSkill,
            HSRNavigationSkill,
            HSRSimpleSkill,
        )
        context.orchestrator.register_skill("hsr_combat", HSRCombatSkill(context.state_bus))
        context.orchestrator.register_skill("hsr_navigation", HSRNavigationSkill(context.state_bus))
        context.orchestrator.register_skill("hsr_claim_rewards", HSRSimpleSkill("hsr_claim_rewards"))
        context.orchestrator.register_skill("hsr_dialog", HSRSimpleSkill("hsr_dialog"))
        context.orchestrator.register_skill(
            "hsr_screen_classification", HSRSimpleSkill("hsr_screen_classification"),
        )

        # Transitions
        context.orchestrator.register_transition("HSR_COMBAT", "HSR_ULTIMATE_PHASE", "ULTIMATE_READY")
        context.orchestrator.register_transition("HSR_ULTIMATE_PHASE", "HSR_COMBAT", "ULTIMATE_USED")

        # Bridges
        from app_service.apps.hsr_failure_bridge import HSRFailureBridge
        self._failure_bridge = HSRFailureBridge(context.state_bus)
        context.state_bus.subscribe("skill_result", self._failure_bridge.on_skill_result)

        from app_service.apps.hsr_persona_bridge import HSRPersonaBridge
        self._persona_bridge = HSRPersonaBridge(context.state_bus)
        context.state_bus.subscribe("interrupt", self._persona_bridge.on_interrupt)

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


class _HSRPerceptionBridge:
    def __init__(self, screen_slot, cooldown_slot, battle_log_slot, sp_slot) -> None:
        self._screen_slot = screen_slot
        self._cooldown_slot = cooldown_slot
        self._battle_log_slot = battle_log_slot
        self._sp_slot = sp_slot
        self._classifier = None
        self._prev_frame = None

    def _ensure_classifier(self) -> None:
        if self._classifier is not None:
            return
        try:
            from perception.hsr_screen_classifier import HSRScreenClassifier
            self._classifier = HSRScreenClassifier()
        except Exception as e:
            _log.warning("Failed to load HSRScreenClassifier: %s", e)

    def process(self, frame, observation, state_bus) -> None:
        self._ensure_classifier()
        from dataclasses import asdict
        if self._classifier is not None:
            try:
                screen_state = self._classifier.classify(frame)
                self._screen_slot.put(asdict(screen_state))
                observation.extensions["hsr_screen"] = screen_state.state
            except Exception as e:
                _log.warning("HSRScreenClassifier.classify failed: %s", e)
                observation.extensions["hsr_screen_error"] = str(e)
        # Update SP state from observation if available
        sp_data = self._sp_slot.get()
        if sp_data:
            observation.extensions["hsr_sp"] = sp_data.get("current", 3)
        self._prev_frame = frame.copy() if frame is not None else None
