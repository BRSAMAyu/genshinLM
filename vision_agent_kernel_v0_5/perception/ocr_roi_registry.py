from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from perception.ocr_base import OcrResult

log = logging.getLogger(__name__)

__all__ = [
    "OcrPurpose",
    "GameScene",
    "OcrRoiSpec",
    "GameSceneOcrRegistry",
    "OcrTargetedScanner",
]


class OcrPurpose(str, Enum):
    """What we want to read from a specific screen region."""
    RESIN_COUNT = "resin_count"
    MORA_COUNT = "mora_count"
    PRIMOGEM_COUNT = "primogem_count"
    ADVENTURE_RANK = "adventure_rank"
    HP_BAR = "hp_bar"
    STAMINA_BAR = "stamina_bar"
    QUEST_TEXT = "quest_text"
    QUEST_OBJECTIVE = "quest_objective"
    INTERACTION_PROMPT = "interaction_prompt"
    DIALOG_TEXT = "dialog_text"
    DIALOG_OPTION = "dialog_option"
    LOADING_TIP = "loading_tip"
    TIMER_COUNTDOWN = "timer_countdown"
    ITEM_COUNT = "item_count"
    CHARACTER_LEVEL = "character_level"
    SKILL_COOLDOWN = "skill_cooldown"
    BOSS_HP = "boss_hp"
    MINIMAP_QUEST_ANGLE = "minimap_quest_angle"
    NOTIFICATION_TEXT = "notification_text"
    SHOP_PRICE = "shop_price"
    ARTIFACT_MAIN_STAT = "artifact_main_stat"
    TALENT_LEVEL = "talent_level"
    COMMISSION_REWARD = "commission_reward"
    DOMAIN_REWARD = "domain_reward"
    GENERIC_NUMBER = "generic_number"
    GENERIC_TEXT = "generic_text"


class GameScene(str, Enum):
    """High-level game screen states that determine which ROIs to scan."""
    OVERWORLD = "overworld"
    COMBAT = "combat"
    MENU = "menu"
    DIALOG = "dialog"
    LOADING = "loading"
    MAP = "map"
    INVENTORY = "inventory"
    CHARACTER_SCREEN = "character_screen"
    SHOP = "shop"
    CRAFTING = "crafting"
    DOMAIN = "domain"
    WISH = "wish"
    NOTIFICATION = "notification"
    QUEST_LOG = "quest_log"
    PARTY_SETUP = "party_setup"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OcrRoiSpec:
    """A targeted OCR region specification.

    All coordinates are normalized (0.0-1.0) relative to the full frame,
    resolution-independent. Converted to pixels at scan time.
    """
    roi_id: str
    purpose: OcrPurpose
    x_norm: float
    y_norm: float
    w_norm: float
    h_norm: float
    scenes: tuple[GameScene, ...]
    priority: int = 50  # lower = scanned first
    fallback_full_scan: bool = False
    description: str = ""

    def to_pixel_roi(self, frame_h: int, frame_w: int) -> tuple[int, int, int, int]:
        x1 = int(self.x_norm * frame_w)
        y1 = int(self.y_norm * frame_h)
        x2 = int((self.x_norm + self.w_norm) * frame_w)
        y2 = int((self.y_norm + self.h_norm) * frame_h)
        return (max(0, x1), max(0, y1), min(frame_w, x2), min(frame_h, y2))


def _spec(
    roi_id: str,
    purpose: OcrPurpose,
    x: float,
    y: float,
    w: float,
    h: float,
    scenes: tuple[GameScene, ...],
    priority: int = 50,
    fallback_full_scan: bool = False,
    description: str = "",
) -> OcrRoiSpec:
    return OcrRoiSpec(
        roi_id=roi_id,
        purpose=purpose,
        x_norm=x,
        y_norm=y,
        w_norm=w,
        h_norm=h,
        scenes=scenes,
        priority=priority,
        fallback_full_scan=fallback_full_scan,
        description=description,
    )


# ---------------------------------------------------------------------------
# Built-in ROI definitions for Genshin Impact at 1920x1080 reference
# ---------------------------------------------------------------------------

_OVERWORLD_ROIS: list[OcrRoiSpec] = [
    _spec("ow_minimap_quest", OcrPurpose.MINIMAP_QUEST_ANGLE, 0.00, 0.00, 0.17, 0.22,
          (GameScene.OVERWORLD,), priority=10, description="Minimap quest marker direction"),
    _spec("ow_quest_objective", OcrPurpose.QUEST_OBJECTIVE, 0.30, 0.00, 0.40, 0.06,
          (GameScene.OVERWORLD, GameScene.COMBAT), priority=15,
          description="Top-center quest objective text"),
    _spec("ow_interaction_prompt", OcrPurpose.INTERACTION_PROMPT, 0.35, 0.55, 0.30, 0.08,
          (GameScene.OVERWORLD,), priority=10,
          description="Center interaction prompt (F to talk/open/interact)"),
    _spec("ow_hp_bar", OcrPurpose.HP_BAR, 0.30, 0.88, 0.40, 0.05,
          (GameScene.OVERWORLD, GameScene.COMBAT), priority=20,
          description="Active character HP bar region"),
    _spec("ow_stamina", OcrPurpose.STAMINA_BAR, 0.88, 0.35, 0.10, 0.35,
          (GameScene.OVERWORLD,), priority=25, description="Stamina bar right side"),
]

_COMBAT_ROIS: list[OcrRoiSpec] = [
    _spec("cb_boss_hp", OcrPurpose.BOSS_HP, 0.15, 0.02, 0.70, 0.04,
          (GameScene.COMBAT,), priority=5, description="Boss/enemy HP bar top of screen"),
    _spec("cb_character_hp", OcrPurpose.HP_BAR, 0.25, 0.85, 0.50, 0.08,
          (GameScene.COMBAT,), priority=15, description="Party HP bars bottom"),
    _spec("cb_skill_cd", OcrPurpose.SKILL_COOLDOWN, 0.58, 0.88, 0.20, 0.08,
          (GameScene.COMBAT,), priority=20, description="Skill cooldown numbers"),
    _spec("cb_quest_obj", OcrPurpose.QUEST_OBJECTIVE, 0.30, 0.00, 0.40, 0.06,
          (GameScene.COMBAT,), priority=15, description="Quest objective in combat"),
]

_MENU_ROIS: list[OcrRoiSpec] = [
    _spec("mu_resin", OcrPurpose.RESIN_COUNT, 0.82, 0.01, 0.15, 0.04,
          (GameScene.MENU, GameScene.DOMAIN, GameScene.MAP),
          priority=5, description="Resin count top-right"),
    _spec("mu_mora", OcrPurpose.MORA_COUNT, 0.55, 0.01, 0.15, 0.04,
          (GameScene.MENU, GameScene.SHOP, GameScene.INVENTORY),
          priority=10, description="Mora count top area"),
    _spec("mu_primogem", OcrPurpose.PRIMOGEM_COUNT, 0.70, 0.01, 0.10, 0.04,
          (GameScene.MENU, GameScene.WISH, GameScene.SHOP),
          priority=10, description="Primogem count top area"),
    _spec("mu_ar", OcrPurpose.ADVENTURE_RANK, 0.88, 0.01, 0.10, 0.04,
          (GameScene.MENU,), priority=15, description="Adventure Rank top-right corner"),
    _spec("mu_item_count", OcrPurpose.ITEM_COUNT, 0.40, 0.45, 0.20, 0.10,
          (GameScene.MENU, GameScene.INVENTORY, GameScene.SHOP),
          priority=20, description="Selected item count/stack"),
    _spec("mu_notification", OcrPurpose.NOTIFICATION_TEXT, 0.20, 0.10, 0.60, 0.15,
          (GameScene.MENU, GameScene.NOTIFICATION), priority=5,
          description="Popup notification text"),
]

_DIALOG_ROIS: list[OcrRoiSpec] = [
    _spec("dg_text", OcrPurpose.DIALOG_TEXT, 0.15, 0.60, 0.70, 0.25,
          (GameScene.DIALOG,), priority=5, description="NPC dialog text area"),
    _spec("dg_option", OcrPurpose.DIALOG_OPTION, 0.25, 0.55, 0.50, 0.35,
          (GameScene.DIALOG,), priority=10, description="Dialog choice options"),
    _spec("dg_interaction", OcrPurpose.INTERACTION_PROMPT, 0.35, 0.55, 0.30, 0.08,
          (GameScene.DIALOG,), priority=15, description="Skip/advance prompt"),
]

_LOADING_ROIS: list[OcrRoiSpec] = [
    _spec("ld_tip", OcrPurpose.LOADING_TIP, 0.20, 0.80, 0.60, 0.15,
          (GameScene.LOADING,), priority=5, description="Loading screen tip text"),
    _spec("ld_timer", OcrPurpose.TIMER_COUNTDOWN, 0.40, 0.45, 0.20, 0.10,
          (GameScene.LOADING, GameScene.DOMAIN), priority=10,
          description="Loading/domain countdown timer"),
]

_CHARACTER_ROIS: list[OcrRoiSpec] = [
    _spec("ch_level", OcrPurpose.CHARACTER_LEVEL, 0.05, 0.15, 0.12, 0.06,
          (GameScene.CHARACTER_SCREEN,), priority=5, description="Character level number"),
    _spec("ch_talent", OcrPurpose.TALENT_LEVEL, 0.60, 0.70, 0.15, 0.05,
          (GameScene.CHARACTER_SCREEN,), priority=10, description="Talent level numbers"),
    _spec("ch_artifact_stat", OcrPurpose.ARTIFACT_MAIN_STAT, 0.45, 0.25, 0.25, 0.08,
          (GameScene.CHARACTER_SCREEN, GameScene.INVENTORY),
          priority=15, description="Artifact main stat text"),
]

_CRAFTING_ROIS: list[OcrRoiSpec] = [
    _spec("cr_count", OcrPurpose.ITEM_COUNT, 0.35, 0.40, 0.30, 0.15,
          (GameScene.CRAFTING,), priority=5, description="Crafting item count"),
    _spec("cr_price", OcrPurpose.SHOP_PRICE, 0.50, 0.60, 0.20, 0.06,
          (GameScene.CRAFTING, GameScene.SHOP), priority=10,
          description="Crafting/shop price"),
]

_DOMAIN_ROIS: list[OcrRoiSpec] = [
    _spec("dm_timer", OcrPurpose.TIMER_COUNTDOWN, 0.42, 0.01, 0.16, 0.05,
          (GameScene.DOMAIN,), priority=5, description="Domain countdown timer"),
    _spec("dm_reward", OcrPurpose.DOMAIN_REWARD, 0.25, 0.30, 0.50, 0.40,
          (GameScene.DOMAIN,), priority=10, description="Domain completion rewards"),
    _spec("dm_resin", OcrPurpose.RESIN_COUNT, 0.82, 0.01, 0.15, 0.04,
          (GameScene.DOMAIN,), priority=5, description="Resin cost for domain"),
]

_QUEST_LOG_ROIS: list[OcrRoiSpec] = [
    _spec("ql_quest_name", OcrPurpose.QUEST_TEXT, 0.05, 0.10, 0.40, 0.10,
          (GameScene.QUEST_LOG,), priority=5, description="Quest name in quest log"),
    _spec("ql_objective", OcrPurpose.QUEST_OBJECTIVE, 0.05, 0.25, 0.40, 0.50,
          (GameScene.QUEST_LOG,), priority=10, description="Quest objectives list"),
]

_PARTY_SETUP_ROIS: list[OcrRoiSpec] = [
    _spec("ps_level", OcrPurpose.CHARACTER_LEVEL, 0.10, 0.40, 0.10, 0.05,
          (GameScene.PARTY_SETUP,), priority=5, description="Character level in party setup"),
]

# Full fallback scan for unknown scenes
_FULL_SCAN_SPEC = _spec(
    "full_fallback", OcrPurpose.GENERIC_TEXT, 0.0, 0.0, 1.0, 1.0,
    (GameScene.UNKNOWN,), priority=100, fallback_full_scan=True,
    description="Full screen fallback scan",
)


@dataclass(frozen=True, slots=True)
class OcrScanResult:
    """Result of a targeted OCR scan."""
    roi_id: str
    purpose: OcrPurpose
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    scene: GameScene
    latency_ms: float
    from_fallback: bool = False


class GameSceneOcrRegistry:
    """Scene-aware OCR ROI registry.

    Maps game scenes to specific screen regions, enabling purpose-driven
    targeted OCR instead of wasteful full-screen scanning.

    Usage:
        registry = GameSceneOcrRegistry()
        rois = registry.get_rois(GameScene.OVERWORLD)
        for roi in rois:
            pixel_roi = roi.to_pixel_roi(frame.shape[0], frame.shape[1])
            results = ocr.detect_text(frame, roi=pixel_roi)
    """

    def __init__(self, custom_rois: list[OcrRoiSpec] | None = None) -> None:
        self._rois: dict[str, OcrRoiSpec] = {}
        self._scene_index: dict[GameScene, list[OcrRoiSpec]] = {}
        self._purpose_index: dict[OcrPurpose, list[OcrRoiSpec]] = {}

        # Register built-in ROIs
        all_builtins = (
            _OVERWORLD_ROIS + _COMBAT_ROIS + _MENU_ROIS +
            _DIALOG_ROIS + _LOADING_ROIS + _CHARACTER_ROIS +
            _CRAFTING_ROIS + _DOMAIN_ROIS + _QUEST_LOG_ROIS +
            _PARTY_SETUP_ROIS + [_FULL_SCAN_SPEC]
        )
        for spec in all_builtins:
            self.register(spec)

        # Register custom ROIs (override builtins with same roi_id)
        if custom_rois:
            for spec in custom_rois:
                self.register(spec)

    def register(self, spec: OcrRoiSpec) -> None:
        self._rois[spec.roi_id] = spec
        for scene in spec.scenes:
            if scene not in self._scene_index:
                self._scene_index[scene] = []
            lst = self._scene_index[scene]
            if spec not in lst:
                lst.append(spec)
                lst.sort(key=lambda s: s.priority)
        if spec.purpose not in self._purpose_index:
            self._purpose_index[spec.purpose] = []
        lst = self._purpose_index[spec.purpose]
        if spec not in lst:
            lst.append(spec)

    def get_rois(self, scene: GameScene) -> list[OcrRoiSpec]:
        return list(self._scene_index.get(scene, []))

    def get_roi_by_purpose(self, purpose: OcrPurpose) -> list[OcrRoiSpec]:
        return list(self._purpose_index.get(purpose, []))

    def get_roi_by_id(self, roi_id: str) -> OcrRoiSpec | None:
        return self._rois.get(roi_id)

    def all_rois(self) -> list[OcrRoiSpec]:
        return list(self._rois.values())

    def scene_count(self) -> int:
        return len(self._scene_index)


class OcrTargetedScanner:
    """Purpose-driven OCR scanner with scene awareness and fallback.

    Scans only the ROIs relevant to the current game scene, dramatically
    reducing processing time. Falls back to full-screen scan when targeted
    ROIs yield no results.

    Integrates with the existing OCRProvider protocol.
    """

    _FALLBACK_THRESHOLD = 0.3

    def __init__(
        self,
        provider: Any,
        registry: GameSceneOcrRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry or GameSceneOcrRegistry()

    def scan_scene(
        self,
        frame: np.ndarray,
        scene: GameScene,
        purposes: list[OcrPurpose] | None = None,
    ) -> list[OcrScanResult]:
        """Scan a frame for the given scene's ROIs.

        Args:
            frame: BGR frame from screen capture
            scene: Current game scene
            purposes: If provided, only scan ROIs matching these purposes

        Returns:
            List of OcrScanResult with matched text and metadata
        """
        h, w = frame.shape[:2]
        rois = self._registry.get_rois(scene)

        if purposes:
            purpose_set = set(purposes)
            rois = [r for r in rois if r.purpose in purpose_set]

        results: list[OcrScanResult] = []
        for roi in rois:
            pixel_roi = roi.to_pixel_roi(h, w)
            started = time.perf_counter()
            raw = self._provider.detect_text(frame, roi=pixel_roi)
            latency = (time.perf_counter() - started) * 1000.0

            for r in raw:
                results.append(OcrScanResult(
                    roi_id=roi.roi_id,
                    purpose=roi.purpose,
                    text=r.text,
                    confidence=r.confidence,
                    bbox=r.bbox,
                    scene=scene,
                    latency_ms=latency,
                ))

        # Fallback: if targeted scan yielded low-confidence or no results,
        # and we're in a known scene (not UNKNOWN), try full-screen scan
        if not results or max((r.confidence for r in results), default=0.0) < self._FALLBACK_THRESHOLD:
            if scene != GameScene.UNKNOWN:
                log.debug("[OcrTargeted] targeted scan yielded %d results (max_conf=%.2f), trying fallback",
                         len(results),
                         max((r.confidence for r in results), default=0.0))
                fallback_results = self._scan_fallback(frame, scene, h, w)
                results.extend(fallback_results)

        return results

    def scan_purpose(
        self,
        frame: np.ndarray,
        purpose: OcrPurpose,
        scene: GameScene | None = None,
    ) -> list[OcrScanResult]:
        """Scan for a specific purpose across all relevant scenes.

        Useful when you need a specific value (e.g., resin count) regardless
        of which scene the player is in.
        """
        h, w = frame.shape[:2]
        rois = self._registry.get_roi_by_purpose(purpose)

        if scene is not None:
            rois = [r for r in rois if scene in r.scenes]

        results: list[OcrScanResult] = []
        for roi in rois:
            pixel_roi = roi.to_pixel_roi(h, w)
            started = time.perf_counter()
            raw = self._provider.detect_text(frame, roi=pixel_roi)
            latency = (time.perf_counter() - started) * 1000.0
            for r in raw:
                results.append(OcrScanResult(
                    roi_id=roi.roi_id,
                    purpose=roi.purpose,
                    text=r.text,
                    confidence=r.confidence,
                    bbox=r.bbox,
                    scene=scene or GameScene.UNKNOWN,
                    latency_ms=latency,
                ))
        return results

    def _scan_fallback(
        self,
        frame: np.ndarray,
        scene: GameScene,
        h: int,
        w: int,
    ) -> list[OcrScanResult]:
        full_roi = _FULL_SCAN_SPEC.to_pixel_roi(h, w)
        started = time.perf_counter()
        raw = self._provider.detect_text(frame, roi=full_roi)
        latency = (time.perf_counter() - started) * 1000.0
        return [
            OcrScanResult(
                roi_id="full_fallback",
                purpose=_FULL_SCAN_SPEC.purpose,
                text=r.text,
                confidence=r.confidence,
                bbox=r.bbox,
                scene=scene,
                latency_ms=latency,
                from_fallback=True,
            )
            for r in raw
        ]
