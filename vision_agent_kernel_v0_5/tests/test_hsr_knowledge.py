from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.hsr_knowledge_loader import HSRKnowledgeBase

KNOWLEDGE_DIR = Path("knowledge")


@pytest.fixture
def kb() -> HSRKnowledgeBase:
    return HSRKnowledgeBase(knowledge_dir=KNOWLEDGE_DIR)


# ---------------------------------------------------------------------------
# Loading counts
# ---------------------------------------------------------------------------

class TestLoading:
    def test_load_all_characters(self, kb: HSRKnowledgeBase) -> None:
        assert len(kb.characters) >= 20

    def test_load_all_enemies(self, kb: HSRKnowledgeBase) -> None:
        assert len(kb.enemies) >= 25


# ---------------------------------------------------------------------------
# Character field integrity
# ---------------------------------------------------------------------------

class TestCharacterFields:
    def test_character_fields(self, kb: HSRKnowledgeBase) -> None:
        # Pick a known character
        char = kb.get_character("himeko")
        assert char is not None
        assert char.character_id == "himeko"
        assert char.name  # non-empty
        assert char.name_en  # non-empty
        assert char.rarity in (4, 5)
        assert char.element
        assert char.path
        assert char.skill_sp_cost >= 0
        assert char.ultimate_sp_cost >= 0
        assert char.basic_sp_gain >= 0

    def test_character_id_is_dict_key(self, kb: HSRKnowledgeBase) -> None:
        for cid, char in kb.characters.items():
            assert char.character_id == cid


# ---------------------------------------------------------------------------
# Enemy field integrity
# ---------------------------------------------------------------------------

class TestEnemyFields:
    def test_enemy_fields(self, kb: HSRKnowledgeBase) -> None:
        enemy = kb.get_enemy("voidranger_reaver")
        assert enemy is not None
        assert enemy.enemy_id == "voidranger_reaver"
        assert isinstance(enemy.weaknesses, tuple)
        assert len(enemy.weaknesses) > 0
        assert enemy.toughness > 0

    def test_enemy_weaknesses_are_strings(self, kb: HSRKnowledgeBase) -> None:
        for enemy in kb.enemies.values():
            for w in enemy.weaknesses:
                assert isinstance(w, str)


# ---------------------------------------------------------------------------
# Find by path / element
# ---------------------------------------------------------------------------

class TestFindByPath:
    def test_find_characters_by_path(self, kb: HSRKnowledgeBase) -> None:
        hunt_chars = kb.find_characters_by_path("hunt")
        assert len(hunt_chars) >= 3
        for c in hunt_chars:
            assert c.path == "hunt"

    def test_find_characters_by_element(self, kb: HSRKnowledgeBase) -> None:
        fire_chars = kb.find_characters_by_element("fire")
        assert len(fire_chars) >= 3
        for c in fire_chars:
            assert c.element == "fire"

    def test_find_unknown_path_returns_empty(self, kb: HSRKnowledgeBase) -> None:
        assert kb.find_characters_by_path("nonexistent_path") == []


# ---------------------------------------------------------------------------
# Enemy weaknesses
# ---------------------------------------------------------------------------

class TestEnemyWeaknesses:
    def test_get_enemy_weaknesses(self, kb: HSRKnowledgeBase) -> None:
        weaknesses = kb.get_weaknesses("doomsday_beast")
        assert len(weaknesses) > 0
        assert "fire" in weaknesses
        assert "ice" in weaknesses

    def test_get_weaknesses_unknown_enemy(self, kb: HSRKnowledgeBase) -> None:
        assert kb.get_weaknesses("nonexistent_enemy") == []


# ---------------------------------------------------------------------------
# Element / path coverage
# ---------------------------------------------------------------------------

ALL_ELEMENTS = ("physical", "fire", "ice", "lightning", "wind", "quantum", "imaginary")
ALL_PATHS = ("destruction", "hunt", "erudition", "harmony", "nihility", "preservation", "abundance")


class TestCoverage:
    def test_all_elements_covered(self, kb: HSRKnowledgeBase) -> None:
        covered = {c.element for c in kb.characters.values()}
        for elem in ALL_ELEMENTS:
            assert elem in covered, f"No character covers element '{elem}'"

    def test_all_paths_covered(self, kb: HSRKnowledgeBase) -> None:
        covered = {c.path for c in kb.characters.values()}
        for path in ALL_PATHS:
            assert path in covered, f"No character covers path '{path}'"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_get_character_unknown_returns_none(self, kb: HSRKnowledgeBase) -> None:
        assert kb.get_character("nonexistent") is None

    def test_get_enemy_unknown_returns_none(self, kb: HSRKnowledgeBase) -> None:
        assert kb.get_enemy("nonexistent") is None

    def test_knowledge_base_lazy_loading(self) -> None:
        kb = HSRKnowledgeBase(knowledge_dir=KNOWLEDGE_DIR)
        # Internal caches should start as None before first access
        assert kb._characters is None
        assert kb._enemies is None
        # Accessing property triggers load
        _ = kb.characters
        assert kb._characters is not None
