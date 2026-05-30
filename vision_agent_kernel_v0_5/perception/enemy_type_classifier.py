"""Enemy type classification for Genshin Impact enemies.

Implements P-35: Enemy Type Classifier
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enemy Type Categories
# ---------------------------------------------------------------------------

class EnemyCategory(Enum):
    HILICHURL = "hilichurl"           # Basic Hilichurl
    HILICHURL_SHOOTER = "hilichurl_shooter"   # Ranged Hilichurl
    HILICHURL_BRUTE = "hilichurl_brute"       # Large Hilichurl
    SAMUWASA = "samuwasa"             # Hilichurl Grenadier/Shooter variant
    HILICHURL_ALCHEMIST = "hilichurl_alchemist"  # Pyro/Cryo Hilichurl


class HilichurlType(Enum):
    """Specific Hilichurl types with visual characteristics."""
    # Hilichurl variants
    MITACHURL = "mitachurl"           # Large, uses shield/axe
    LAWLURL = "lawlurl"               # Hilichurl Berserker
    ALPHA = "hilichurl_alpha"         # Elite Hilichurl with red glow
    CRUEL = "hilichurl_cruel"         # Elite with blue aura

    # Samuwasa (Grenadier)
    SAMUWASA_BLASTER = "samuwasa_blaster"     # Throws explosive barrels
    SAMUWASA_FERRIER = "samuwasa_ferrier"     # Throws fire bombs

    # Shamuwasa (Shaman variants)
    SAMUWASA_SHAMAN = "samuwasa_shaman"       # Any elemental shaman
    PYRO_SAMUWASA = "pyro_shaman"             # Pyro shaman
    CRYO_SAMUWASA = "cryo_shaman"             # Cryo shaman
    ELECTRO_SAMUWASA = "electro_shaman"       # Electro shaman
    HYDRO_SAMUWASA = "hydro_shaman"           # Hydro shaman

    # Abyss Mage
    ABYSS_MAGECRYO = "abyss_mage_cryo"
    ABYSS_MAGE_PYRO = "abyss_mage_pyro"
    ABYSS_MAGE_ELECTRO = "abyss_mage_electro"
    ABYSS_MAGE_HYDRO = "abyss_mage_hydro"
    ABYSS_MAGE_PYRO_ELITE = "abyss_mage_pyro_elite"

    # Fatui
    FATUI_SKIRMISHER = "fatui_skirmisher"
    FATUI_CRYO_CANNONEER = "fatui_cryo_cannoneer"
    FATUI_ELECTRO_CANNONEER = "fatui_electro_cannoneer"
    FATUI_ANEMO_CASTER = "fatui_anemo_caster"
    FATUI_HYDRO_ABYSSAL = "fatui_hydro_abyssal"
    FATUI_GEO_RAPTOR = "fatui_geo_raptor"
    FATUI_CRYO_RAPTOR = "fatui_cryo_raptor"

    # Treasure Hoarders
    TREASURE_HOARDER = "treasure_hoarder"
    TREASURE_HOARDER_RANGED = "treasure_hoarder_ranged"

    # Basic Hilichurl variants
    HILICHURL = "hilichurl"                 # Basic Hilichurl
    HILICHURL_SHOOTER = "hilichurl_shooter"  # Ranged Hilichurl
    HILICHURL_BRUTE = "hilichurl_brute"     # Large brute

    # Unknown
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Enemy Classification Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EnemyClassification:
    enemy_id: int                    # Unique ID for tracking
    enemy_type: HilichurlType
    category: EnemyCategory
    position: tuple[float, float]    # Center position (x, y)
    bounding_box: tuple[int, int, int, int]   # (x, y, w, h)
    confidence: float               # Classification confidence
    size_ratio: float               # Size relative to expected size
    has_shield: bool                # Has visible shield
    has_weapon: bool                # Has visible weapon (bow/club/sword)
    is_elite: bool                  # Is elite enemy
    timestamp: float


@dataclass(frozen=True, slots=True)
class EnemyFieldStatus:
    enemies: tuple[EnemyClassification, ...]
    enemy_count: int
    priority_targets: tuple[EnemyClassification, ...]  # Highest threat
    recommended_action: str
    highest_threat_level: Literal["none", "low", "medium", "high"]


# ---------------------------------------------------------------------------
# Visual Feature Definitions
# ---------------------------------------------------------------------------

# Color ranges in HSV for enemy visual detection
_ENEMY_COLORS: dict[str, tuple[np.ndarray, np.ndarray]] = {
    # Hilichurl mask (brownish/wood)
    "mask_brown": (
        np.array([10, 80, 80]),
        np.array([25, 255, 200]),
    ),
    # Elite hilichurl (red aura)
    "elite_red": (
        np.array([0, 150, 100]),
        np.array([15, 255, 255]),
    ),
    # Abyss mage robe (dark purple)
    "abyss_robe": (
        np.array([130, 50, 20]),
        np.array([170, 150, 100]),
    ),
    # Fatui armor (blue/white)
    "fatui_armor": (
        np.array([90, 30, 100]),
        np.array([130, 150, 255]),
    ),
    # Shaman glow (elemental colored)
    "shaman_pyro": (
        np.array([0, 150, 150]),
        np.array([20, 255, 255]),
    ),
    "shaman_cryo": (
        np.array([85, 100, 150]),
        np.array([115, 255, 255]),
    ),
    "shaman_electro": (
        np.array([120, 150, 150]),
        np.array([160, 255, 255]),
    ),
    # Weapon glint
    "weapon_glint": (
        np.array([0, 0, 200]),
        np.array([180, 50, 255]),
    ),
}


# Size thresholds (relative to 1920x1080 reference)
_SIZE_THRESHOLDS: dict[HilichurlType, tuple[float, float]] = {
    # Very small
    HilichurlType.SAMUWASA_BLASTER: (0.03, 0.08),
    # Small
    HilichurlType.SAMUWASA_SHAMAN: (0.05, 0.12),
    # Medium
    HilichurlType.HILICHURL: (0.08, 0.15),
    HilichurlType.HILICHURL_SHOOTER: (0.08, 0.15),
    HilichurlType.ABYSS_MAGECRYO: (0.10, 0.18),
    # Large
    HilichurlType.MITACHURL: (0.18, 0.30),
    HilichurlType.LAWLURL: (0.15, 0.25),
    HilichurlType.HILICHURL_BRUTE: (0.18, 0.30),
    # Elite markers add size
    HilichurlType.ALPHA: (0.10, 0.18),
}


# ---------------------------------------------------------------------------
# P-35: Enemy Type Classifier
# ---------------------------------------------------------------------------

class EnemyTypeClassifier:
    """Classifies enemy types based on visual characteristics.

    Features:
    - Detects Hilichurl variants (Basic, Shooter, Brute, Berserker)
    - Identifies Shamans (Pyro, Cryo, Electro, Hydro)
    - Recognizes Abyss Mages
    - Detects Fatui enemies
    - Tracks elite enemies with special auras
    - Estimates threat level based on type and count

    Visual analysis:
    - Body shape and size
    - Weapon type (club, bow, staff)
    - Elemental aura (colored glow)
    - Shield presence
    - Elite markers (aura color)
    """

    _REF_W = 1920
    _REF_H = 1080

    # Classification thresholds
    MIN_DETECTION_SIZE = 20     # Minimum pixel size
    MASK_HISTORY_FRAMES = 5     # Frames to track for ID

    # Threat levels by enemy type
    THREAT_LEVELS: dict[HilichurlType, int] = {
        HilichurlType.HILICHURL: 1,
        HilichurlType.HILICHURL_SHOOTER: 2,
        HilichurlType.MITACHURL: 3,
        HilichurlType.LAWLURL: 3,
        HilichurlType.ALPHA: 4,
        HilichurlType.SAMUWASA_SHAMAN: 4,
        HilichurlType.PYRO_SAMUWASA: 5,
        HilichurlType.CRYO_SAMUWASA: 5,
        HilichurlType.ELECTRO_SAMUWASA: 5,
        HilichurlType.ABYSS_MAGECRYO: 6,
        HilichurlType.ABYSS_MAGE_PYRO: 6,
        HilichurlType.ABYSS_MAGE_ELECTRO: 6,
        HilichurlType.FATUI_SKIRMISHER: 3,
        HilichurlType.FATUI_CRYO_CANNONEER: 5,
        HilichurlType.FATUI_ELECTRO_CANNONEER: 5,
        HilichurlType.UNKNOWN: 2,
    }

    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or time.perf_counter
        self._enemy_ids: dict[int, EnemyClassification] = {}
        self._next_enemy_id = 0
        self._last_classifications: list[EnemyClassification] = []
        self._last_result: EnemyFieldStatus | None = None

    @property
    def last_result(self) -> EnemyFieldStatus | None:
        return self._last_result

    @property
    def enemies(self) -> tuple[EnemyClassification, ...]:
        return tuple(self._last_classifications)

    def classify(
        self,
        frame: np.ndarray,
        frame_id: int,
        detections: list[tuple[int, int, int, int]] | None = None,
    ) -> EnemyFieldStatus:
        """Classify enemy types from detections.

        Args:
            frame: BGR frame from screen capture.
            frame_id: Current frame ID.
            detections: Optional list of bounding boxes (x, y, w, h).
                       If None, performs full scan.

        Returns:
            EnemyFieldStatus with classified enemies.
        """
        if cv2 is None or frame.size == 0:
            return EnemyFieldStatus((), 0, (), "continue", "none")

        now = self._now_fn()
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        if detections is None:
            detections = self._full_scan(hsv, sx, sy)

        classifications: list[EnemyClassification] = []

        for bbox in detections:
            x, y, bw, bh = bbox
            size_ratio = (bw * bh) / (w * h)

            # Skip tiny detections
            if bw < self.MIN_DETECTION_SIZE or bh < self.MIN_DETECTION_SIZE:
                continue

            # Analyze region
            roi = frame[y:y+bh, x:x+bw]
            if roi.size == 0:
                continue

            roi_hsv = hsv[y:y+bh, x:x+bw]

            # Classify based on visual features
            classification = self._classify_region(
                bbox, roi, roi_hsv, size_ratio, sx, sy, now
            )
            classifications.append(classification)

        # Assign IDs based on position matching
        self._assign_ids(classifications)

        self._last_classifications = classifications
        self._last_result = self._build_status(classifications)

        return self._last_result

    def _full_scan(
        self,
        hsv: np.ndarray,
        sx: float,
        sy: float,
    ) -> list[tuple[int, int, int, int]]:
        """Perform full frame scan for enemy-like shapes."""
        detections: list[tuple[int, int, int, int]] = []

        # Scan for hilichurl mask color
        lower, upper = _ENEMY_COLORS["mask_brown"]
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3)))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 500:
                continue

            x, y, bw, bh = cv2.boundingRect(contour)
            detections.append((x, y, bw, bh))

        return detections

    def _classify_region(
        self,
        bbox: tuple[int, int, int, int],
        roi: np.ndarray,
        roi_hsv: np.ndarray,
        size_ratio: float,
        sx: float,
        sy: float,
        now: float,
    ) -> EnemyClassification:
        """Classify a single enemy region."""
        x, y, bw, bh = bbox

        # Detect elemental aura
        has_elemental = False
        elemental_color = ""

        for color_name, (lower, upper) in _ENEMY_COLORS.items():
            if "shaman" in color_name or color_name.startswith("shaman_"):
                mask = cv2.inRange(roi_hsv, lower, upper)
                if cv2.countNonZero(mask) > 50:
                    has_elemental = True
                    elemental_color = color_name
                    break

        # Detect shield (typically on left side, darker)
        has_shield = self._detect_shield(roi_hsv)

        # Detect weapon
        has_weapon = self._detect_weapon(roi_hsv, bw, bh)

        # Detect elite aura (red glow)
        is_elite = self._detect_elite_aura(roi_hsv)

        # Determine enemy type
        enemy_type = self._determine_enemy_type(
            size_ratio, has_elemental, elemental_color,
            has_shield, has_weapon, is_elite, bw, bh, sx, sy
        )

        # Calculate position and bounding box
        cx = x + bw // 2
        cy = y + bh // 2

        confidence = 0.7 if is_elite else 0.6  # Simplified confidence

        return EnemyClassification(
            enemy_id=-1,  # Will be assigned
            enemy_type=enemy_type,
            category=self._type_to_category(enemy_type),
            position=(float(cx), float(cy)),
            bounding_box=bbox,
            confidence=confidence,
            size_ratio=size_ratio,
            has_shield=has_shield,
            has_weapon=has_weapon,
            is_elite=is_elite,
            timestamp=now,
        )

    def _detect_shield(self, roi_hsv: np.ndarray) -> bool:
        """Detect if enemy has a shield."""
        # Shield is typically darker with wood/brown color
        shield_mask = cv2.inRange(roi_hsv, np.array([10, 50, 50]), np.array([25, 200, 200]))
        shield_ratio = cv2.countNonZero(shield_mask) / max(shield_mask.size, 1)
        return shield_ratio > 0.1

    def _detect_weapon(self, roi_hsv: np.ndarray, bw: int, bh: int) -> bool:
        """Detect if enemy has a weapon (glint detection)."""
        # Weapon glint is typically white/bright
        glint_mask = cv2.inRange(roi_hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        glint_ratio = cv2.countNonZero(glint_mask) / max(glint_mask.size, 1)
        return glint_ratio > 0.01

    def _detect_elite_aura(self, roi_hsv: np.ndarray) -> bool:
        """Detect elite enemy aura (red glow)."""
        elite_mask = cv2.inRange(roi_hsv, _ENEMY_COLORS["elite_red"][0], _ENEMY_COLORS["elite_red"][1])
        elite_ratio = cv2.countNonZero(elite_mask) / max(elite_mask.size, 1)
        return elite_ratio > 0.05

    def _determine_enemy_type(
        self,
        size_ratio: float,
        has_elemental: bool,
        elemental_color: str,
        has_shield: bool,
        has_weapon: bool,
        is_elite: bool,
        bw: int,
        bh: int,
        sx: float,
        sy: float,
    ) -> HilichurlType:
        """Determine enemy type from features."""
        # Check for elemental shaman first
        if has_elemental:
            if "cryo" in elemental_color:
                return HilichurlType.CRYO_SAMUWASA
            elif "pyro" in elemental_color:
                return HilichurlType.PYRO_SAMUWASA
            elif "electro" in elemental_color:
                return HilichurlType.ELECTRO_SAMUWASA
            else:
                return HilichurlType.SAMUWASA_SHAMAN

        # Check size categories
        # Very large = Mitachurl (axe/shield)
        if size_ratio > 0.15 and (has_shield or bw > bh):
            return HilichurlType.MITACHURL

        # Abyss mage detection (dark robe, distinct shape)
        # (Would need more specific detection logic)

        # Large with weapon = could be brute
        if size_ratio > 0.12 and has_weapon:
            return HilichurlType.MITACHURL

        # Elite detection
        if is_elite:
            return HilichurlType.HILICHURL_ALPHA

        # Basic hilichurl
        if has_weapon and size_ratio < 0.10:
            return HilichurlType.HILICHURL_SHOOTER

        return HilichurlType.HILICHURL

    def _type_to_category(self, enemy_type: HilichurlType) -> EnemyCategory:
        """Map enemy type to category."""
        name = enemy_type.value
        if "samuwasa" in name or "shaman" in name:
            return EnemyCategory.HILICHURL_ALCHEMIST
        elif "shooter" in name:
            return EnemyCategory.HILICHURL_SHOOTER
        elif "mitachurl" in name or "brute" in name:
            return EnemyCategory.HILICHURL_BRUTE
        elif "abyss" in name:
            return EnemyCategory.HILICHURL  # Simplified
        else:
            return EnemyCategory.HILICHURL

    def _assign_ids(self, classifications: list[EnemyClassification]) -> None:
        """Assign IDs based on position matching."""
        id_assignments: dict[int, int] = {}  # old_id -> new_id
        new_id_by_position: dict[tuple[int, int], int] = {}

        for i, classification in enumerate(classifications):
            cx, cy = int(classification.position[0]), int(classification.position[1])

            # Check if this matches an existing tracked enemy
            best_match = None
            best_dist = 50  # Max distance for match

            for old_id, old_class in self._enemy_ids.items():
                if old_id in id_assignments:
                    continue
                ox, oy = int(old_class.position[0]), int(old_class.position[1])
                dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_match = old_id

            if best_match is not None:
                id_assignments[best_match] = best_match
                object.__setattr__(classification, 'enemy_id', best_match)
            else:
                new_id = self._next_enemy_id
                self._next_enemy_id += 1
                id_assignments[new_id] = new_id
                object.__setattr__(classification, 'enemy_id', new_id)

        # Update tracking
        self._enemy_ids.clear()
        for c in classifications:
            self._enemy_ids[c.enemy_id] = c

    def _build_status(self, classifications: list[EnemyClassification]) -> EnemyFieldStatus:
        """Build enemy field status."""
        # Sort by threat level
        threat_sorted = sorted(
            classifications,
            key=lambda c: self.THREAT_LEVELS.get(c.enemy_type, 0),
            reverse=True,
        )

        # Get priority targets (top 3 threats)
        priority = tuple(threat_sorted[:3])

        # Calculate overall threat level
        max_threat = max(
            (self.THREAT_LEVELS.get(c.enemy_type, 0) for c in classifications),
            default=0,
        )
        threat_level: Literal["none", "low", "medium", "high"] = "none"
        if max_threat >= 5:
            threat_level = "high"
        elif max_threat >= 3:
            threat_level = "medium"
        elif max_threat > 0:
            threat_level = "low"

        # Determine recommended action
        if threat_level == "high":
            action = "focus_priority"
        elif threat_level == "medium":
            action = "clear_threats"
        else:
            action = "continue"

        return EnemyFieldStatus(
            enemies=tuple(classifications),
            enemy_count=len(classifications),
            priority_targets=priority,
            recommended_action=action,
            highest_threat_level=threat_level,
        )

    def get_enemies_by_type(self, enemy_type: HilichurlType) -> list[EnemyClassification]:
        """Get all enemies of a specific type."""
        return [c for c in self._last_classifications if c.enemy_type == enemy_type]

    def get_elite_count(self) -> int:
        """Count elite enemies in current frame."""
        return sum(1 for c in self._last_classifications if c.is_elite)

    def get_threat_count(self, min_threat: int = 3) -> int:
        """Count enemies at or above a threat level."""
        return sum(
            1 for c in self._last_classifications
            if self.THREAT_LEVELS.get(c.enemy_type, 0) >= min_threat
        )

    def reset(self) -> None:
        """Reset classifier state."""
        self._enemy_ids.clear()
        self._last_classifications.clear()
        self._last_result = None