"""OCR-aware claim builder — wires OcrTargetedScanner into ScreenStateClaimBuilder.

Bridges the gap between the pixel-only GenshinScreenClassifier and the
OCR-ready ScreenStateClaimBuilder by running targeted OCR scans on the
current frame based on the detected screen state.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from perception.ocr_base import OcrResult
from perception.ocr_roi_registry import (
    GameScene,
    GameSceneOcrRegistry,
    OcrPurpose,
    OcrScanResult,
    OcrTargetedScanner,
)
from planning.screen_state_claim import ScreenStateClaim
from planning.screen_state_claim_builder import (
    ClassifierOutput,
    OcrOutput,
    ScreenStateClaimBuilder,
    VLMOutput,
)

log = logging.getLogger(__name__)

# Map classifier state names to GameScene enum values.
_CLASSIFIER_TO_SCENE: dict[str, GameScene] = {
    "world_hud": GameScene.OVERWORLD,
    "overworld": GameScene.OVERWORLD,
    "combat": GameScene.COMBAT,
    "full_menu": GameScene.MENU,
    "menu": GameScene.MENU,
    "paimon_menu": GameScene.MENU,
    "dialog": GameScene.DIALOG,
    "loading": GameScene.LOADING,
    "loading_screen": GameScene.LOADING,
    "map": GameScene.MAP,
    "inventory": GameScene.INVENTORY,
    "backpack": GameScene.INVENTORY,
    "character_screen": GameScene.CHARACTER_SCREEN,
    "character_select_screen": GameScene.CHARACTER_SCREEN,
    "shop": GameScene.SHOP,
    "crafting": GameScene.CRAFTING,
    "forging": GameScene.CRAFTING,
    "domain_entrance": GameScene.DOMAIN,
    "domain": GameScene.DOMAIN,
    "wish": GameScene.WISH,
    "notification": GameScene.NOTIFICATION,
    "notification_popup": GameScene.NOTIFICATION,
    "quest_log": GameScene.QUEST_LOG,
    "cutscene": GameScene.DIALOG,
    "death_screen": GameScene.UNKNOWN,
    "no_hud": GameScene.UNKNOWN,
    "unknown": GameScene.UNKNOWN,
}


def _map_scene(classifier_state: str) -> GameScene:
    state = classifier_state.lower().strip()
    return _CLASSIFIER_TO_SCENE.get(state, GameScene.UNKNOWN)


def _scan_to_ocr_output(scan: OcrScanResult, frame_h: int, frame_w: int) -> OcrOutput:
    """Convert OcrScanResult to the OcrOutput format expected by ClaimBuilder."""
    return OcrOutput(
        text=scan.text,
        confidence=scan.confidence,
        bbox_norm=(
            scan.bbox[0] / frame_w,
            scan.bbox[1] / frame_h,
            scan.bbox[2] / frame_w,
            scan.bbox[3] / frame_h,
        ),
        source=scan.roi_id,
    )


class OcrClaimBuilder:
    """High-level claim builder that runs OCR + classifier fusion.

    Usage::

        builder = OcrClaimBuilder(ocr_provider=paddle_engine)
        claim = builder.build_claim(
            game_id="genshin",
            frame_id=42,
            frame=captured_frame,
            classifier_state="full_menu",
            classifier_confidence=0.6,
        )
    """

    def __init__(
        self,
        ocr_provider: Any = None,
        registry: GameSceneOcrRegistry | None = None,
        claim_builder: ScreenStateClaimBuilder | None = None,
    ) -> None:
        self._scanner: OcrTargetedScanner | None = None
        self._claim_builder = claim_builder or ScreenStateClaimBuilder()
        self._registry = registry or GameSceneOcrRegistry()
        if ocr_provider is not None:
            self._scanner = OcrTargetedScanner(ocr_provider, self._registry)

    def build_claim(
        self,
        game_id: str,
        frame_id: int,
        frame: np.ndarray,
        classifier_state: str = "unknown",
        classifier_confidence: float = 0.0,
        vlm: VLMOutput | None = None,
        extra_purposes: list[OcrPurpose] | None = None,
    ) -> ScreenStateClaim:
        """Build a ScreenStateClaim with OCR-augmented verification.

        Args:
            game_id: Game identifier (e.g., "genshin").
            frame_id: Sequential frame identifier.
            frame: BGR numpy array of the captured frame.
            classifier_state: State from GenshinScreenClassifier.
            classifier_confidence: Classifier confidence (0.0-1.0).
            vlm: Optional VLM output for higher-fidelity fusion.
            extra_purposes: Additional OCR purposes to scan beyond scene defaults.
        """
        classifier = ClassifierOutput(
            screen_state=classifier_state,
            confidence=classifier_confidence,
            source="genshin_classifier",
        )

        ocr_outputs: list[OcrOutput] = []
        if self._scanner is not None and frame is not None and frame.size > 0:
            scene = _map_scene(classifier_state)
            scan_results = self._scan_frame(frame, scene, extra_purposes)
            frame_h, frame_w = frame.shape[:2]
            ocr_outputs = [_scan_to_ocr_output(r, frame_h, frame_w) for r in scan_results]

        return self._claim_builder.build(
            game_id=game_id,
            frame_id=frame_id,
            frame_raw=frame,
            vlm=vlm,
            classifier=classifier,
            ocr_results=ocr_outputs if ocr_outputs else None,
        )

    def read_purpose(
        self,
        frame: np.ndarray,
        purpose: OcrPurpose,
        scene_hint: str = "",
    ) -> list[OcrScanResult]:
        """Read a specific OCR purpose from the frame.

        Convenience method for targeted reads (e.g., character level, resin).
        """
        if self._scanner is None:
            return []
        scene = _map_scene(scene_hint) if scene_hint else None
        return self._scanner.scan_purpose(frame, purpose, scene)

    def read_number(
        self,
        frame: np.ndarray,
        purpose: OcrPurpose,
        scene_hint: str = "",
    ) -> int | None:
        """Read a numeric value for a specific purpose.

        Returns the first integer found in the OCR text, or None.
        """
        results = self.read_purpose(frame, purpose, scene_hint)
        import re
        for r in results:
            digits = re.sub(r"\D", "", r.text)
            if digits:
                return int(digits)
        return None

    def _scan_frame(
        self,
        frame: np.ndarray,
        scene: GameScene,
        extra_purposes: list[OcrPurpose] | None,
    ) -> list[OcrScanResult]:
        if self._scanner is None:
            return []
        try:
            started = time.perf_counter()
            results = self._scanner.scan_scene(frame, scene)
            if extra_purposes:
                for purpose in extra_purposes:
                    results.extend(self._scanner.scan_purpose(frame, purpose, scene))
            elapsed = (time.perf_counter() - started) * 1000.0
            log.debug(
                "[OcrClaimBuilder] scene=%s rois=%d results=%d latency=%.1fms",
                scene.value,
                len(self._registry.get_rois(scene)),
                len(results),
                elapsed,
            )
            return results
        except Exception as exc:
            log.warning("[OcrClaimBuilder] OCR scan failed: %s", exc)
            return []
