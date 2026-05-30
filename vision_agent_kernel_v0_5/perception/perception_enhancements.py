"""Enhanced perception capabilities for remaining partial items.

Covers:
- P-09: Popup/notification detection enhancement (achievement, level-up, mail)
- P-11: AoE ground indicator detection (red/orange circles for incoming attacks)
- P-18: Quest marker color differentiation (gold=Archon, blue=Story/World)
- P-21: Numeric value reading (damage numbers, HP values, resource counts)
- P-22: Menu text OCR enhancement (character stats, material quantities, shop prices)
- P-27: Interactive object identification (NPCs, items, mechanisms)
- P-28: Enemy type identification (enemy kind, element, shield type)
- P-30: Character current state identification (active character, team config)

Integrates with:
- perception/genshin_screen_classifier.py for HSV-based detection
- perception/genshin_visual_detectors.py for visual element detection
- perception/advanced_perception.py for OCR result types
- combat/danger_detector.py for ground danger signals
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P-09: Popup/Notification Detection Enhancement
# ---------------------------------------------------------------------------

class PopupType(str, Enum):
    """Types of game popups/notifications."""
    ACHIEVEMENT = "achievement"
    LEVEL_UP = "level_up"
    ADVENTURE_RANK_UP = "adventure_rank_up"
    MAIL = "mail"
    QUEST_COMPLETE = "quest_complete"
    REWARD = "reward"
    SYSTEM_NOTICE = "system_notice"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PopupDetection:
    """Detected popup/notification."""
    popup_type: PopupType
    position: tuple[int, int] = (0, 0)
    confidence: float = 0.0
    text: str = ""
    requires_action: bool = False  # True if needs click/dismiss


class PopupDetector:
    """Enhanced popup/notification detection (P-09).

    Builds on genshin_screen_classifier._detect_notification() with
    type-specific detection and action requirements.
    """

    def classify_popup(self, notification_data: dict) -> PopupDetection:
        """Classify a detected notification into a specific popup type.

        Args:
            notification_data: Dict from screen classifier with position,
                             color info, and screen region data.
        """
        region = notification_data.get("region", "")
        has_gold = notification_data.get("has_gold_tint", False)
        has_icon = notification_data.get("has_icon", False)
        text_hint = notification_data.get("text", "")

        popup_type = PopupType.UNKNOWN

        if has_gold:
            popup_type = PopupType.ACHIEVEMENT
        elif "rank" in text_hint.lower() or "冒险等阶" in text_hint:
            popup_type = PopupType.ADVENTURE_RANK_UP
        elif "level" in text_hint.lower() or "等级" in text_hint:
            popup_type = PopupType.LEVEL_UP
        elif "mail" in text_hint.lower() or "邮件" in text_hint:
            popup_type = PopupType.MAIL
        elif "quest" in text_hint.lower() or "任务" in text_hint:
            popup_type = PopupType.QUEST_COMPLETE
        elif region == "center_bottom":
            popup_type = PopupType.REWARD

        requires_action = popup_type in (
            PopupType.ACHIEVEMENT, PopupType.LEVEL_UP,
            PopupType.ADVENTURE_RANK_UP, PopupType.REWARD,
        )

        return PopupDetection(
            popup_type=popup_type,
            position=notification_data.get("position", (0, 0)),
            confidence=notification_data.get("confidence", 0.5),
            text=text_hint,
            requires_action=requires_action,
        )


# ---------------------------------------------------------------------------
# P-11: AoE Ground Indicator Detection Enhancement
# ---------------------------------------------------------------------------

class AoEType(str, Enum):
    """Types of AoE ground indicators."""
    RED_CIRCLE = "red_circle"           # Incoming AoE attack
    ORANGE_CIRCLE = "orange_circle"     # Warning zone
    ELEMENTAL_ZONE = "elemental_zone"   # Elemental effect area (Pyro, Cryo, etc.)
    SAFE_ZONE = "safe_zone"             # Blue/green safe area
    UNKNOWN = "unknown"


@dataclass(slots=True)
class AoEDetection:
    """Detected AoE ground indicator."""
    aoe_type: AoEType
    center: tuple[int, int] = (0, 0)
    radius: int = 0
    time_remaining_ms: int = 0  # Estimated time before impact
    element: str = ""
    danger_level: str = "medium"  # "low", "medium", "high", "critical"


class AoEGroundDetector:
    """Enhanced AoE ground indicator detection (P-11).

    Extends danger_detector._detect_ground_danger() with type classification,
    timing estimation, and element-specific detection.
    """

    # HSV ranges for AoE types
    _RED_AOE_HSV = ((0, 150, 100), (10, 255, 255))
    _ORANGE_AOE_HSV = ((10, 150, 100), (25, 255, 255))
    _ELEMENTAL_HSV: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        "pyro": ((10, 150, 150), (20, 255, 255)),    # Avoids red circle overlap
        "cryo": ((85, 50, 150), (110, 200, 255)),
        "electro": ((130, 100, 100), (160, 255, 255)),
        "hydro": ((95, 100, 100), (130, 255, 255)),
    }

    def detect_aoe(self, ground_danger_data: dict) -> AoEDetection | None:
        """Detect and classify an AoE ground indicator.

        Args:
            ground_danger_data: Dict from danger_detector with position,
                               color, intensity data.
        """
        if not ground_danger_data:
            return None

        hue = ground_danger_data.get("hue", 0)
        intensity = ground_danger_data.get("intensity", 0)

        if intensity < 0.3:
            return None

        aoe_type = AoEType.UNKNOWN
        element = ""
        if 0 <= hue <= 10:
            aoe_type = AoEType.RED_CIRCLE
        elif 10 < hue <= 25:
            aoe_type = AoEType.ORANGE_CIRCLE
        else:
            for elem, (low, high) in self._ELEMENTAL_HSV.items():
                if low[0] <= hue <= high[0]:
                    aoe_type = AoEType.ELEMENTAL_ZONE
                    element = elem
                    break

        danger_level = "high" if intensity > 0.7 else "medium" if intensity > 0.5 else "low"

        return AoEDetection(
            aoe_type=aoe_type,
            center=ground_danger_data.get("center", (0, 0)),
            radius=ground_danger_data.get("radius", 0),
            element=element,
            danger_level=danger_level,
        )


# ---------------------------------------------------------------------------
# P-18: Quest Marker Color Differentiation
# ---------------------------------------------------------------------------

class QuestMarkerType(str, Enum):
    """Quest marker types by color."""
    ARCHON_QUEST = "archon_quest"       # Gold/Yellow — main storyline
    STORY_QUEST = "story_quest"         # Blue — character story quests
    WORLD_QUEST = "world_quest"         # Blue — world quests
    DAILY_COMMISSION = "daily"          # Blue — daily commissions
    HIDDEN_QUEST = "hidden_quest"       # Gray — untracked
    EVENT_QUEST = "event_quest"         # Purple — event quests
    UNKNOWN = "unknown"


@dataclass(slots=True)
class QuestMarkerDetection:
    """Detected quest marker on minimap or screen."""
    marker_type: QuestMarkerType
    position: tuple[int, int] = (0, 0)
    direction: float = 0.0  # Angle in degrees from character
    distance: str = "medium"  # "near", "medium", "far"


class QuestMarkerClassifier:
    """Classifies quest markers by color (P-18).

    Differentiates Archon (gold) from Story/World (blue) from Event (purple)
    quest markers using HSV color analysis.
    """

    # Quest marker color ranges (HSV)
    _MARKER_COLORS: dict[QuestMarkerType, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        QuestMarkerType.ARCHON_QUEST: ((20, 200, 200), (35, 255, 255)),     # Gold
        # STORY_QUEST and WORLD_QUEST share blue hue range; first match wins
        QuestMarkerType.STORY_QUEST: ((100, 150, 150), (120, 255, 255)),    # Blue
        QuestMarkerType.WORLD_QUEST: ((100, 150, 150), (120, 255, 255)),    # Blue
        QuestMarkerType.EVENT_QUEST: ((130, 150, 150), (160, 255, 255)),    # Purple
    }

    def classify_marker(self, marker_data: dict) -> QuestMarkerDetection:
        """Classify a detected quest marker by its color.

        Args:
            marker_data: Dict with hue, saturation, value, position, direction.
        """
        hue = marker_data.get("hue", 0)
        sat = marker_data.get("saturation", 0)
        val = marker_data.get("value", 0)

        marker_type = QuestMarkerType.UNKNOWN
        best_match = 0.0

        for mtype, (low, high) in self._MARKER_COLORS.items():
            if low[0] <= hue <= high[0] and sat >= low[1] and val >= low[2]:
                match_score = sat / 255.0
                if match_score > best_match:
                    best_match = match_score
                    marker_type = mtype

        direction = marker_data.get("direction", 0.0)
        distance = "near" if marker_data.get("size", 0) > 20 else "medium"

        return QuestMarkerDetection(
            marker_type=marker_type,
            position=marker_data.get("position", (0, 0)),
            direction=direction,
            distance=distance,
        )


# ---------------------------------------------------------------------------
# P-21/P-22: Numeric Reading + Menu Text OCR Enhancement
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class NumericReading:
    """A read numeric value from the screen."""
    value: float
    raw_text: str = ""
    value_type: str = ""  # "damage", "hp", "resource", "stat"
    position: tuple[int, int] = (0, 0)
    confidence: float = 0.0


class NumericValueReader:
    """Reads numeric values from screen text (P-21)."""

    _DAMAGE_COLORS: dict[str, tuple[int, int, int]] = {
        "normal": (255, 255, 255),    # White
        "critical": (255, 200, 50),   # Gold
        "elemental": (100, 200, 255), # Blue
        "heal": (100, 255, 100),      # Green
    }

    def parse_numeric(self, text: str,
                      value_type: str = "") -> NumericReading | None:
        """Parse a numeric value from OCR text.

        Handles comma-separated numbers, percentages, and suffixed values.
        """
        original = text.strip()
        text = original.replace(",", "").replace("，", "")

        # Remove common suffixes
        suffix = ""
        for s in ["%", "万", "K", "k", "M", "m"]:
            if text.endswith(s):
                suffix = s
                text = text[:-1]
                break

        try:
            value = float(text)
        except ValueError:
            return None

        # Apply suffix multiplier
        if suffix == "万":
            value *= 10000
        elif suffix in ("K", "k"):
            value *= 1000
        elif suffix in ("M", "m"):
            value *= 1000000

        return NumericReading(
            value=value,
            raw_text=original,
            value_type=value_type,
        )

    def parse_hp_ratio(self, hp_text: str) -> float | None:
        """Parse HP ratio from text like '32000/45000'."""
        if "/" not in hp_text:
            return None
        parts = hp_text.split("/")
        if len(parts) != 2:
            return None
        try:
            current = float(parts[0].strip().replace(",", ""))
            maximum = float(parts[1].strip().replace(",", ""))
            if maximum <= 0:
                return None
            return current / maximum
        except (ValueError, ZeroDivisionError):
            return None


class MenuTextReader:
    """Enhanced menu text reading (P-22).

    Provides structured parsing for character stats, material quantities,
    shop prices, and other menu text.
    """

    def parse_character_stats(self, stat_texts: list[str]) -> dict[str, float]:
        """Parse character stat text into a stat dictionary."""
        stats: dict[str, float] = {}
        _STAT_NAMES = {
            "HP": "hp", "ATK": "atk", "DEF": "def",
            "EM": "elemental_mastery", "ER": "energy_recharge",
            "CR": "crit_rate", "CD": "crit_damage",
            "生命": "hp", "攻击": "atk", "防御": "def",
            "元素精通": "elemental_mastery",
            "暴击率": "crit_rate", "暴击伤害": "crit_damage",
        }
        for text in stat_texts:
            for name, key in _STAT_NAMES.items():
                if name in text:
                    # Extract numeric value after the stat name
                    parts = text.split()
                    for part in reversed(parts):
                        try:
                            val = float(part.replace("%", "").replace(",", ""))
                            stats[key] = val
                            break
                        except ValueError:
                            continue
        return stats

    def parse_shop_price(self, price_text: str) -> dict[str, int]:
        """Parse shop price text like '750 星尘' into {currency: amount}."""
        price_text = price_text.strip()
        _CURRENCIES = {
            "摩拉": "mora", "原石": "primogem", "星尘": "stardust",
            "星辉": "starglitter", "纠缠之缘": "intertwined_fate",
            "相遇之缘": "acquaint_fate",
        }
        for cn_name, en_name in _CURRENCIES.items():
            if cn_name in price_text:
                num_part = price_text.replace(cn_name, "").strip()
                try:
                    return {en_name: int(num_part.replace(",", ""))}
                except ValueError:
                    return {en_name: 0}
        return {}


# ---------------------------------------------------------------------------
# P-27/P-28/P-30: Object/Enemy/Character Identification
# ---------------------------------------------------------------------------

class InteractiveObjectType(str, Enum):
    """Types of interactive objects in the game world."""
    NPC = "npc"
    CHEST = "chest"
    MATERIAL = "material"
    TELEPORT = "teleport"
    STATUE = "statue"
    DOMAIN = "domain"
    MECHANISM = "mechanism"
    FORGE = "forge"
    COOKING = "cooking"
    SHOP = "shop"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class InteractiveObject:
    """Detected interactive object."""
    object_type: InteractiveObjectType
    position: tuple[int, int] = (0, 0)
    name: str = ""
    interaction_key: str = "F"
    element: str = ""
    confidence: float = 0.0


class InteractiveObjectDetector:
    """Identifies interactive objects in the game world (P-27).

    Uses visual cues (F-key prompt, object shape, element icon) to classify
    objects the player can interact with.
    """

    def classify_object(self, object_data: dict) -> InteractiveObject:
        """Classify an interactive object from detection data.

        Args:
            object_data: Dict with type hints, position, visual features.
        """
        obj_type = InteractiveObjectType.UNKNOWN

        has_f_prompt = object_data.get("has_f_prompt", False)
        shape = object_data.get("shape", "")
        element = object_data.get("element", "")
        icon_type = object_data.get("icon_type", "")

        if not has_f_prompt:
            return InteractiveObject(object_type=obj_type)

        if icon_type == "chest":
            obj_type = InteractiveObjectType.CHEST
        elif icon_type == "npc" or shape == "humanoid":
            obj_type = InteractiveObjectType.NPC
        elif icon_type == "material" or shape == "small":
            obj_type = InteractiveObjectType.MATERIAL
        elif icon_type == "teleport":
            obj_type = InteractiveObjectType.TELEPORT
        elif icon_type == "statue":
            obj_type = InteractiveObjectType.STATUE
        elif icon_type == "domain":
            obj_type = InteractiveObjectType.DOMAIN
        elif shape == "mechanism":
            obj_type = InteractiveObjectType.MECHANISM

        return InteractiveObject(
            object_type=obj_type,
            position=object_data.get("position", (0, 0)),
            element=element,
            confidence=object_data.get("confidence", 0.5),
        )


class EnemyTypeClassifier:
    """Classifies enemy types from visual detection (P-28).

    Identifies enemy kind (Slime, Hilichurl, Boss, etc.), element,
    and shield type from visual features.
    """

    _ENEMY_SIZE_MAP: dict[str, str] = {
        "tiny": "slime",
        "small": "hilichurl",
        "medium": "mitachurl",
        "large": "boss",
        "giant": "world_boss",
    }

    def classify_enemy(self, enemy_data: dict) -> dict[str, str]:
        """Classify an enemy from detection data.

        Args:
            enemy_data: Dict with size, element, shield info, visual features.
        """
        size = enemy_data.get("size", "medium")
        element = enemy_data.get("element", "")
        has_shield = enemy_data.get("has_shield", False)
        shield_element = enemy_data.get("shield_element", "")

        enemy_kind = self._ENEMY_SIZE_MAP.get(size, "unknown")

        result = {
            "kind": enemy_kind,
            "element": element,
            "has_shield": has_shield,
            "shield_element": shield_element,
            "is_boss": enemy_kind in ("boss", "world_boss"),
            "is_elite": enemy_kind in ("mitachurl", "boss", "world_boss"),
        }

        return result


class CharacterStateDetector:
    """Detects current character state from screen (P-30).

    Identifies the active character, team configuration, and character states.
    """

    # Party slot positions (normalized)
    _PARTY_SLOT_X: list[float] = [0.02, 0.06, 0.10, 0.14]
    _PARTY_SLOT_Y: float = 0.92

    def detect_active_slot(self, slot_data: list[dict]) -> int:
        """Detect which character slot is currently active.

        Active slot is brighter/larger than others.

        Args:
            slot_data: List of 4 dicts, one per slot, with brightness info.
        """
        if not slot_data:
            return 0

        best_idx = 0
        best_brightness = 0.0
        for i, slot in enumerate(slot_data):
            brightness = slot.get("brightness", 0.0)
            if brightness > best_brightness:
                best_brightness = brightness
                best_idx = i
        return best_idx

    def detect_team_elements(self, slot_data: list[dict]) -> list[str]:
        """Detect team element composition from party slots.

        Args:
            slot_data: List of 4 dicts with element color info.
        """
        _ELEMENT_BY_HUE: dict[tuple[int, int], str] = {
            (0, 15): "pyro",
            (15, 35): "geo",
            (35, 75): "dendro",
            (75, 100): "anemo",
            (100, 130): "hydro",
            (130, 160): "electro",
            (185, 210): "cryo",
        }

        elements: list[str] = []
        for slot in slot_data:
            hue = slot.get("hue", 0)
            detected = ""
            for (low, high), element in _ELEMENT_BY_HUE.items():
                if low <= hue <= high:
                    detected = element
                    break
            elements.append(detected or "unknown")

        return elements
