"""Tests for the Genshin party-state perception reader.

Synthetic HUD frames (numpy arrays we construct) drive the reader so we can
assert its structure and heuristics without a real game: active-card detection,
burst-ready true only when the Q ring is full, energy_ratio monotonic with ring
fill, and that ``build_combat_view`` produces a multi-char ``CombatView`` once a
party state is injected (so the controller can burst/skill/switch, not just
attack). Exact pixel thresholds need real-game calibration (see
``CALIBRATION_RESIDUALS``); these tests use deliberately extreme synthetic crops
(fully lit vs fully dark) so they hold regardless of final tuning.
"""
from __future__ import annotations

import time

import numpy as np

from capsules.genshin.control_adapters import build_combat_view
from capsules.genshin.party_state_reader import (
    CALIBRATION_RESIDUALS,
    GenshinPartyStateReader,
    PartyState,
    PartyStateThresholds,
    load_party_rois,
)
from combat.reactive_combat_controller import (
    CombatCharView,
    CombatView,
    ReactiveCombatController,
)
from core.types import FocusState, Observation

# Use ROIs covering distinct, non-overlapping regions of a synthetic 100x100
# frame so each painted block maps to exactly one signal. (x, y, w, h) norm.
_TEST_ROIS = {
    "party_portraits": (0.0, 0.0, 0.10, 0.80),   # left column, 4 stacked cards
    "skill_q_icon": (0.40, 0.40, 0.20, 0.20),     # centre block = Q ring
    "skill_e_icon": (0.70, 0.40, 0.20, 0.20),     # right block = E icon
    "active_char_hp": (0.20, 0.90, 0.60, 0.06),   # bottom strip = HP bar
}


def _frame(h: int = 200, w: int = 200) -> np.ndarray:
    """A black BGR frame to paint synthetic HUD elements onto."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def _fill_norm(frame: np.ndarray, roi: tuple[float, float, float, float],
               color: tuple[int, int, int]) -> None:
    h, w = frame.shape[:2]
    x0, y0 = int(roi[0] * w), int(roi[1] * h)
    x1, y1 = int((roi[0] + roi[2]) * w), int((roi[1] + roi[3]) * h)
    frame[y0:y1, x0:x1] = color  # BGR


def _paint_ring(frame: np.ndarray, roi: tuple[float, float, float, float],
                fill_fraction: float, color: tuple[int, int, int]) -> None:
    """Paint a bright annulus over ``fill_fraction`` of its angular sweep.

    Models a Q energy ring charged to ``fill_fraction`` (1.0 = full = ready).
    """
    h, w = frame.shape[:2]
    x0, y0 = int(roi[0] * w), int(roi[1] * h)
    x1, y1 = int((roi[0] + roi[2]) * w), int((roi[1] + roi[3]) * h)
    sub = frame[y0:y1, x0:x1]
    sh, sw = sub.shape[:2]
    cy, cx = (sh - 1) / 2.0, (sw - 1) / 2.0
    half = min(sh, sw) / 2.0
    yy, xx = np.mgrid[0:sh, 0:sw]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) / max(half, 1e-6)
    annulus = (dist >= 0.55) & (dist <= 0.95)
    # angle 0..1 starting from top, clockwise
    ang = (np.arctan2(xx - cx, -(yy - cy)) + np.pi) / (2 * np.pi)
    lit = annulus & (ang <= fill_fraction)
    sub[lit] = color


def _reader(**kw: object) -> GenshinPartyStateReader:
    return GenshinPartyStateReader(rois=_TEST_ROIS, **kw)  # type: ignore[arg-type]


def _obs() -> Observation:
    t = time.perf_counter()
    return Observation(
        frame_id=1, t_capture=t, t_processed=t, latency_ms=0.0,
        viewport_size=(200, 200), target_track=None, obstacle_field=None,
        ui_state=None, visual_triggers={}, os_focus=FocusState(focused=True),
        extensions={},
    )


# --- ROI loading -----------------------------------------------------------


def test_load_party_rois_from_bundled_profile() -> None:
    rois = load_party_rois()  # bundled genshin.json
    for key in ("party_portraits", "active_char_hp", "skill_e_icon", "skill_q_icon"):
        assert key in rois
        x, y, w, h = rois[key]
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and w > 0.0 and h > 0.0


def test_load_party_rois_falls_back_on_bad_profile() -> None:
    rois = load_party_rois({"rois": {}})  # empty -> all fallbacks
    assert rois["skill_q_icon"] == (0.82, 0.87, 0.04, 0.06)


# --- active card detection -------------------------------------------------


def test_active_index_picks_brightest_card() -> None:
    frame = _frame()
    # Party strip split into 4 stacked cards; brighten the 3rd (index 2).
    px, py, pw, ph = _TEST_ROIS["party_portraits"]
    card_h = ph / 4.0
    _fill_norm(frame, (px, py + 2 * card_h, pw, card_h), (200, 200, 200))
    party = _reader().read(frame, _obs())
    assert party.active_index == 2


def test_active_index_defaults_zero_when_ambiguous() -> None:
    frame = _frame()  # all cards equally dark
    party = _reader().read(frame, _obs())
    assert party.active_index == 0
    assert any("ambiguous" in n or "empty" in n for n in party.notes)


# --- burst (Q) ring --------------------------------------------------------


def test_burst_ready_only_when_ring_full() -> None:
    th = PartyStateThresholds()
    # Full ring -> burst ready.
    full = _frame()
    _paint_ring(full, _TEST_ROIS["skill_q_icon"], 1.0, (60, 255, 255))
    p_full = _reader(thresholds=th).read(full, _obs())
    assert p_full.chars[p_full.active_index].burst_ready is True
    assert p_full.chars[p_full.active_index].energy_ratio >= th.burst_ready_fill

    # Half ring -> NOT ready (safe default).
    half = _frame()
    _paint_ring(half, _TEST_ROIS["skill_q_icon"], 0.5, (60, 255, 255))
    p_half = _reader(thresholds=th).read(half, _obs())
    assert p_half.chars[p_half.active_index].burst_ready is False

    # Empty ring -> NOT ready, energy ~0.
    empty = _frame()
    p_empty = _reader(thresholds=th).read(empty, _obs())
    assert p_empty.chars[p_empty.active_index].burst_ready is False
    assert p_empty.chars[p_empty.active_index].energy_ratio < 0.1


def test_energy_ratio_monotonic_with_ring_fill() -> None:
    ratios = []
    for fill in (0.0, 0.25, 0.5, 0.75, 1.0):
        frame = _frame()
        if fill > 0:
            _paint_ring(frame, _TEST_ROIS["skill_q_icon"], fill, (60, 255, 255))
        party = _reader().read(frame, _obs())
        ratios.append(party.chars[party.active_index].energy_ratio)
    # non-decreasing with fill
    assert all(b >= a - 1e-6 for a, b in zip(ratios, ratios[1:]))
    assert ratios[-1] > ratios[0]


# --- skill (E) icon --------------------------------------------------------


def test_skill_ready_when_icon_bright_not_when_dark() -> None:
    bright = _frame()
    _fill_norm(bright, _TEST_ROIS["skill_e_icon"], (200, 200, 200))
    p_ready = _reader().read(bright, _obs())
    assert p_ready.chars[p_ready.active_index].skill_ready is True

    dark = _frame()  # dark E icon = cooling down
    p_cd = _reader().read(dark, _obs())
    assert p_cd.chars[p_cd.active_index].skill_ready is False


# --- HP bar ----------------------------------------------------------------


def test_hp_ratio_tracks_bar_fill() -> None:
    full = _frame()
    _fill_norm(full, _TEST_ROIS["active_char_hp"], (120, 255, 120))  # green bar
    p_full = _reader().read(full, _obs())
    assert p_full.chars[p_full.active_index].hp_ratio > 0.8

    # Half-filled bar: paint only the left half of the HP strip.
    half = _frame()
    hx, hy, hw, hh = _TEST_ROIS["active_char_hp"]
    _fill_norm(half, (hx, hy, hw / 2.0, hh), (120, 255, 120))
    p_half = _reader().read(half, _obs())
    assert 0.3 < p_half.chars[p_half.active_index].hp_ratio < 0.7


# --- off-field chars stay conservative -------------------------------------


def test_off_field_chars_conservative() -> None:
    frame = _frame()
    _paint_ring(frame, _TEST_ROIS["skill_q_icon"], 1.0, (60, 255, 255))
    _fill_norm(frame, _TEST_ROIS["skill_e_icon"], (200, 200, 200))
    party = _reader().read(frame, _obs())
    assert len(party.chars) == 4
    for c in party.chars:
        if c.index != party.active_index:
            assert c.skill_ready is False and c.burst_ready is False
            assert c.energy_ratio == 0.0


# --- malformed frame safe --------------------------------------------------


def test_bad_frame_yields_safe_single() -> None:
    party = GenshinPartyStateReader(rois=_TEST_ROIS).read(np.zeros((0,)), _obs())
    assert isinstance(party, PartyState)
    assert len(party.chars) == 1
    assert party.chars[0].burst_ready is False and party.chars[0].skill_ready is False
    assert party.confidence == 0.0


# --- inject + build_combat_view integration --------------------------------


def test_inject_populates_extensions_in_consumable_shape() -> None:
    obs = _obs()
    reader = _reader()
    party = PartyState(
        chars=(
            CombatCharView(0, "dps", "pyro", 1.0, 1.0, True, True, "dps"),
            CombatCharView(1, "sub", "hydro", 1.0, 0.0, True, False, "sub"),
        ),
        active_index=0,
        confidence=0.9,
    )
    reader.inject(obs, party)
    assert obs.extensions["party_state"] == party.chars
    assert obs.extensions["party_active_index"] == 0
    assert obs.extensions["party_state_full"] is party


def test_build_combat_view_reads_injected_party_state() -> None:
    obs = _obs()
    chars = (
        CombatCharView(0, "dps", "pyro", 1.0, 1.0, True, True, "dps"),
        CombatCharView(1, "sub", "hydro", 1.0, 0.0, True, False, "sub"),
    )
    obs.extensions["party_state"] = chars
    obs.extensions["party_active_index"] = 0
    view = build_combat_view(obs, "combat")  # no explicit chars
    assert isinstance(view, CombatView)
    assert len(view.chars) == 2
    assert view.active_index == 0
    # The controller can now burst on the active char (energy full, burst ready).
    action = ReactiveCombatController().decide(view)
    assert action.kind == "burst"


def test_explicit_chars_still_wins_over_injected() -> None:
    obs = _obs()
    obs.extensions["party_state"] = (
        CombatCharView(0, "dps", "pyro", 1.0, 1.0, True, True, "dps"),
    )
    explicit = (
        CombatCharView(0, "dps", "pyro", 1.0, 0.0, False, False, "dps"),
    )
    view = build_combat_view(obs, "combat", chars=explicit)
    assert view.chars == explicit  # explicit arg wins
    action = ReactiveCombatController().decide(view)
    assert action.kind == "attack"  # nothing ready


def test_full_pipeline_reader_to_multichar_combat() -> None:
    """End-to-end: synthetic HUD -> reader -> inject -> multi-char combat view."""
    frame = _frame()
    px, py, pw, ph = _TEST_ROIS["party_portraits"]
    _fill_norm(frame, (px, py, pw, ph / 4.0), (200, 200, 200))  # active = slot 0
    _paint_ring(frame, _TEST_ROIS["skill_q_icon"], 1.0, (60, 255, 255))  # burst ready
    obs = _obs()
    reader = _reader(roster=(
        ("amber", "pyro", "dps"),
        ("barbara", "hydro", "healer"),
        ("lisa", "electro", "sub"),
        ("kaeya", "cryo", "sub"),
    ))
    party = reader.read(frame, obs)
    reader.inject(obs, party)
    view = build_combat_view(obs, "combat")
    assert len(view.chars) == 4
    action = ReactiveCombatController().decide(view)
    # active char (amber) has a full burst ready -> controller bursts.
    assert action.kind == "burst"


def test_calibration_residuals_documented() -> None:
    assert CALIBRATION_RESIDUALS
    assert all(isinstance(s, str) and s for s in CALIBRATION_RESIDUALS)
