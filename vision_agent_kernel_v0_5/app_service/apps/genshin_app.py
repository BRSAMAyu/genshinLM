from __future__ import annotations

import logging

from app_service.app_registry import AppContext
from perception.pipeline import FramePostProcessor

_log = logging.getLogger("GenshinApp")


class GenshinApp:
    app_id = "genshin"

    def __init__(self) -> None:
        self._screen_slot = None
        self._danger_slot = None
        self._cooldown_slot = None
        self._failure_bridge = None
        self._persona_bridge = None
        self._active = False

    def install(self, context: AppContext) -> None:
        self._screen_slot = context.state_bus.register_slot("genshin.screen_state")
        self._danger_slot = context.state_bus.register_slot("genshin.danger_signals")
        self._cooldown_slot = context.state_bus.register_slot("genshin.cooldown_state")

        processor = _GenshinPerceptionBridge(
            screen_slot=self._screen_slot,
            danger_slot=self._danger_slot,
            cooldown_slot=self._cooldown_slot,
        )
        context.pipeline.add_post_processor(processor)

        from app_service.apps.genshin_skills import (
            GenshinCombatSkill,
            GenshinDodgeReflexSkill,
        )
        context.orchestrator.register_skill("genshin_combat", GenshinCombatSkill(context.state_bus))
        context.orchestrator.register_skill("genshin_dodge", GenshinDodgeReflexSkill(
            context.state_bus, self._danger_slot,
        ))

        context.orchestrator.register_transition("GENSHIN_COMBAT", "GENSHIN_DODGE", "DODGE_TRIGGERED")
        context.orchestrator.register_transition("GENSHIN_DODGE", "GENSHIN_COMBAT", "SUCCESS")

        from app_service.apps.genshin_failure_bridge import GenshinFailureBridge
        self._failure_bridge = GenshinFailureBridge(context.state_bus)
        context.state_bus.subscribe("skill_result", self._failure_bridge.on_skill_result)

        from app_service.apps.genshin_persona_bridge import GenshinPersonaBridge
        self._persona_bridge = GenshinPersonaBridge(context.state_bus)
        context.state_bus.subscribe("interrupt", self._persona_bridge.on_interrupt)

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


class _GenshinPerceptionBridge:
    def __init__(self, screen_slot, danger_slot, cooldown_slot) -> None:
        self._screen_slot = screen_slot
        self._danger_slot = danger_slot
        self._cooldown_slot = cooldown_slot
        self._classifier = None
        self._danger_extractor = None
        self._prev_frame = None

    def _ensure_components(self) -> None:
        if self._classifier is not None:
            return
        try:
            from perception.genshin_screen_classifier import GenshinScreenClassifier
            self._classifier = GenshinScreenClassifier()
        except Exception as e:
            _log.warning("Failed to load GenshinScreenClassifier: %s", e)
        try:
            from combat.danger_detector import GenshinDangerSignalExtractor
            self._danger_extractor = GenshinDangerSignalExtractor()
        except Exception as e:
            _log.warning("Failed to load GenshinDangerSignalExtractor: %s", e)

    def process(self, frame, observation, state_bus) -> None:
        self._ensure_components()
        from dataclasses import asdict
        if self._classifier is not None:
            try:
                screen_state = self._classifier.classify(frame)
                self._screen_slot.put(asdict(screen_state))
                observation.extensions["genshin_screen"] = screen_state.state
            except Exception as e:
                _log.warning("ScreenClassifier.classify failed: %s", e)
                observation.extensions["genshin_screen_error"] = str(e)
        if self._danger_extractor is not None:
            try:
                signals = self._danger_extractor.extract(frame, self._prev_frame)
                self._danger_slot.put({
                    "ground_danger_zone": signals.ground_danger_zone,
                    "projectile_approaching": signals.projectile_approaching,
                    "hp_drop_signal": signals.hp_drop_signal,
                    "overall_danger": signals.overall_danger,
                    "should_dodge": signals.overall_danger >= 0.7,
                })
                observation.extensions["genshin_danger"] = signals.overall_danger
            except Exception as e:
                _log.warning("DangerSignalExtractor.extract failed: %s", e)
                observation.extensions["genshin_danger_error"] = str(e)
        self._prev_frame = frame.copy() if frame is not None else None
