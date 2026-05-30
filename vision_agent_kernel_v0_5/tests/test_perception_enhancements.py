"""Tests for enhanced perception capabilities (P-09, P-11, P-18, P-21, P-22, P-27, P-28, P-30)."""
from __future__ import annotations

import pytest

from perception.perception_enhancements import (
    AoEDetection,
    AoEGroundDetector,
    AoEType,
    CharacterStateDetector,
    EnemyTypeClassifier,
    InteractiveObject,
    InteractiveObjectDetector,
    InteractiveObjectType,
    MenuTextReader,
    NumericReading,
    NumericValueReader,
    PopupDetection,
    PopupDetector,
    PopupType,
    QuestMarkerClassifier,
    QuestMarkerDetection,
    QuestMarkerType,
)


# ---------------------------------------------------------------------------
# PopupDetector (P-09)
# ---------------------------------------------------------------------------
class TestPopupDetector:
    def test_achievement_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"has_gold_tint": True, "region": "center"})
        assert result.popup_type == PopupType.ACHIEVEMENT
        assert result.requires_action

    def test_level_up_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"text": "等级提升!", "region": "center"})
        assert result.popup_type == PopupType.LEVEL_UP

    def test_ar_up_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"text": "冒险等阶提升", "region": "center"})
        assert result.popup_type == PopupType.ADVENTURE_RANK_UP

    def test_mail_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"text": "新邮件", "region": "right_edge"})
        assert result.popup_type == PopupType.MAIL

    def test_quest_complete_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"text": "quest complete", "region": "right_edge"})
        assert result.popup_type == PopupType.QUEST_COMPLETE

    def test_unknown_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"text": "something", "region": "left"})
        assert result.popup_type == PopupType.UNKNOWN

    def test_reward_popup(self) -> None:
        det = PopupDetector()
        result = det.classify_popup({"region": "center_bottom"})
        assert result.popup_type == PopupType.REWARD


# ---------------------------------------------------------------------------
# AoEGroundDetector (P-11)
# ---------------------------------------------------------------------------
class TestAoEGroundDetector:
    def test_red_aoe(self) -> None:
        det = AoEGroundDetector()
        result = det.detect_aoe({"hue": 5, "intensity": 0.8, "center": (400, 300)})
        assert result is not None
        assert result.aoe_type == AoEType.RED_CIRCLE
        assert result.danger_level == "high"

    def test_orange_aoe(self) -> None:
        det = AoEGroundDetector()
        result = det.detect_aoe({"hue": 15, "intensity": 0.6})
        assert result is not None
        assert result.aoe_type == AoEType.ORANGE_CIRCLE

    def test_elemental_aoe(self) -> None:
        det = AoEGroundDetector()
        result = det.detect_aoe({"hue": 140, "intensity": 0.7})
        assert result is not None
        assert result.aoe_type == AoEType.ELEMENTAL_ZONE
        assert result.element == "electro"

    def test_low_intensity_none(self) -> None:
        det = AoEGroundDetector()
        assert det.detect_aoe({"hue": 5, "intensity": 0.1}) is None

    def test_empty_data_none(self) -> None:
        det = AoEGroundDetector()
        assert det.detect_aoe({}) is None

    def test_danger_level_critical(self) -> None:
        det = AoEGroundDetector()
        result = det.detect_aoe({"hue": 5, "intensity": 0.9})
        assert result is not None
        assert result.danger_level == "high"


# ---------------------------------------------------------------------------
# QuestMarkerClassifier (P-18)
# ---------------------------------------------------------------------------
class TestQuestMarkerClassifier:
    def test_archon_quest(self) -> None:
        cls = QuestMarkerClassifier()
        result = cls.classify_marker({"hue": 28, "saturation": 220, "value": 230})
        assert result.marker_type == QuestMarkerType.ARCHON_QUEST

    def test_story_quest(self) -> None:
        cls = QuestMarkerClassifier()
        result = cls.classify_marker({"hue": 110, "saturation": 200, "value": 200})
        assert result.marker_type in (QuestMarkerType.STORY_QUEST, QuestMarkerType.WORLD_QUEST)

    def test_event_quest(self) -> None:
        cls = QuestMarkerClassifier()
        result = cls.classify_marker({"hue": 145, "saturation": 200, "value": 200})
        assert result.marker_type == QuestMarkerType.EVENT_QUEST

    def test_unknown_marker(self) -> None:
        cls = QuestMarkerClassifier()
        result = cls.classify_marker({"hue": 200, "saturation": 50, "value": 50})
        assert result.marker_type == QuestMarkerType.UNKNOWN

    def test_marker_distance(self) -> None:
        cls = QuestMarkerClassifier()
        near = cls.classify_marker({"hue": 28, "saturation": 220, "value": 230, "size": 30})
        assert near.distance == "near"


# ---------------------------------------------------------------------------
# NumericValueReader (P-21)
# ---------------------------------------------------------------------------
class TestNumericValueReader:
    def test_parse_simple(self) -> None:
        reader = NumericValueReader()
        result = reader.parse_numeric("1234", "damage")
        assert result is not None
        assert result.value == 1234.0

    def test_parse_percentage(self) -> None:
        reader = NumericValueReader()
        result = reader.parse_numeric("45.6%")
        assert result is not None
        assert result.value == pytest.approx(45.6)

    def test_parse_comma_separated(self) -> None:
        reader = NumericValueReader()
        result = reader.parse_numeric("1,234")
        assert result is not None
        assert result.value == 1234.0

    def test_parse_wan(self) -> None:
        reader = NumericValueReader()
        result = reader.parse_numeric("5万")
        assert result is not None
        assert result.value == 50000.0

    def test_parse_k(self) -> None:
        reader = NumericValueReader()
        result = reader.parse_numeric("10K")
        assert result is not None
        assert result.value == 10000.0

    def test_parse_invalid(self) -> None:
        reader = NumericValueReader()
        assert reader.parse_numeric("abc") is None

    def test_parse_hp_ratio(self) -> None:
        reader = NumericValueReader()
        ratio = reader.parse_hp_ratio("32000/45000")
        assert ratio is not None
        assert ratio == pytest.approx(32000 / 45000)

    def test_parse_hp_ratio_invalid(self) -> None:
        reader = NumericValueReader()
        assert reader.parse_hp_ratio("invalid") is None

    def test_parse_hp_ratio_zero_max(self) -> None:
        reader = NumericValueReader()
        assert reader.parse_hp_ratio("100/0") is None


# ---------------------------------------------------------------------------
# MenuTextReader (P-22)
# ---------------------------------------------------------------------------
class TestMenuTextReader:
    def test_parse_stats(self) -> None:
        reader = MenuTextReader()
        stats = reader.parse_character_stats(["ATK 1234", "HP 32000", "暴击率 65.5%"])
        assert stats.get("atk") == 1234.0
        assert stats.get("hp") == 32000.0
        assert stats.get("crit_rate") == pytest.approx(65.5)

    def test_parse_empty(self) -> None:
        reader = MenuTextReader()
        stats = reader.parse_character_stats([])
        assert len(stats) == 0

    def test_parse_shop_price(self) -> None:
        reader = MenuTextReader()
        result = reader.parse_shop_price("750 星尘")
        assert result.get("stardust") == 750

    def test_parse_shop_price_mora(self) -> None:
        reader = MenuTextReader()
        result = reader.parse_shop_price("10000 摩拉")
        assert result.get("mora") == 10000

    def test_parse_shop_price_unknown(self) -> None:
        reader = MenuTextReader()
        result = reader.parse_shop_price("unknown currency")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# InteractiveObjectDetector (P-27)
# ---------------------------------------------------------------------------
class TestInteractiveObjectDetector:
    def test_chest_detection(self) -> None:
        det = InteractiveObjectDetector()
        obj = det.classify_object({"has_f_prompt": True, "icon_type": "chest"})
        assert obj.object_type == InteractiveObjectType.CHEST

    def test_npc_detection(self) -> None:
        det = InteractiveObjectDetector()
        obj = det.classify_object({"has_f_prompt": True, "shape": "humanoid"})
        assert obj.object_type == InteractiveObjectType.NPC

    def test_material_detection(self) -> None:
        det = InteractiveObjectDetector()
        obj = det.classify_object({"has_f_prompt": True, "icon_type": "material"})
        assert obj.object_type == InteractiveObjectType.MATERIAL

    def test_no_prompt_unknown(self) -> None:
        det = InteractiveObjectDetector()
        obj = det.classify_object({"has_f_prompt": False})
        assert obj.object_type == InteractiveObjectType.UNKNOWN

    def test_teleport_detection(self) -> None:
        det = InteractiveObjectDetector()
        obj = det.classify_object({"has_f_prompt": True, "icon_type": "teleport"})
        assert obj.object_type == InteractiveObjectType.TELEPORT


# ---------------------------------------------------------------------------
# EnemyTypeClassifier (P-28)
# ---------------------------------------------------------------------------
class TestEnemyTypeClassifier:
    def test_slime(self) -> None:
        cls = EnemyTypeClassifier()
        result = cls.classify_enemy({"size": "tiny", "element": "pyro"})
        assert result["kind"] == "slime"
        assert result["element"] == "pyro"

    def test_hilichurl(self) -> None:
        cls = EnemyTypeClassifier()
        result = cls.classify_enemy({"size": "small"})
        assert result["kind"] == "hilichurl"

    def test_boss(self) -> None:
        cls = EnemyTypeClassifier()
        result = cls.classify_enemy({"size": "large", "has_shield": True, "shield_element": "hydro"})
        assert result["kind"] == "boss"
        assert result["is_boss"]
        assert result["has_shield"]

    def test_world_boss(self) -> None:
        cls = EnemyTypeClassifier()
        result = cls.classify_enemy({"size": "giant"})
        assert result["kind"] == "world_boss"
        assert result["is_boss"]
        assert result["is_elite"]

    def test_unknown_size(self) -> None:
        cls = EnemyTypeClassifier()
        result = cls.classify_enemy({"size": "humongous"})
        assert result["kind"] == "unknown"


# ---------------------------------------------------------------------------
# CharacterStateDetector (P-30)
# ---------------------------------------------------------------------------
class TestCharacterStateDetector:
    def test_active_slot(self) -> None:
        det = CharacterStateDetector()
        slots = [
            {"brightness": 0.5},
            {"brightness": 0.9},
            {"brightness": 0.4},
            {"brightness": 0.3},
        ]
        assert det.detect_active_slot(slots) == 1

    def test_empty_slots(self) -> None:
        det = CharacterStateDetector()
        assert det.detect_active_slot([]) == 0

    def test_team_elements(self) -> None:
        det = CharacterStateDetector()
        slots = [
            {"hue": 5},    # pyro
            {"hue": 100},  # hydro
            {"hue": 145},  # electro
            {"hue": 180},  # cryo
        ]
        elements = det.detect_team_elements(slots)
        assert len(elements) == 4
        assert elements[0] == "pyro"

    def test_team_elements_unknown(self) -> None:
        det = CharacterStateDetector()
        slots = [{"hue": 250}]
        elements = det.detect_team_elements(slots)
        assert elements[0] == "unknown"
