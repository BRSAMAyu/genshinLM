from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from capsules.domain_protocols import (
    CombatContext,
    CombatPlan,
    DialogState,
    KnowledgeQuery,
    KnowledgeResult,
    NavigationGoal,
    NavigationPlan,
    ProviderHealth,
    ScreenState,
)

_log = logging.getLogger("hsr.providers")


class HSRScreenClassifierProvider:
    """Wraps HSRScreenClassifier for real screen state detection."""

    def __init__(self) -> None:
        self._classifier = None
        try:
            from perception.hsr_screen_classifier import HSRScreenClassifier
            self._classifier = HSRScreenClassifier()
        except Exception as e:
            _log.debug("HSRScreenClassifier not available (lazy): %s", e)

    def classify(self, frame: Any, state_bus: Any) -> ScreenState:
        if self._classifier is None:
            return ScreenState("overworld", confidence=0.5, active_regions=[])
        try:
            res = self._classifier.classify(frame)
            return ScreenState(
                state=res.state,
                confidence=res.confidence,
                active_regions=list(res.indicators.keys()),
                metadata=res.indicators,
            )
        except Exception as e:
            _log.warning("HSRScreenClassifier.classify failed: %s", e)
            return ScreenState("unknown", confidence=0.0, metadata={"error": str(e)})

    def health(self) -> ProviderHealth:
        status = "ok" if self._classifier is not None else "degraded"
        msg = "HSRScreenClassifier loaded" if self._classifier else "HSRScreenClassifier not loaded"
        return ProviderHealth(status, msg)


class HSRCombatPlannerProvider:
    """Wraps HSRCombatPlanner for turn-based combat planning."""

    def __init__(self) -> None:
        self._planner = None
        try:
            from combat.hsr_combat_planner import HSRCombatPlanner
            self._planner = HSRCombatPlanner()
        except Exception as e:
            _log.debug("HSRCombatPlanner not available (lazy): %s", e)

    def plan(self, context: CombatContext | None) -> CombatPlan:
        if self._planner is None:
            return CombatPlan(
                action_keys=["Q"],
                thought="Planner not loaded, fallback to basic attack",
            )
        if context is None:
            context = CombatContext()

        from combat.hsr_combat_planner import HSRCharacterState

        team_data = context.extensions.get("team", [])
        weaknesses = context.extensions.get("enemy_weaknesses", [])
        sp = context.extensions.get("skill_points", 3)

        team: list[HSRCharacterState] = []
        for i, char_data in enumerate(team_data):
            if isinstance(char_data, dict):
                team.append(HSRCharacterState(
                    character_id=char_data.get("character_id", f"char_{i+1}"),
                    position=i + 1,
                    element=char_data.get("element", "physical"),
                    path=char_data.get("path", "destruction"),
                    hp_ratio=char_data.get("hp_ratio", 1.0),
                    ultimate_ready=char_data.get("ultimate_ready", False),
                ))
            elif isinstance(char_data, HSRCharacterState):
                team.append(char_data)

        plan = self._planner.generate_plan(
            team=team,
            enemy_weaknesses=weaknesses,
            current_sp=sp,
        )

        action_keys: list[str] = []
        for action in plan.turn_rotation:
            if action.action == "skill":
                action_keys.append("E")
            elif action.action == "ultimate":
                action_keys.append(str(action.character_pos))
            else:
                action_keys.append("Q")

        return CombatPlan(
            action_keys=action_keys,
            thought=f"HSR plan: {plan.plan_id}, fallback={plan.fallback_strategy}",
            should_interrupt=bool(plan.ultimate_interrupts),
            metadata={"plan_id": plan.plan_id, "sp_budget": plan.sp_budget},
        )

    def health(self) -> ProviderHealth:
        status = "ok" if self._planner is not None else "degraded"
        msg = "HSRCombatPlanner loaded" if self._planner else "HSRCombatPlanner not loaded"
        return ProviderHealth(status, msg)


class HSRNavigatorProvider:
    """Wraps HSRNavigator for map-based navigation."""

    def __init__(self) -> None:
        self._navigator = None
        try:
            from navigation.hsr_navigator import HSRNavigator
            self._navigator = HSRNavigator()
        except Exception as e:
            _log.debug("HSRNavigator not available (lazy): %s", e)

    def plan(self, goal: NavigationGoal | None, screen_state: ScreenState | None, knowledge: Any) -> NavigationPlan:
        if self._navigator is None or goal is None:
            target = goal.target if goal else "unknown"
            return NavigationPlan(
                steps=[{"input_type": "press_key", "target": "M", "label": f"navigate_to_{target}"}],
                total_steps=1,
                route_valid=True,
                thought="Navigator not loaded, returning minimal plan",
            )

        nav_plan = self._navigator.plan_teleport("current", goal.target)
        return NavigationPlan(
            steps=[{"input_type": s.input_type, "target": s.target, "label": s.label} for s in nav_plan.steps],
            total_steps=len(nav_plan.steps),
            route_valid=True,
            thought=f"Teleport plan to {nav_plan.destination}",
        )

    def health(self) -> ProviderHealth:
        status = "ok" if self._navigator is not None else "degraded"
        msg = "HSRNavigator loaded" if self._navigator else "HSRNavigator not loaded"
        return ProviderHealth(status, msg)


class HSRDialogHandlerProvider:
    """Wraps HSRDialogHandler for dialog detection and interaction."""

    def __init__(self) -> None:
        self._handler = None
        try:
            from navigation.hsr_dialog_handler import HSRDialogHandler
            self._handler = HSRDialogHandler()
        except Exception as e:
            _log.debug("HSRDialogHandler not available (lazy): %s", e)

    def detect(self, frame: Any, screen_state: ScreenState) -> DialogState:
        if self._handler is None:
            return DialogState()
        try:
            state = screen_state.state if screen_state else "unknown"
            result = self._handler.detect_dialog(frame, state)
            return DialogState(
                in_dialog=result.in_dialog,
                dialog_text=result.dialog_text,
                options=result.options,
                option_click_zones=result.option_click_zones,
                can_skip=result.can_skip,
            )
        except Exception as e:
            _log.warning("HSRDialogHandler.detect failed: %s", e)
            return DialogState()

    def health(self) -> ProviderHealth:
        status = "ok" if self._handler is not None else "degraded"
        msg = "HSRDialogHandler loaded" if self._handler else "HSRDialogHandler not loaded"
        return ProviderHealth(status, msg)


class HSRKnowledgeProvider:
    """Wraps HSRKnowledgeBase for game knowledge queries."""

    def __init__(self) -> None:
        self._kb = None
        try:
            from knowledge.hsr_knowledge_loader import HSRKnowledgeBase
            self._kb = HSRKnowledgeBase()
        except Exception as e:
            _log.debug("HSRKnowledgeBase not available (lazy): %s", e)

    def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        if self._kb is None:
            return KnowledgeResult(found=False)
        try:
            if query.category == "characters":
                char = self._kb.get_character(query.query_string)
                if char:
                    return KnowledgeResult(found=True, payload=asdict(char))
            elif query.category == "enemies":
                enemy = self._kb.get_enemy(query.query_string)
                if enemy:
                    return KnowledgeResult(found=True, payload=asdict(enemy))
            elif query.category == "weaknesses":
                weaknesses = self._kb.get_weaknesses(query.query_string)
                return KnowledgeResult(found=True, payload={"weaknesses": weaknesses})
            elif query.category == "characters_by_path":
                chars = self._kb.find_characters_by_path(query.query_string)
                return KnowledgeResult(
                    found=bool(chars),
                    payload={"characters": [asdict(c) for c in chars]},
                )
            elif query.category == "characters_by_element":
                chars = self._kb.find_characters_by_element(query.query_string)
                return KnowledgeResult(
                    found=bool(chars),
                    payload={"characters": [asdict(c) for c in chars]},
                )
        except Exception as e:
            _log.warning("HSRKnowledgeProvider.query failed: %s", e)
            return KnowledgeResult(found=False, confidence=0.0)
        return KnowledgeResult(found=False)

    def health(self) -> ProviderHealth:
        status = "ok" if self._kb is not None else "degraded"
        msg = "HSRKnowledgeBase loaded" if self._kb else "HSRKnowledgeBase not loaded"
        return ProviderHealth(status, msg)


class HSRVerifierProvider:
    """HSR verifiers resolver."""

    _HSR_VERIFIERS = frozenset({
        "combat_finished",
        "nav_destination_reached",
        "reward_claimed",
        "dialog_progressed",
        "screen_state_classified",
    })

    def get(self, verifier_id: str) -> Any | None:
        if verifier_id in self._HSR_VERIFIERS:
            try:
                from execution.ui_verifier import UIVerifier
                return UIVerifier()
            except Exception:
                return None
        return None

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "HSRVerifierProvider is healthy")
