from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.genshin_knowledge_loader import GenshinKnowledgeBase

KNOWLEDGE_DIR = Path("knowledge")


@pytest.fixture
def kb() -> GenshinKnowledgeBase:
    return GenshinKnowledgeBase(knowledge_dir=KNOWLEDGE_DIR)


def test_load_all_resources(kb: GenshinKnowledgeBase) -> None:
    assert len(kb.resources) > 30


def test_load_all_monsters(kb: GenshinKnowledgeBase) -> None:
    assert len(kb.monsters) > 20


def test_find_resources_by_region_mondstadt(kb: GenshinKnowledgeBase) -> None:
    mondstadt_resources = kb.find_resources_by_region("mondstadt")
    assert len(mondstadt_resources) > 0
    ids = {r.resource_id for r in mondstadt_resources}
    assert "cecilia" in ids
    assert "dandelion_seed" in ids
    assert "wolfhook" in ids


def test_find_monsters_by_class_boss(kb: GenshinKnowledgeBase) -> None:
    bosses = kb.find_monsters_by_class("monster_boss")
    assert len(bosses) > 0
    ids = {m.monster_id for m in bosses}
    assert "pyro_regisvine" in ids
    assert "oceanid" in ids


def test_get_weakness_for_pyro_slime(kb: GenshinKnowledgeBase) -> None:
    weaknesses = kb.get_weakness("pyro_slime")
    assert "hydro" in weaknesses
    assert "cryo" in weaknesses


def test_resource_has_required_fields(kb: GenshinKnowledgeBase) -> None:
    crystal = kb.get_resource("crystal_chunk")
    assert crystal is not None
    assert crystal.name == "水晶块"
    assert crystal.name_en == "Crystal Chunk"
    assert crystal.type == "mineral"
    assert crystal.interaction == "attack"
    assert crystal.attack_count >= 1
    assert len(crystal.regions) > 0
    assert crystal.visual != ""


def test_region_info_complete(kb: GenshinKnowledgeBase) -> None:
    expected = {"mondstadt", "liyue", "inazuma", "sumeru", "fontaine", "natlan", "snezhnaya"}
    assert set(kb.regions.keys()) == expected
    for region_id in expected:
        region = kb.get_region(region_id)
        assert region is not None
        assert region.name != ""
        assert region.element_theme != ""


def test_waypoints_exist(kb: GenshinKnowledgeBase) -> None:
    assert len(kb.waypoints) >= 20
    assert "monstadt_city" in kb.waypoints
    assert "liyue_harbor" in kb.waypoints
    assert "sumeru_city" in kb.waypoints
    assert "fontaine_court" in kb.waypoints
    assert "natlan_stadium" in kb.waypoints
