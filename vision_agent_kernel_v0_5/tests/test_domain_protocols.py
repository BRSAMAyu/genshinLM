"""Tests to verify that domain protocols and data payloads are completely game-agnostic."""

from __future__ import annotations

import sys
from typing import get_type_hints

from capsules.domain_protocols import (
    CombatContext,
    CombatPlan,
    CooldownProviderProtocol,
    DialogHandlerProtocol,
    DialogState,
    KnowledgeProviderProtocol,
    KnowledgeQuery,
    KnowledgeResult,
    NavigationGoal,
    NavigationPlan,
    NavigatorProtocol,
    ProviderHealth,
    ScreenClassifierProtocol,
    ScreenState,
    VerifierProviderProtocol,
)


def test_domain_protocols_are_game_agnostic() -> None:
    """Verify that all domain protocols and dataclasses contain zero references to genshin or hsr."""
    payload_classes = [
        ProviderHealth,
        ScreenState,
        CombatContext,
        CombatPlan,
        NavigationGoal,
        NavigationPlan,
        DialogState,
        KnowledgeQuery,
        KnowledgeResult,
    ]

    protocols = [
        ScreenClassifierProtocol,
        CombatPlannerProtocol,
        NavigatorProtocol,
        DialogHandlerProtocol,
        CooldownProviderProtocol,
        KnowledgeProviderProtocol,
        VerifierProviderProtocol,
    ] if "CombatPlannerProtocol" in globals() else [
        ScreenClassifierProtocol,
        NavigatorProtocol,
        DialogHandlerProtocol,
        CooldownProviderProtocol,
        KnowledgeProviderProtocol,
        VerifierProviderProtocol,
    ]
    # Import combat planner protocol dynamically if it exists
    try:
        from capsules.domain_protocols import CombatPlannerProtocol
        protocols.append(CombatPlannerProtocol)
    except ImportError:
        pass

    # Check that type annotations don't mention genshin or hsr
    for cls in payload_classes + protocols:
        hints = get_type_hints(cls)
        for name, hint_type in hints.items():
            hint_str = str(hint_type).lower()
            assert "genshin" not in hint_str, f"Found genshin in type hint of {cls.__name__}.{name}: {hint_type}"
            assert "hsr" not in hint_str, f"Found hsr in type hint of {cls.__name__}.{name}: {hint_type}"


def test_dataclass_instantiation() -> None:
    """Verify standard instantiation of the protocol data structures."""
    health = ProviderHealth(status="ok", message="All systems nominal")
    assert health.status == "ok"
    assert health.message == "All systems nominal"

    state = ScreenState(state="overworld", confidence=0.99, active_regions=["minimap"])
    assert state.state == "overworld"
    assert state.confidence == 0.99
    assert "minimap" in state.active_regions

    ctx = CombatContext(character_hp={"character_1": 100.0}, active_character="character_1")
    assert ctx.character_hp["character_1"] == 100.0
    assert ctx.active_character == "character_1"

    plan = CombatPlan(action_keys=["normal_attack"], thought="strike")
    assert plan.action_keys == ["normal_attack"]
    assert plan.thought == "strike"

    goal = NavigationGoal(goal_type="marker", target="quest_1")
    assert goal.goal_type == "marker"
    assert goal.target == "quest_1"

    nav_plan = NavigationPlan(steps=[{"type": "move"}], route_valid=True)
    assert len(nav_plan.steps) == 1
    assert nav_plan.route_valid is True

    dialog = DialogState(in_dialog=True, dialog_text="Hello", options=["Option A"])
    assert dialog.in_dialog is True
    assert dialog.dialog_text == "Hello"
    assert dialog.options == ["Option A"]

    query = KnowledgeQuery(category="quests", query_string="quest_marker_1")
    assert query.category == "quests"
    assert query.query_string == "quest_marker_1"

    result = KnowledgeResult(found=True, payload={"id": "quest_1"})
    assert result.found is True
    assert result.payload == {"id": "quest_1"}
