from __future__ import annotations

import numpy as np

from combat.danger_detector import (
    DangerDetector,
    DangerSignals,
    DangerState,
    DangerThresholds,
    GenshinDangerSignalExtractor,
    _clamp,
)


def _bgr_color_frame(h: int, w: int, color: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = color
    return frame


def _make_red_circle_frame(
    h: int = 720,
    w: int = 1280,
    center: tuple[int, int] = (360, 640),
    radius: int = 250,
) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    try:
        import cv2  # type: ignore[import-not-found]

        cv2.circle(frame, center[::-1], radius, (0, 0, 255), -1)
    except ImportError:
        yy, xx = np.ogrid[:h, :w]
        mask = (xx - center[1]) ** 2 + (yy - center[0]) ** 2 <= radius**2
        frame[mask] = (0, 0, 255)
    return frame


def _make_yellow_stamina_bar(
    h: int = 40,
    w: int = 200,
    fill_ratio: float = 0.5,
) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    fill_w = max(1, int(w * fill_ratio))
    frame[:, :fill_w] = (0, 220, 255)
    return frame


def test_clamp_function() -> None:
    assert _clamp(-0.5) == 0.0
    assert _clamp(0.5) == 0.5
    assert _clamp(1.5) == 1.0


def test_existing_danger_detector_backward_compat() -> None:
    danger = DangerDetector().evaluate(
        {"generic_warning_area": 1.0, "projectile_approaching": 1.0, "hp_drop_signal": 0.4},
        context_priority=0.2,
    )
    assert isinstance(danger, DangerState)
    assert danger.score > 0.0
    assert danger.level in {"LOW", "MEDIUM", "HIGH"}


# --- GenshinDangerSignalExtractor tests ---
# ROI convention: (x1, y1, x2, y2) where x=column, y=row
# crop does: frame[y1:y2, x1:x2]


def test_ground_danger_detects_red_circle() -> None:
    frame = _make_red_circle_frame(radius=250)
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame)
    assert signals.ground_danger_zone > 0.10


def test_ground_danger_ignores_normal_frame() -> None:
    frame = _bgr_color_frame(720, 1280, (40, 120, 40))
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame)
    assert signals.ground_danger_zone < 0.05


def test_projectile_detection_with_motion() -> None:
    h, w = 720, 1280
    prev = np.zeros((h, w, 3), dtype=np.uint8)
    curr = np.zeros((h, w, 3), dtype=np.uint8)
    bright_val = (200, 200, 255)
    prev[350:380, 500:530] = bright_val
    curr[350:380, 540:570] = bright_val
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(curr, prev_frame=prev)
    assert signals.projectile_approaching > 0.0


def test_projectile_detection_static_frames() -> None:
    frame = _bgr_color_frame(720, 1280, (100, 100, 100))
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame, prev_frame=frame.copy())
    assert signals.projectile_approaching == 0.0


def test_hp_drop_detected() -> None:
    ext = GenshinDangerSignalExtractor()
    # ROI: rows 690-710, cols 200-800 -> (x1=200, y1=690, x2=800, y2=710)
    hp_roi = (200, 690, 800, 710)

    full_hp_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    full_hp_frame[690:710, 200:800] = (0, 200, 0)
    signals_full = ext.extract(full_hp_frame, rois={"active_char_hp": hp_roi})
    assert signals_full.hp_drop_signal == 0.0

    half_hp_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    half_hp_frame[690:710, 200:500] = (0, 200, 0)
    signals_drop = ext.extract(half_hp_frame, rois={"active_char_hp": hp_roi})
    assert signals_drop.hp_drop_signal > 0.2


def test_hp_no_drop_stable() -> None:
    ext = GenshinDangerSignalExtractor()
    hp_roi = (200, 690, 800, 710)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[690:710, 200:800] = (0, 200, 0)
    ext.extract(frame, rois={"active_char_hp": hp_roi})
    signals = ext.extract(frame, rois={"active_char_hp": hp_roi})
    assert signals.hp_drop_signal < 0.05


def test_stamina_critical_low_bar() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    stamina = _make_yellow_stamina_bar(fill_ratio=0.05)
    frame[680:700, 200:400] = stamina[:20, :200]
    # ROI: rows 680-700, cols 200-400 -> (x1=200, y1=680, x2=400, y2=700)
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame, rois={"stamina_bar": (200, 680, 400, 700)})
    assert signals.stamina_critical == 1.0


def test_stamina_ok() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    stamina = _make_yellow_stamina_bar(fill_ratio=0.8)
    frame[680:700, 200:400] = stamina[:20, :200]
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame, rois={"stamina_bar": (200, 680, 400, 700)})
    assert signals.stamina_critical == 0.0


def test_should_dodge_ground_danger() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.5,
        projectile_approaching=0.0,
        hp_drop_signal=0.0,
        boss_windup=0.0,
        stamina_critical=0.0,
        overall_danger=0.2,
    )
    should, reason, priority = ext.should_dodge(signals)
    assert should is True
    assert reason == "ground_danger_zone"
    assert priority == 0


def test_should_dodge_hp_drop() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.0,
        projectile_approaching=0.0,
        hp_drop_signal=0.5,
        boss_windup=0.0,
        stamina_critical=0.0,
        overall_danger=0.2,
    )
    should, reason, priority = ext.should_dodge(signals)
    assert should is True
    assert reason == "hp_drop_signal"
    assert priority == 0


def test_no_dodge_safe_scene() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.01,
        projectile_approaching=0.0,
        hp_drop_signal=0.0,
        boss_windup=0.0,
        stamina_critical=0.0,
        overall_danger=0.01,
    )
    should, reason, priority = ext.should_dodge(signals)
    assert should is False
    assert reason == ""
    assert priority == 6


def test_should_retreat_high_danger() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.8,
        projectile_approaching=0.7,
        hp_drop_signal=0.6,
        boss_windup=0.5,
        stamina_critical=0.3,
        overall_danger=0.92,
    )
    assert ext.should_retreat(signals) is True


def test_extract_with_rois() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[300:420, 400:600] = (0, 0, 255)
    frame[690:710, 200:800] = (0, 200, 0)
    frame[680:700, 200:400] = _make_yellow_stamina_bar(20, 200, fill_ratio=0.7)[:20, :200]

    rois = {
        "ground_area": (400, 300, 600, 420),
        "active_char_hp": (200, 690, 800, 710),
        "stamina_bar": (200, 680, 400, 700),
    }
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame, rois=rois)
    assert isinstance(signals, DangerSignals)
    assert 0.0 <= signals.ground_danger_zone <= 1.0
    assert 0.0 <= signals.hp_drop_signal <= 1.0
    assert 0.0 <= signals.stamina_critical <= 1.0
    assert 0.0 <= signals.overall_danger <= 1.0


def test_danger_signals_frozen() -> None:
    signals = DangerSignals(
        ground_danger_zone=0.0,
        projectile_approaching=0.0,
        hp_drop_signal=0.0,
        boss_windup=0.0,
        stamina_critical=0.0,
        overall_danger=0.0,
    )
    try:
        signals.ground_danger_zone = 1.0  # type: ignore[misc]
        assert False, "Should raise FrozenInstanceError"
    except AttributeError:
        pass


def test_overall_danger_composite_weighting() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.5,
        projectile_approaching=0.5,
        hp_drop_signal=0.0,
        boss_windup=0.0,
        stamina_critical=0.0,
        overall_danger=0.0,
    )
    overall = ext._compute_overall_danger(signals)
    expected = 0.5 * 0.35 + 0.5 * 0.20
    assert abs(overall - expected) < 1e-6


def test_projectile_detection_shape_mismatch() -> None:
    frame_a = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame_b = np.zeros((480, 640, 3), dtype=np.uint8)
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame_a, prev_frame=frame_b)
    assert signals.projectile_approaching == 0.0


def test_dodge_from_overall_danger_threshold() -> None:
    ext = GenshinDangerSignalExtractor()
    signals = DangerSignals(
        ground_danger_zone=0.0,
        projectile_approaching=0.0,
        hp_drop_signal=0.0,
        boss_windup=0.9,
        stamina_critical=0.0,
        overall_danger=0.75,
    )
    should, reason, priority = ext.should_dodge(signals)
    assert should is True
    assert reason == "boss_windup"
    assert priority == 2


def test_empty_frame_returns_safe_signals() -> None:
    frame = np.zeros((0, 0, 3), dtype=np.uint8)
    ext = GenshinDangerSignalExtractor()
    signals = ext.extract(frame)
    assert signals.ground_danger_zone == 0.0
    assert signals.hp_drop_signal <= 1.0
