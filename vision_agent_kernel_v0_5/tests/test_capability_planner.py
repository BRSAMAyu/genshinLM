"""Tests for the CapabilityPlanner, PlanValidator, and Skill Contract v2 schemas."""

from __future__ import annotations

from pathlib import Path

import pytest

from capsules.capsule_protocol import load_manifest_from_yaml
from capsules.capsule_registry import CapsuleRegistry
from planning.capability_planner import CapabilityPlanner
from planning.intent_parser import ParsedIntent
from planning.mission_queue import MissionGoal, MissionNode, MissionQueue
from planning.plan_validator import PlanValidator
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog


@pytest.fixture
def test_catalog() -> SkillCapabilityCatalog:
    """Create a unified catalog populated with core, Genshin, and HSR skills."""
    entries = [
        # Genshin skills
        SkillCatalogEntry(
            skill_id="genshin_combat",
            capsule_id="genshin",
            source="capsule_manifest",
            kind="runtime_skill",
            capabilities=["arpg_combat"],
            verifiers=["combat_state_clear"],
            risk_level="medium",
            capabilities_provided=["arpg_combat"],
        ),
        SkillCatalogEntry(
            skill_id="genshin_navigation",
            capsule_id="genshin",
            source="capsule_manifest",
            kind="declarative_skill_pack",
            capabilities=["navigation"],
            verifiers=["marker_visible"],
            risk_level="low",
            capabilities_provided=["navigation"],
        ),
        # HSR skills
        SkillCatalogEntry(
            skill_id="hsr_combat",
            capsule_id="hsr",
            source="capsule_manifest",
            kind="turn_based_skill",
            capabilities=["hsr_turn_based_combat"],
            verifiers=["combat_finished"],
            risk_level="medium",
            capabilities_provided=["hsr_turn_based_combat"],
        ),
        SkillCatalogEntry(
            skill_id="hsr_navigation",
            capsule_id="hsr",
            source="capsule_manifest",
            kind="grid_nav_skill",
            capabilities=["hsr_navigation"],
            verifiers=[],  # Unverified
            risk_level="high",  # High risk
            capabilities_provided=["hsr_navigation"],
        ),
        SkillCatalogEntry(
            skill_id="hsr_claim_rewards",
            capsule_id="hsr",
            source="capsule_manifest",
            kind="menu_interaction_skill",
            capabilities=["hsr_reward_claim"],
            verifiers=["reward_claimed"],
            risk_level="human_confirm",  # requires user confirmation
            capabilities_provided=["hsr_reward_claim"],
        ),
    ]
    return SkillCapabilityCatalog(entries)


def test_capability_planner_selects_genshin_skill(test_catalog: SkillCapabilityCatalog) -> None:
    """Verify CapabilityPlanner selects the correct skill for Genshin intent."""
    planner = CapabilityPlanner(test_catalog)
    
    # Using explicit string intent
    proposal = planner.plan(intent="combat", active_capsule_id="genshin")
    assert proposal.capsule_id == "genshin"
    assert "genshin_combat" in proposal.selected_skill_ids
    assert proposal.requires_user_confirmation is False
    assert proposal.verifier_coverage == 1.0


def test_capability_planner_selects_hsr_skill(test_catalog: SkillCapabilityCatalog) -> None:
    """Verify CapabilityPlanner selects the correct skill for HSR intent."""
    planner = CapabilityPlanner(test_catalog)
    
    proposal = planner.plan(intent="unknown target", active_capsule_id="hsr")
    assert proposal.capsule_id == "hsr"
    # Fallback to navigation as intent is not recognized and falls back to hsr_navigation
    assert "hsr_navigation" in proposal.selected_skill_ids


def test_capability_planner_rejects_unverified_skill_in_strict_mode(test_catalog: SkillCapabilityCatalog) -> None:
    """Verify that in strict mode, capability planner filters out high risk skills without verifiers."""
    planner = CapabilityPlanner(test_catalog)
    
    # HSR Navigation is high-risk and has NO verifiers in our mock catalog
    proposal = planner.plan(
        intent="navigation",
        active_capsule_id="hsr",
        strict_mode=True,
        required_capabilities=["hsr_navigation"],
    )
    
    assert "hsr_navigation" not in proposal.selected_skill_ids
    assert "hsr_navigation" in proposal.missing_capabilities
    assert any(
        entry.skill_id == "hsr_navigation" and "high_risk_without_verifier" in reason
        for entry, reason in proposal.rejected_candidates
    )


def test_skill_contract_v2_validation(test_catalog: SkillCapabilityCatalog) -> None:
    """Verify plan validator checks skill contract risks, verifiers, and user confirmation in strict mode."""
    validator = PlanValidator()
    
    # Node 1: High risk but has verifier. OK.
    node_ok = MissionNode(
        id="node_1",
        type="action",
        skill_binding="hsr_combat",
        verifier="combat_finished",
        failure_policy={},
    )
    
    # Node 2: Human confirm skill. Requires confirmation.
    node_confirm = MissionNode(
        id="node_2",
        type="action",
        skill_binding="hsr_claim_rewards",
        verifier="reward_claimed",
        failure_policy={},
    )

    # 1. Test failure when strict_mode is True and requires_user_confirmation is False
    queue_fail = MissionQueue(
        mission_id="test_queue",
        goal=MissionGoal(type="collect", resource_id="hsr_reward_claim"),
        nodes=[node_confirm],
        requires_user_confirmation=False,
    )
    
    result = validator.validate(
        queue_fail,
        available_skills={"hsr_claim_rewards"},
        strict_mode=True,
        catalog=test_catalog,
    )
    
    assert result["ok"] is False
    assert any("requires user confirmation" in err for err in result["errors"])

    # 2. Test success when strict_mode is True and requires_user_confirmation is True
    queue_ok = MissionQueue(
        mission_id="test_queue_ok",
        goal=MissionGoal(type="combat", resource_id="hsr_turn_based_combat"),
        nodes=[node_ok],
        requires_user_confirmation=True,
    )
    
    result = validator.validate(
        queue_ok,
        available_skills={"hsr_combat"},
        strict_mode=True,
        catalog=test_catalog,
    )
    
    assert result["ok"] is True


def test_skill_contract_v2_schema_parsing() -> None:
    """Verify that Skill Contract v2 fields are successfully parsed from capsule.yaml."""
    manifest_path = Path(__file__).resolve().parents[1] / "capsules" / "hsr" / "capsule.yaml"
    manifest = load_manifest_from_yaml(str(manifest_path))

    # Verify combat skill specs match v2 schema
    combat_skill = next(s for s in manifest.skills if s.skill_id == "hsr_combat")
    assert combat_skill.risk_level == "medium"
    assert "hsr_turn_based_combat" in combat_skill.capabilities_provided
    assert "combat_finished" in combat_skill.verifiers
    assert "hsr_keymap" in combat_skill.resources

    # Verify claim rewards specs
    claim_rewards = next(s for s in manifest.skills if s.skill_id == "hsr_claim_rewards")
    assert claim_rewards.risk_level == "human_confirm"
    assert "hsr_reward_claim" in claim_rewards.capabilities_provided
    assert "reward_claimed" in claim_rewards.verifiers


def test_planner_selects_skills_from_real_capsule_manifests() -> None:
    """Real capsule manifests must be directly usable by the planner without hand-written catalog aliases."""
    repo_root = Path(__file__).resolve().parents[1]
    genshin_manifest = load_manifest_from_yaml(str(repo_root / "capsules" / "genshin" / "capsule.yaml"))
    hsr_manifest = load_manifest_from_yaml(str(repo_root / "capsules" / "hsr" / "capsule.yaml"))
    catalog = SkillCapabilityCatalog.from_sources(manifests=[genshin_manifest, hsr_manifest])
    planner = CapabilityPlanner(catalog)

    genshin_combat = planner.plan(intent="combat", active_capsule_id="genshin")
    assert genshin_combat.missing_capabilities == []
    assert genshin_combat.selected_skill_ids == ["genshin_combat"]

    hsr_dialog = planner.plan(intent="dialog progression", active_capsule_id="hsr")
    assert hsr_dialog.missing_capabilities == []
    assert hsr_dialog.selected_skill_ids == ["hsr_dialog"]

    hsr_reward = planner.plan(intent="claim reward", active_capsule_id="hsr")
    assert hsr_reward.missing_capabilities == []
    assert hsr_reward.selected_skill_ids == ["hsr_claim_rewards"]
    assert hsr_reward.requires_user_confirmation is True
