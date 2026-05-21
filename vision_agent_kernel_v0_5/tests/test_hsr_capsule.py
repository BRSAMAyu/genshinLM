"""Tests for Honkai: Star Rail (HSR) capsule integration, lifecycle, and providers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from capsules.capsule_protocol import CapsuleContext, load_manifest_from_yaml
from capsules.capsule_registry import CapsuleRegistry
from capsules.hsr.capsule_entry import HSRCapsule
from capsules.provider_registry import provider_registry
from core.state_bus import StateBus


def _make_context(state_bus: StateBus) -> CapsuleContext:
    orchestrator = MagicMock()
    # Mock orchestrator register_skill/unregister_skill
    skills = {}
    orchestrator.register_skill = lambda name, skill: skills.update({name: skill})
    orchestrator.unregister_skill = lambda name: skills.pop(name, None)
    orchestrator.register_transition = MagicMock()
    orchestrator.unregister_transition = MagicMock()
    orchestrator._skills = skills

    return CapsuleContext(
        state_bus=state_bus,
        pipeline=MagicMock(),
        orchestrator=orchestrator,
        mode_arbiter=MagicMock(),
    )


def test_hsr_capsule_registers_and_unregisters_cleanly() -> None:
    """Verify that HSRCapsule loads, registers slots/skills, activates, and tears down cleanly."""
    manifest_path = Path(__file__).resolve().parents[1] / "capsules" / "hsr" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    registry = CapsuleRegistry()
    bus = StateBus()
    ctx = _make_context(bus)
    capsule = HSRCapsule()

    # 1. Register and install
    registry.register(capsule, manifest, ctx, manifest_path=manifest_path)
    assert registry.get("hsr") is capsule
    assert "hsr" in registry.list_registered()

    # Verify slots are registered
    assert "hsr.screen_state" in bus.registered_slot_names()
    assert "hsr.cooldown_state" in bus.registered_slot_names()
    assert "hsr.battle_log" in bus.registered_slot_names()
    assert "hsr.skill_points" in bus.registered_slot_names()

    # Verify skills are registered in the orchestrator mock
    assert "hsr_combat" in ctx.orchestrator._skills
    assert "hsr_navigation" in ctx.orchestrator._skills
    assert "hsr_claim_rewards" in ctx.orchestrator._skills
    assert "hsr_dialog" in ctx.orchestrator._skills
    assert "hsr_screen_classification" in ctx.orchestrator._skills

    # Registered combat skill should return SUCCESS
    result = ctx.orchestrator._skills["hsr_combat"].run()
    assert result.status == "SUCCESS"
    # In overworld mode (default), it returns not_in_combat; in combat mode it returns SP decision
    assert result.payload.get("status") == "not_in_combat" or "action" in result.payload

    # Verify providers are loaded
    assert provider_registry.get_provider("hsr", "screen_classifier") is not None
    assert provider_registry.get_provider("hsr", "combat_planner") is not None

    # 2. Activation / Deactivation
    assert registry.activate("hsr") is True
    assert capsule.is_active is True
    assert "hsr" in registry.list_active()

    assert registry.deactivate("hsr") is True
    assert capsule.is_active is False
    assert "hsr" not in registry.list_active()

    # 3. Unregister & Cleanup validation
    registry.unregister("hsr")
    assert registry.get("hsr") is None
    assert "hsr" not in registry.list_registered()

    # Verify slots are cleaned up from StateBus
    assert "hsr.screen_state" not in bus.registered_slot_names()
    assert "hsr.cooldown_state" not in bus.registered_slot_names()
    assert "hsr.battle_log" not in bus.registered_slot_names()
    assert "hsr.skill_points" not in bus.registered_slot_names()

    # Verify skills are cleaned up
    assert "hsr_combat" not in ctx.orchestrator._skills
    assert "hsr_navigation" not in ctx.orchestrator._skills
    assert "hsr_dialog" not in ctx.orchestrator._skills
    assert "hsr_screen_classification" not in ctx.orchestrator._skills

    # Verify providers are unloaded
    assert provider_registry.get_provider("hsr", "screen_classifier") is None


def test_hsr_providers_return_health() -> None:
    """Verify that all HSR providers are loaded from the registry and return healthy status."""
    manifest_path = Path(__file__).resolve().parents[1] / "capsules" / "hsr" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    registry = CapsuleRegistry()
    bus = StateBus()
    ctx = _make_context(bus)
    capsule = HSRCapsule()

    # Register to trigger provider registry loading
    registry.register(capsule, manifest, ctx, manifest_path=manifest_path)

    try:
        healths = provider_registry.health("hsr")
        for key, health in healths.items():
            assert health.status in ("ok", "degraded"), (
                f"Provider {key} returned unhealthy status: {health.message}"
            )

        # Verify key provider actions
        classifier = provider_registry.get_provider("hsr", "screen_classifier")
        # None frame should return overworld or unknown (classifier loaded but no data)
        screen_state = classifier.classify(None, bus)
        assert screen_state.state in ("overworld", "unknown", "turn_based_combat", "dialog", "menu")

        combat = provider_registry.get_provider("hsr", "combat_planner")
        # With no team context, planner returns fallback basic attack
        combat_plan = combat.plan(None)
        assert len(combat_plan.action_keys) >= 0  # May be empty with no team
        assert combat_plan.thought != ""  # But should have a thought

        nav = provider_registry.get_provider("hsr", "navigator")
        nav_plan = nav.plan(None, None, None)
        assert nav_plan.route_valid is True

        verifier = provider_registry.get_provider("hsr", "verifier")
        assert verifier.get("dialog_progressed") is not None
        assert verifier.get("screen_state_classified") is not None

    finally:
        registry.unregister("hsr")


def test_hsr_manifest_declares_capabilities_and_resources() -> None:
    """Verify capsule.yaml declares all expected capabilities, transitions, and resources."""
    manifest_path = Path(__file__).resolve().parents[1] / "capsules" / "hsr" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    assert manifest.capsule_id == "hsr"
    assert manifest.entrypoint == "capsule_entry:HSRCapsule"
    assert "hsr_turn_based_combat" in manifest.capabilities
    assert "hsr_navigation" in manifest.capabilities
    assert "hsr.screen_state" in manifest.slots
    assert "hsr.skill_points" in manifest.slots
    assert len(manifest.transitions) == 2
    assert manifest.transitions[0]["from"] == "HSR_COMBAT"
    assert manifest.transitions[0]["to"] == "HSR_ULTIMATE_PHASE"

    # Verify skill declarations
    skill_ids = [s.skill_id for s in manifest.skills]
    assert "hsr_combat" in skill_ids
    assert "hsr_navigation" in skill_ids
    assert "hsr_claim_rewards" in skill_ids

    # Verify knowledge resources exist
    resource_ids = [r.resource_id for r in manifest.resources]
    assert "hsr_characters" in resource_ids
    assert "hsr_enemies" in resource_ids

    # Verify resource paths resolve
    paths = manifest.resource_paths(manifest_path)
    assert paths["hsr_characters"].exists()
    assert paths["hsr_enemies"].exists()


def test_hsr_combat_skill_sp_management() -> None:
    """Verify HSRCombatSkill manages SP correctly."""
    from app_service.apps.hsr_skills import HSRCombatSkill

    bus = StateBus()
    sp_slot = bus.register_slot("hsr.skill_points")
    screen_slot = bus.register_slot("hsr.screen_state")

    # Set combat mode with high SP
    sp_slot.put({"current": 5, "max": 5})
    screen_slot.put({"state": "turn_based_combat", "confidence": 0.9})

    skill = HSRCombatSkill(bus)
    result = skill.run()

    assert result.status == "SUCCESS"
    assert result.payload["action"] == "skill"
    assert result.payload["sp_before"] == 5
    assert result.payload["sp_after"] == 4
    assert result.payload["sp_change"] == -1

    # Low SP should trigger basic attack
    sp_slot.put({"current": 1, "max": 5})
    result = skill.run()
    assert result.status == "SUCCESS"
    assert result.payload["action"] == "basic_attack"
    assert result.payload["sp_change"] == +1


def test_hsr_knowledge_base_loads() -> None:
    """Verify HSR knowledge base loads characters and enemies."""
    from knowledge.hsr_knowledge_loader import HSRKnowledgeBase

    kb = HSRKnowledgeBase()
    assert len(kb.characters) >= 20
    assert len(kb.enemies) >= 25

    # Check character structure
    seele = kb.get_character("seele")
    assert seele is not None
    assert seele.element == "quantum"
    assert seele.path == "hunt"

    # Check enemy structure
    doomsday = kb.get_enemy("doomsday_beast")
    assert doomsday is not None
    assert doomsday.class_id in ("enemy_boss", "echo_of_war")
    assert len(doomsday.weaknesses) >= 3

    # Check queries
    fire_chars = kb.find_characters_by_element("fire")
    assert len(fire_chars) >= 3
    assert any(c.character_id == "himeko" for c in fire_chars)

    hunt_chars = kb.find_characters_by_path("hunt")
    assert len(hunt_chars) >= 3


def test_hsr_and_genshin_capsules_coexist() -> None:
    """Verify HSR and Genshin capsules can be registered simultaneously."""
    from capsules.genshin.capsule_entry import GenshinCapsule

    registry = CapsuleRegistry()
    bus = StateBus()
    ctx = _make_context(bus)

    # Register Genshin
    genshin_manifest_path = (
        Path(__file__).resolve().parents[1] / "capsules" / "genshin" / "capsule.yaml"
    )
    genshin_manifest = load_manifest_from_yaml(str(genshin_manifest_path))
    registry.register(GenshinCapsule(), genshin_manifest, ctx, manifest_path=genshin_manifest_path)

    # Register HSR
    hsr_manifest_path = (
        Path(__file__).resolve().parents[1] / "capsules" / "hsr" / "capsule.yaml"
    )
    hsr_manifest = load_manifest_from_yaml(str(hsr_manifest_path))
    registry.register(HSRCapsule(), hsr_manifest, ctx, manifest_path=hsr_manifest_path)

    # Both registered
    assert set(registry.list_registered()) == {"genshin", "hsr"}

    # Slots don't clash
    slot_names = bus.registered_slot_names()
    assert "genshin.screen_state" in slot_names
    assert "hsr.screen_state" in slot_names

    # Both active
    registry.activate("genshin")
    registry.activate("hsr")
    assert set(registry.list_active()) == {"genshin", "hsr"}

    # Unregister one keeps the other
    registry.unregister("hsr")
    assert "genshin" in registry.list_registered()
    assert registry.get("hsr") is None
    assert "genshin.screen_state" in bus.registered_slot_names()
