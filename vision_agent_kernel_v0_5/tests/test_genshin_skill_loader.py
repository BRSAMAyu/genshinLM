from __future__ import annotations

from pathlib import Path

import pytest

from combat.genshin_skill_loader import (
    GenshinSkillLoader,
    GenshinSkill,
    SkillStep,
    SkillValidationError,
    SkillNotFoundError,
)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "data" / "skills"


def test_load_combat_skill() -> None:
    loader = GenshinSkillLoader(skills_dir=SKILLS_DIR)
    skill = loader.load_skill("safe_combat_genshin_v1")

    assert isinstance(skill, GenshinSkill)
    assert skill.skill_id == "safe_combat_genshin_v1"
    assert skill.type == "combat"
    assert skill.name == "Genshin Safe Combat Loop v1"
    assert len(skill.steps) >= 7

    step_ids = [s.step_id for s in skill.steps]
    assert "maintain_lock" in step_ids
    assert "normal_attack_combo" in step_ids
    assert "dodge_on_danger" in step_ids
    assert "switch_character" in step_ids

    maintain = next(s for s in skill.steps if s.step_id == "maintain_lock")
    assert isinstance(maintain, SkillStep)
    assert maintain.type == "checkpoint"

    assert "skill_e_ready" in skill.visual_triggers
    assert "burst_q_ready" in skill.visual_triggers
    assert skill.visual_triggers["skill_e_ready"].detection == "skill_icon_not_greyed"

    assert "target_eliminated" in skill.success_criteria
    assert skill.safety["dry_run_default"] is True


def test_load_collection_skill() -> None:
    loader = GenshinSkillLoader(skills_dir=SKILLS_DIR)
    skill = loader.load_skill("collect_plant_genshin_v1")

    assert skill.skill_id == "collect_plant_genshin_v1"
    assert skill.type == "collection"
    assert len(skill.steps) == 5

    step_ids = [s.step_id for s in skill.steps]
    assert "approach_target" in step_ids
    assert "align_center" in step_ids
    assert "wait_f_prompt" in step_ids
    assert "press_f" in step_ids
    assert "verify_collection" in step_ids

    assert "interact_prompt_visible" in skill.visual_triggers
    assert skill.failure_policy["max_retries"] == 2


def test_load_all_skills() -> None:
    loader = GenshinSkillLoader(skills_dir=SKILLS_DIR)
    all_skills = loader.load_all()

    assert len(all_skills) == 10

    combat_ids = [sid for sid, s in all_skills.items() if s.type == "combat"]
    collection_ids = [sid for sid, s in all_skills.items() if s.type == "collection"]
    navigation_ids = [sid for sid, s in all_skills.items() if s.type == "navigation"]

    assert len(combat_ids) == 3
    assert len(collection_ids) == 3
    assert len(navigation_ids) == 4


def test_skill_inheritance() -> None:
    loader = GenshinSkillLoader(skills_dir=SKILLS_DIR)
    boss = loader.load_skill("boss_combat_genshin_v1")

    assert boss.skill_id == "boss_combat_genshin_v1"

    inherited_ids = [s.step_id for s in boss.steps]
    assert "maintain_lock" in inherited_ids
    assert "normal_attack_combo" in inherited_ids
    assert "dodge_on_danger" in inherited_ids

    assert "detect_phase_change" in inherited_ids
    assert "check_weakpoint" in inherited_ids
    assert "attack_weakpoint" in inherited_ids
    assert "q_burst_iframe_dodge" in inherited_ids

    assert "boss_phase_changed" in boss.visual_triggers
    assert "weakpoint_visible" in boss.visual_triggers
    assert "skill_e_ready" in boss.visual_triggers
    assert "burst_q_ready" in boss.visual_triggers

    assert boss.safety["max_duration_ms"] == 120000
    assert boss.failure_policy["max_retries"] == 5


def test_invalid_skill_raises() -> None:
    loader = GenshinSkillLoader(skills_dir=SKILLS_DIR)

    with pytest.raises(SkillNotFoundError):
        loader.load_skill("nonexistent_skill_xyz")

    import tempfile
    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        bad_yaml = Path(tmpdir) / "genshin_bad.yaml"
        bad_yaml.write_text(
            yaml.dump(
                {
                    "skills": {
                        "bad_skill": {
                            "skill_id": "bad_skill",
                            "name": "Bad",
                            # missing: type, environment_profile, steps, etc.
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        bad_loader = GenshinSkillLoader(skills_dir=Path(tmpdir))
        with pytest.raises(SkillValidationError):
            bad_loader.load_skill("bad_skill")
