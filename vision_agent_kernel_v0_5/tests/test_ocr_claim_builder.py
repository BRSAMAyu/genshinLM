"""Tests for OcrClaimBuilder — OCR-aware claim building integration."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from perception.ocr_claim_builder import OcrClaimBuilder, _map_scene
from perception.ocr_roi_registry import GameScene, OcrPurpose, OcrScanResult


@dataclass(frozen=True, slots=True)
class _FakeOcrResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    source: str = "fake"


class _FakeOcrProvider:
    """Fake OCR provider that returns canned results."""

    def __init__(self, results: list[_FakeOcrResult] | None = None) -> None:
        self._results = results or []
        self.calls: list[tuple[int, int, int, int] | None] = []

    def detect_text(self, image: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> list[_FakeOcrResult]:
        self.calls.append(roi)
        return self._results

    def status(self) -> object:
        return type("Status", (), {"provider": "fake", "ok": True, "message": "ok"})()


def test_map_scene_known_states() -> None:
    assert _map_scene("world_hud") == GameScene.OVERWORLD
    assert _map_scene("full_menu") == GameScene.MENU
    assert _map_scene("combat") == GameScene.COMBAT
    assert _map_scene("dialog") == GameScene.DIALOG
    assert _map_scene("loading") == GameScene.LOADING
    assert _map_scene("character_screen") == GameScene.CHARACTER_SCREEN
    assert _map_scene("shop") == GameScene.SHOP
    assert _map_scene("crafting") == GameScene.CRAFTING


def test_map_scene_unknown_falls_back() -> None:
    assert _map_scene("unknown") == GameScene.UNKNOWN
    assert _map_scene("something_weird") == GameScene.UNKNOWN


def test_build_claim_without_ocr() -> None:
    builder = OcrClaimBuilder()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    claim = builder.build_claim(
        game_id="genshin",
        frame_id=1,
        frame=frame,
        classifier_state="world_hud",
        classifier_confidence=0.9,
    )
    assert claim.game_id == "genshin"
    assert claim.screen_state == "overworld"
    assert claim.confidence == 0.9
    assert claim.source == "classifier"


def test_build_claim_with_fake_ocr() -> None:
    fake_results = [
        _FakeOcrResult(text="Lv.45", confidence=0.95, bbox=(100, 160, 200, 220)),
    ]
    fake_ocr = _FakeOcrProvider(results=fake_results)
    builder = OcrClaimBuilder(ocr_provider=fake_ocr)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    claim = builder.build_claim(
        game_id="genshin",
        frame_id=2,
        frame=frame,
        classifier_state="character_screen",
        classifier_confidence=0.7,
    )
    assert claim.screen_state == "character_select"
    assert "Lv.45" in claim.raw_ocr_texts
    assert len(claim.ui_elements) >= 1


def test_build_claim_menu_with_resin_ocr() -> None:
    fake_results = [
        _FakeOcrResult(text="120/160", confidence=0.90, bbox=(1580, 10, 1700, 50)),
        _FakeOcrResult(text="确认", confidence=0.88, bbox=(1200, 900, 1300, 950)),
    ]
    fake_ocr = _FakeOcrProvider(results=fake_results)
    builder = OcrClaimBuilder(ocr_provider=fake_ocr)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    claim = builder.build_claim(
        game_id="genshin",
        frame_id=3,
        frame=frame,
        classifier_state="full_menu",
        classifier_confidence=0.6,
    )
    assert claim.screen_state == "menu"
    assert len(claim.raw_ocr_texts) >= 1


def test_read_number_with_purpose() -> None:
    fake_results = [
        _FakeOcrResult(text="Lv.45", confidence=0.95, bbox=(100, 160, 200, 220)),
    ]
    fake_ocr = _FakeOcrProvider(results=fake_results)
    builder = OcrClaimBuilder(ocr_provider=fake_ocr)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    level = builder.read_number(frame, OcrPurpose.CHARACTER_LEVEL, "character_screen")
    assert level == 45


def test_read_number_returns_none_without_ocr() -> None:
    builder = OcrClaimBuilder()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert builder.read_number(frame, OcrPurpose.CHARACTER_LEVEL) is None


def test_read_purpose_returns_empty_without_ocr() -> None:
    builder = OcrClaimBuilder()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert builder.read_purpose(frame, OcrPurpose.RESIN_COUNT) == []


def test_build_claim_ocr_failure_graceful() -> None:
    """OCR scan failure should still produce a valid claim (classifier-only)."""

    class _BrokenOcr:
        name = "broken"
        def detect_text(self, image: np.ndarray, roi=None):
            raise RuntimeError("OCR engine crashed")
        def status(self):
            return type("Status", (), {"provider": "broken", "ok": False, "message": "dead"})()

    builder = OcrClaimBuilder(ocr_provider=_BrokenOcr())
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    claim = builder.build_claim(
        game_id="genshin",
        frame_id=4,
        frame=frame,
        classifier_state="world_hud",
        classifier_confidence=0.8,
    )
    assert claim.screen_state == "overworld"
    assert claim.raw_ocr_texts == ()
