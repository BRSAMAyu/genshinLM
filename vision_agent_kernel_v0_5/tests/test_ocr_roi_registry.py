from __future__ import annotations

import numpy as np
import pytest

from perception.ocr_roi_registry import (
    GameScene,
    GameSceneOcrRegistry,
    OcrPurpose,
    OcrRoiSpec,
    OcrScanResult,
    OcrTargetedScanner,
    _FULL_SCAN_SPEC,
)


class _FakeProvider:
    name = "fake"

    def __init__(self, results=None):
        self._results = results or []
        self.calls = []

    def detect_text(self, image, roi=None):
        self.calls.append(roi)
        return list(self._results)

    def status(self):
        from perception.ocr_base import ProviderStatus
        return ProviderStatus(provider="fake", ok=True)


class TestOcrRoiSpec:
    def test_to_pixel_roi_1080p(self):
        spec = OcrRoiSpec("test", OcrPurpose.RESIN_COUNT, 0.5, 0.1, 0.3, 0.2,
                          (GameScene.MENU,))
        x1, y1, x2, y2 = spec.to_pixel_roi(1080, 1920)
        assert x1 == 960
        assert y1 == 108
        assert x2 == 1536
        assert y2 == 324

    def test_to_pixel_roi_clamps(self):
        spec = OcrRoiSpec("test", OcrPurpose.GENERIC_TEXT, -0.1, -0.1, 1.5, 1.5,
                          (GameScene.UNKNOWN,))
        x1, y1, x2, y2 = spec.to_pixel_roi(100, 200)
        assert x1 == 0
        assert y1 == 0
        assert x2 == 200
        assert y2 == 100


class TestGameSceneOcrRegistry:
    def test_instantiation(self):
        reg = GameSceneOcrRegistry()
        assert reg.scene_count() >= 10

    def test_overworld_has_rois(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.OVERWORLD)
        assert len(rois) >= 4
        purposes = {r.purpose for r in rois}
        assert OcrPurpose.QUEST_OBJECTIVE in purposes
        assert OcrPurpose.INTERACTION_PROMPT in purposes

    def test_combat_has_boss_hp(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.COMBAT)
        purposes = {r.purpose for r in rois}
        assert OcrPurpose.BOSS_HP in purposes

    def test_menu_has_resin(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.MENU)
        purposes = {r.purpose for r in rois}
        assert OcrPurpose.RESIN_COUNT in purposes
        assert OcrPurpose.MORA_COUNT in purposes

    def test_dialog_has_text(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.DIALOG)
        purposes = {r.purpose for r in rois}
        assert OcrPurpose.DIALOG_TEXT in purposes

    def test_unknown_has_fallback(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.UNKNOWN)
        assert len(rois) >= 1
        assert any(r.roi_id == "full_fallback" for r in rois)

    def test_priority_ordering(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_rois(GameScene.COMBAT)
        priorities = [r.priority for r in rois]
        assert priorities == sorted(priorities)

    def test_get_roi_by_purpose(self):
        reg = GameSceneOcrRegistry()
        rois = reg.get_roi_by_purpose(OcrPurpose.RESIN_COUNT)
        assert len(rois) >= 1
        assert all(r.purpose == OcrPurpose.RESIN_COUNT for r in rois)

    def test_get_roi_by_id(self):
        reg = GameSceneOcrRegistry()
        roi = reg.get_roi_by_id("ow_quest_objective")
        assert roi is not None
        assert roi.purpose == OcrPurpose.QUEST_OBJECTIVE

    def test_custom_roi_overrides(self):
        custom = OcrRoiSpec(
            "ow_quest_objective", OcrPurpose.QUEST_OBJECTIVE,
            0.20, 0.01, 0.60, 0.08,
            (GameScene.OVERWORLD,), priority=1,
            description="custom override",
        )
        reg = GameSceneOcrRegistry(custom_rois=[custom])
        roi = reg.get_roi_by_id("ow_quest_objective")
        assert roi is not None
        assert roi.w_norm == 0.60
        assert roi.priority == 1

    def test_all_rois_count(self):
        reg = GameSceneOcrRegistry()
        all_r = reg.all_rois()
        assert len(all_r) >= 30


class TestOcrTargetedScanner:
    def test_scan_scene_basic(self):
        from perception.ocr_base import OcrResult
        fake = _FakeProvider(results=[
            OcrResult(text="120/200", confidence=0.95, bbox=(1500, 10, 1700, 40)),
        ])
        reg = GameSceneOcrRegistry()
        scanner = OcrTargetedScanner(fake, reg)

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        results = scanner.scan_scene(frame, GameScene.MENU)

        assert len(results) >= 1
        assert any(r.purpose == OcrPurpose.RESIN_COUNT for r in results)
        # Provider should have been called with ROI, not full frame
        assert fake.calls
        for call_roi in fake.calls:
            if call_roi is not None:
                x1, y1, x2, y2 = call_roi
                assert x2 - x1 < 1920  # Not full-width
                break

    def test_scan_with_purpose_filter(self):
        fake = _FakeProvider()
        reg = GameSceneOcrRegistry()
        scanner = OcrTargetedScanner(fake, reg)

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        scanner.scan_scene(frame, GameScene.OVERWORLD, purposes=[OcrPurpose.HP_BAR])

        # Only HP-related ROIs should be scanned
        assert len(fake.calls) >= 1

    def test_scan_purpose_across_scenes(self):
        fake = _FakeProvider()
        reg = GameSceneOcrRegistry()
        scanner = OcrTargetedScanner(fake, reg)

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        scanner.scan_purpose(frame, OcrPurpose.RESIN_COUNT)

        # Resin appears in menu, domain, map
        assert len(fake.calls) >= 2

    def test_fallback_on_empty_results(self):
        fake = _FakeProvider(results=[])  # No results from targeted
        reg = GameSceneOcrRegistry()
        scanner = OcrTargetedScanner(fake, reg)

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        results = scanner.scan_scene(frame, GameScene.OVERWORLD)

        # Should have triggered fallback full scan
        assert any(call is not None and call == (0, 0, 1920, 1080) for call in fake.calls)

    def test_no_fallback_for_unknown_scene(self):
        fake = _FakeProvider(results=[])
        reg = GameSceneOcrRegistry()
        scanner = OcrTargetedScanner(fake, reg)

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        results = scanner.scan_scene(frame, GameScene.UNKNOWN)

        # Should NOT trigger double fallback for UNKNOWN
        full_scans = sum(1 for c in fake.calls if c is not None and c == (0, 0, 1920, 1080))
        assert full_scans <= 1  # Only the built-in full_scan_spec, no extra fallback
