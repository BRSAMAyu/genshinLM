from __future__ import annotations

from typing import Any, Dict

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


class GenshinScreenClassifierProvider:
    """Wraps perception.genshin_screen_classifier.GenshinScreenClassifier."""

    def __init__(self) -> None:
        self._classifier = None
        try:
            from perception.genshin_screen_classifier import GenshinScreenClassifier
            self._classifier = GenshinScreenClassifier()
        except Exception:
            pass

    def classify(self, frame: Any, state_bus: Any) -> ScreenState:
        if self._classifier is None:
            return ScreenState("unknown", confidence=0.0)
        try:
            res = self._classifier.classify(frame)
            return ScreenState(
                state=res.state,
                confidence=res.confidence,
                active_regions=list(res.metadata.keys()) if hasattr(res, "metadata") else [],
                metadata=dict(res.metadata) if hasattr(res, "metadata") else {},
            )
        except Exception as e:
            return ScreenState("unknown", confidence=0.0, metadata={"error": str(e)})

    def health(self) -> ProviderHealth:
        if self._classifier is not None:
            return ProviderHealth("ok", "GenshinScreenClassifier loaded successfully")
        return ProviderHealth("degraded", "GenshinScreenClassifier failed to load")


class GenshinCombatPlannerProvider:
    """Wraps Genshin combat planning routines."""

    def plan(self, context: CombatContext) -> CombatPlan:
        # Check active character and overall danger
        if context.danger_level >= 0.7:
            # P1 Dodge trigger
            return CombatPlan(
                action_keys=["Shift"],
                thought="High danger detected! Execute sprint/dodge.",
                should_interrupt=True,
            )
        # Normal attack cycle
        return CombatPlan(
            action_keys=["LMB", "E", "Q"],
            thought="Normal combat routine.",
            should_interrupt=False,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinCombatPlannerProvider is healthy")


class GenshinNavigatorProvider:
    """Wraps Genshin navigation routines."""

    def plan(self, goal: NavigationGoal, screen_state: ScreenState, knowledge: Any) -> NavigationPlan:
        # Standard synthetic navigation step
        return NavigationPlan(
            steps=[{"action": "move_forward", "duration": 1.0}],
            total_steps=1,
            route_valid=True,
            thought=f"Navigating toward goal target: '{goal.target}'",
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinNavigatorProvider is healthy")


class GenshinDialogHandlerProvider:
    """Wraps Genshin dialog detection and choice selection."""

    def detect(self, frame: Any, screen_state: ScreenState) -> DialogState:
        if screen_state.state == "dialog":
            return DialogState(
                in_dialog=True,
                dialog_text="Synthetic Genshin conversation",
                options=["Option 1", "Option 2"],
                option_click_zones=[(100, 100, 200, 200)],
                can_skip=True,
            )
        return DialogState(in_dialog=False)

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinDialogHandlerProvider is healthy")


class GenshinKnowledgeProvider:
    """Wraps Genshin game asset knowledge queries."""

    def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        if query.category == "keymaps":
            return KnowledgeResult(
                found=True,
                payload={"normal_attack": "LMB", "elemental_skill": "E", "elemental_burst": "Q"},
            )
        return KnowledgeResult(found=False)

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinKnowledgeProvider is healthy")


class GenshinVerifierProvider:
    """Dynamically resolves existing Genshin verifiers by ID."""

    def get(self, verifier_id: str) -> Any | None:
        # Simple resolution map
        if verifier_id in {"combat_state_clear", "danger_cleared", "marker_visible", "route_progress"}:
            from execution.collection_verifier import CollectionVerifier
            return CollectionVerifier()
        return None

    def health(self) -> ProviderHealth:
        return ProviderHealth("ok", "GenshinVerifierProvider is healthy")
