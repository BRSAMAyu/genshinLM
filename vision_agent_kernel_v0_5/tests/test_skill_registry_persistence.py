"""Tests for SkillRegistry persistence."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from planning.skill_registry import LearnedSkill, SkillRegistry


class TestLearnedSkillPersistence:
    def test_register_and_retrieve(self, tmp_path: Path) -> None:
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_1",
            action="combat_attack",
            steps=({"key": "e"}, {"key": "click"}),
            confidence=0.7,
            capsule_id="genshin",
        )
        registry.register_learned_skill(skill)
        assert registry.get_learned_skill("test_1") is not None
        # File should exist
        assert Path(path).exists()

    def test_persist_and_reload(self, tmp_path: Path) -> None:
        path = str(tmp_path / "skills.json")
        registry1 = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_persist",
            action="explore_chest",
            steps=({"action": "interact"},),
            confidence=0.8,
            verification_count=1,
            capsule_id="genshin",
        )
        registry1.register_learned_skill(skill)

        # New registry instance loads from file
        registry2 = SkillRegistry(persist_path=path)
        loaded = registry2.get_learned_skill("test_persist")
        assert loaded is not None
        assert loaded.action == "explore_chest"
        assert loaded.verification_count == 1

    def test_verification_count_increments(self, tmp_path: Path) -> None:
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        skill = LearnedSkill(
            skill_id="test_verify",
            action="combat_dodge",
            steps=({"key": "space"},),
        )
        registry.register_learned_skill(skill)
        assert registry.get_learned_skill("test_verify").verification_count == 0

        # Re-register — should increment
        registry.register_learned_skill(skill)
        assert registry.get_learned_skill("test_verify").verification_count == 1

        # 3rd registration — should promote to verified
        registry.register_learned_skill(skill)
        assert registry.get_learned_skill("test_verify").trust_level == "verified"

    def test_find_learned_skills(self, tmp_path: Path) -> None:
        path = str(tmp_path / "skills.json")
        registry = SkillRegistry(persist_path=path)
        registry.register_learned_skill(LearnedSkill(
            skill_id="c1", action="combat_attack", steps=(),
        ))
        registry.register_learned_skill(LearnedSkill(
            skill_id="c2", action="combat_dodge", steps=(),
        ))
        registry.register_learned_skill(LearnedSkill(
            skill_id="e1", action="explore_chest", steps=(),
        ))
        combat = registry.find_learned_skills("combat")
        assert len(combat) == 2

    def test_no_file_no_error(self, tmp_path: Path) -> None:
        path = str(tmp_path / "nonexistent" / "skills.json")
        registry = SkillRegistry(persist_path=path)
        assert registry.learned_skills == ()

    def test_empty_registry_load(self, tmp_path: Path) -> None:
        path = str(tmp_path / "skills.json")
        Path(path).write_text("[]")
        registry = SkillRegistry(persist_path=path)
        assert registry.learned_skills == ()
