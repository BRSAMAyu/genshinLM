"""Genshin party-state perception reader (the #1 live-combat blocker).

Today live combat can only issue ``attack`` because no per-character HP / energy /
cooldown data exists: :func:`capsules.genshin.control_adapters.build_combat_view`
synthesises a single conservative DPS char when no ``chars`` are supplied, so the
:class:`~combat.reactive_combat_controller.ReactiveCombatController` never has the
information it needs to burst, use a skill, switch, or heal.

This module is the missing perception step. It reads the Genshin HUD party panel
(4 character cards on the right edge), the active character's elemental-burst (Q)
energy ring and skill (E) cooldown icon, and the active character's HP bar, and
emits a tuple of :class:`~combat.reactive_combat_controller.CombatCharView` in the
exact shape ``build_combat_view`` consumes — written into
``Observation.extensions["party_state"]`` via :func:`inject`.

Design rules honoured here (mirroring the rest of the capsule's CV code):

* **Classic CV, not ML.** HSV thresholds, ring-fill fraction, brightness of the
  active-card highlight. ``cv2`` is used when present; a pure-numpy fallback keeps
  the reader importable in test/CI environments without OpenCV.
* **Genshin specifics stay in the capsule.** ROIs come from the resolution-
  independent ``configs/profiles/genshin.json`` profile (normalized ``relative``
  rects), never hardcoded pixels in core. Tunable thresholds live in
  :class:`PartyStateThresholds`, defaulting from that same profile / this module —
  not magic numbers sprinkled through logic.
* **Safe by default.** Exact HP%, energy-ring, and cooldown pixel thresholds need
  real-game calibration (see ``CALIBRATION_RESIDUALS``). Until a signal is *clearly*
  detected the reader reports the conservative state: burst NOT ready, skill NOT
  ready, energy 0.0. A reader that over-reports "burst ready" would make combat act
  dangerously; under-reporting only costs an attack.
* **Monotonic clock only** (this module performs no timing of its own; ``read`` is
  pure over a single frame).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:  # OpenCV is optional; pure-numpy fallback keeps the reader importable.
    import cv2
except ImportError:  # pragma: no cover - exercised only on cv2-less environments
    cv2 = None  # type: ignore[assignment]

from combat.reactive_combat_controller import CombatCharView

# Default profile path (resolution-independent normalized ROIs). The integrator
# can pass a different profile dict / path; this is only the standalone default.
_DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[2] / "configs" / "profiles" / "genshin.json"
)

# Normalized ROIs used by the reader, with documented fallbacks matching
# ``genshin.json`` so the reader still works if a profile omits a key.
_FALLBACK_ROIS: dict[str, tuple[float, float, float, float]] = {
    # 4 stacked character cards on the right edge.
    "party_portraits": (0.94, 0.44, 0.04, 0.26),
    # Active char HP bar, bottom-centre.
    "active_char_hp": (0.30, 0.89, 0.40, 0.04),
    # Elemental-skill (E) cooldown icon, bottom-right.
    "skill_e_icon": (0.87, 0.87, 0.04, 0.06),
    # Elemental-burst (Q) energy ring, bottom-right.
    "skill_q_icon": (0.82, 0.87, 0.04, 0.06),
}


@dataclass(frozen=True, slots=True)
class PartyStateThresholds:
    """Tunable CV thresholds — calibrate against the real game (see residuals).

    Every value here is a *documented best-guess* that must be tuned with real
    Genshin frames. They are grouped so a capsule config / profile can override
    the whole block. Defaults bias toward the safe (under-report) side.
    """

    # --- party size / slots --------------------------------------------------
    party_size: int = 4

    # --- active-card highlight ----------------------------------------------
    # The active card is brighter/enlarged. We pick the card whose mean
    # brightness (HSV V) is the highest and clears ``active_min_brightness``.
    active_min_brightness: float = 60.0
    # A card must beat the runner-up by this ratio to be "clearly" active; if no
    # card stands out we fall back to slot 0 (safe: index in range).
    active_dominance_ratio: float = 1.08

    # --- burst (Q) energy ring ----------------------------------------------
    # The ring is "full" (burst ready) when the bright/coloured ring pixels
    # exceed this fraction of the ring annulus.
    burst_ready_fill: float = 0.90
    # Saturation/value floor for counting a pixel as "lit" ring (vs dim/empty).
    ring_lit_min_sat: float = 70.0
    ring_lit_min_val: float = 130.0
    # Inner/outer radius (fraction of icon half-size) defining the ring annulus.
    ring_inner_frac: float = 0.55
    ring_outer_frac: float = 0.95

    # --- skill (E) cooldown --------------------------------------------------
    # E is ready when the icon is bright/coloured (no dark cooldown sweep).
    # Ready when the lit fraction of the icon exceeds this.
    skill_ready_fill: float = 0.70
    skill_lit_min_val: float = 110.0

    # --- HP bar (active char) ------------------------------------------------
    # HP bar is a horizontal green/white fill; ratio = lit columns / total.
    hp_lit_min_val: float = 110.0
    hp_lit_min_sat: float = 25.0


@dataclass(frozen=True, slots=True)
class PartyState:
    """Structured party-state reading; ``chars`` is what the controller needs.

    ``chars`` is in the exact :class:`CombatCharView` shape and order that
    :func:`capsules.genshin.control_adapters.build_combat_view` consumes.
    ``confidence`` is a coarse 0-1 self-assessment (low when ROIs were empty /
    cv2 missing) so a caller can decide whether to trust the richer view.
    """

    chars: tuple[CombatCharView, ...]
    active_index: int
    confidence: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)


# Calibration residuals — the exact thresholds that need real-game tuning. These
# are exported so a perception-roadmap task can consume them programmatically and
# so the honesty about "structure landed, numbers pending" is machine-readable.
CALIBRATION_RESIDUALS: tuple[str, ...] = (
    "burst_ready_fill / ring_lit_min_sat / ring_lit_min_val "
    "(Q energy-ring full vs partial — needs per-element ring colours)",
    "skill_ready_fill / skill_lit_min_val "
    "(E ready vs cooldown-sweep dark overlay — needs cooldown-icon samples)",
    "active_min_brightness / active_dominance_ratio "
    "(which party card is highlighted/enlarged — needs active-vs-dim samples)",
    "hp_lit_min_val / hp_lit_min_sat "
    "(active-char HP-bar fill fraction — needs full/half/low HP-bar samples)",
    "party_portraits / active_char_hp / skill_e_icon / skill_q_icon ROIs "
    "(per-slot card sub-rects — current ROIs are the testbed profile, "
    "real Genshin card stack geometry must be measured)",
    "energy_ratio for OFF-FIELD chars (their Q ring is not on the HUD; only the "
    "active char's ring/cooldown is visible — off-field energy stays 0.0 / unknown)",
)


def load_party_rois(
    profile: dict[str, Any] | str | Path | None = None,
) -> dict[str, tuple[float, float, float, float]]:
    """Resolve the normalized ROIs the reader needs from a profile.

    Accepts a profile dict, a path to a profile JSON, or ``None`` (uses the
    bundled ``genshin.json``). Only ``relative``-mode ROIs are read here; any
    ROI missing or not in relative mode falls back to ``_FALLBACK_ROIS`` so the
    reader never crashes on an incomplete profile. Keeping ROI resolution in the
    capsule (not core) honours the "Genshin specifics stay local" rule.
    """
    data: dict[str, Any]
    if isinstance(profile, dict):
        data = profile
    else:
        path = Path(profile) if profile is not None else _DEFAULT_PROFILE
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            data = {}

    rois_raw = data.get("rois", {}) if isinstance(data, dict) else {}
    out: dict[str, tuple[float, float, float, float]] = {}
    for key, fallback in _FALLBACK_ROIS.items():
        spec = rois_raw.get(key) if isinstance(rois_raw, dict) else None
        if isinstance(spec, dict) and spec.get("mode") == "relative":
            try:
                out[key] = (
                    float(spec["x"]),
                    float(spec["y"]),
                    float(spec["w"]),
                    float(spec["h"]),
                )
                continue
            except (KeyError, TypeError, ValueError):
                pass
        out[key] = fallback
    return out


def _crop(frame: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    """Crop a normalized ROI ``(x, y, w, h)`` from a frame, clamped to bounds."""
    h, w = frame.shape[:2]
    x0 = int(round(roi[0] * w))
    y0 = int(round(roi[1] * h))
    x1 = int(round((roi[0] + roi[2]) * w))
    y1 = int(round((roi[1] + roi[3]) * h))
    x0 = max(0, min(x0, w))
    y0 = max(0, min(y0, h))
    x1 = max(x0, min(x1, w))
    y1 = max(y0, min(y1, h))
    return frame[y0:y1, x0:x1]


def _to_hsv(crop: np.ndarray) -> np.ndarray | None:
    """Convert a BGR crop to HSV (OpenCV ranges). Returns None if empty/bad."""
    if crop.size == 0 or crop.ndim != 3 or crop.shape[2] < 3:
        return None
    if cv2 is not None:
        return cv2.cvtColor(crop[:, :, :3], cv2.COLOR_BGR2HSV)
    return _bgr_to_hsv_numpy(crop[:, :, :3])


def _bgr_to_hsv_numpy(bgr: np.ndarray) -> np.ndarray:
    """Pure-numpy BGR->HSV matching OpenCV ranges (H:0-179, S/V:0-255).

    Used only when ``cv2`` is unavailable so the reader (and its tests) stay
    importable. Vectorised over the crop.
    """
    arr = bgr.astype(np.float32) / 255.0
    b, g, r = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    diff = mx - mn

    h = np.zeros_like(mx)
    mask = diff > 1e-6
    # red is max
    rm = mask & (mx == r)
    h[rm] = (60.0 * (g[rm] - b[rm]) / diff[rm]) % 360.0
    # green is max
    gm = mask & (mx == g) & ~rm
    h[gm] = 60.0 * (b[gm] - r[gm]) / diff[gm] + 120.0
    # blue is max
    bm = mask & (mx == b) & ~rm & ~gm
    h[bm] = 60.0 * (r[bm] - g[bm]) / diff[bm] + 240.0

    s = np.where(mx > 1e-6, diff / mx, 0.0)
    v = mx

    hsv = np.empty(bgr.shape[:2] + (3,), dtype=np.uint8)
    hsv[..., 0] = np.clip(h / 2.0, 0, 179).astype(np.uint8)  # OpenCV halves hue
    hsv[..., 1] = np.clip(s * 255.0, 0, 255).astype(np.uint8)
    hsv[..., 2] = np.clip(v * 255.0, 0, 255).astype(np.uint8)
    return hsv


def _ring_fill_fraction(hsv: np.ndarray, th: PartyStateThresholds) -> float:
    """Fraction of the ring annulus that is 'lit' (energy filled).

    Builds an annulus mask between ``ring_inner_frac`` and ``ring_outer_frac`` of
    the icon half-size, then measures the share of annulus pixels whose S and V
    clear the lit thresholds. Monotonic with how much of the Q ring is charged.
    """
    h, w = hsv.shape[:2]
    if h < 4 or w < 4:
        return 0.0
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    half = min(h, w) / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) / max(half, 1e-6)
    annulus = (dist >= th.ring_inner_frac) & (dist <= th.ring_outer_frac)
    total = int(annulus.sum())
    if total == 0:
        return 0.0
    s = hsv[..., 1].astype(np.float32)
    v = hsv[..., 2].astype(np.float32)
    lit = annulus & (s >= th.ring_lit_min_sat) & (v >= th.ring_lit_min_val)
    return float(int(lit.sum()) / total)


def _icon_lit_fraction(hsv: np.ndarray, min_val: float) -> float:
    """Fraction of an icon that is bright (V >= min_val).

    A ready skill icon is brightly lit; a cooling-down icon is darkened by the
    radial cooldown sweep, lowering the bright fraction. Coarse but monotonic.
    """
    if hsv.size == 0:
        return 0.0
    v = hsv[..., 2].astype(np.float32)
    return float(np.count_nonzero(v >= min_val) / v.size)


def _hp_bar_ratio(hsv: np.ndarray, th: PartyStateThresholds) -> float:
    """Estimate HP fill ratio from a horizontal bar crop.

    Per column, mark it 'filled' if any pixel clears the lit S/V floor (the HP
    fill is bright green/white over a dark track). Ratio = filled cols / total.
    """
    if hsv.size == 0 or hsv.shape[1] == 0:
        return 0.0
    s = hsv[..., 1].astype(np.float32)
    v = hsv[..., 2].astype(np.float32)
    lit = (v >= th.hp_lit_min_val) & (s >= th.hp_lit_min_sat)
    col_filled = lit.any(axis=0)
    return float(np.count_nonzero(col_filled) / col_filled.size)


def _slot_crops(party_hsv: np.ndarray, n: int) -> list[np.ndarray]:
    """Split a vertical party-portrait strip into ``n`` stacked card crops."""
    h = party_hsv.shape[0]
    if h < n or n <= 0:
        return [party_hsv] if party_hsv.size else []
    step = h // n
    return [party_hsv[i * step : (i + 1) * step] for i in range(n)]


class GenshinPartyStateReader:
    """Read per-character HP/energy/cooldown/active-slot from a Genshin frame.

    Usage (live tick)::

        reader = GenshinPartyStateReader()           # once, at wiring time
        party = reader.read(frame, observation)       # each combat tick
        reader.inject(observation, party)             # stash into extensions
        view = build_combat_view(observation, screen) # now multi-char

    The reader is intentionally conservative: only the *active* character's Q
    ring, E cooldown, and HP bar are visible on the HUD, so off-field chars get
    safe defaults (skill/burst NOT ready, energy 0.0, hp 1.0). This still lets
    the controller burst/skill/heal on the active char instead of only attacking,
    while never inventing a phantom off-field burst.
    """

    def __init__(
        self,
        *,
        rois: dict[str, tuple[float, float, float, float]] | None = None,
        thresholds: PartyStateThresholds | None = None,
        profile: dict[str, Any] | str | Path | None = None,
        roster: tuple[tuple[str, str, str], ...] | None = None,
    ) -> None:
        """
        :param rois: explicit normalized ROIs (overrides ``profile``).
        :param thresholds: tunable CV thresholds (overrides defaults).
        :param profile: profile dict/path to load ROIs from when ``rois`` absent.
        :param roster: optional ``(name, element, role)`` per slot from the team
            profile. Element/role are NOT visually derivable yet (residual), so
            the integrator should pass the active team; absent => generic dps.
        """
        self._rois = rois if rois is not None else load_party_rois(profile)
        self._th = thresholds or PartyStateThresholds()
        self._roster = roster

    def read(self, frame: Any, observation: Any = None) -> PartyState:
        """Read party state from a single BGR frame.

        Returns a :class:`PartyState` whose ``chars`` is ready to feed straight
        into ``build_combat_view``. Never raises on a malformed frame: an empty
        or non-image frame yields a single safe DPS placeholder.
        """
        th = self._th
        notes: list[str] = []
        n = max(1, th.party_size)

        if not isinstance(frame, np.ndarray) or frame.ndim < 2 or frame.size == 0:
            notes.append("no_frame")
            return PartyState(chars=self._safe_single(), active_index=0,
                              confidence=0.0, notes=tuple(notes))
        if cv2 is None:
            notes.append("cv2_missing_numpy_fallback")

        # --- active card detection (brightness of each stacked card) ---------
        party_hsv = _to_hsv(_crop(frame, self._rois["party_portraits"]))
        active_index = 0
        if party_hsv is not None and party_hsv.size:
            crops = _slot_crops(party_hsv, n)
            brightness = [float(c[..., 2].mean()) if c.size else 0.0 for c in crops]
            if brightness:
                order = sorted(range(len(brightness)), key=lambda i: brightness[i],
                               reverse=True)
                top = order[0]
                runner = brightness[order[1]] if len(order) > 1 else 0.0
                clear = brightness[top] >= th.active_min_brightness and (
                    runner <= 0.0 or brightness[top] >= runner * th.active_dominance_ratio
                )
                active_index = top if clear else 0
                if not clear:
                    notes.append("active_card_ambiguous_default0")
        else:
            notes.append("party_roi_empty")

        # --- active char: Q ring (burst), E icon (skill), HP bar -------------
        q_hsv = _to_hsv(_crop(frame, self._rois["skill_q_icon"]))
        burst_ready = False
        energy_ratio = 0.0
        if q_hsv is not None and q_hsv.size:
            energy_ratio = _ring_fill_fraction(q_hsv, th)
            burst_ready = energy_ratio >= th.burst_ready_fill
        else:
            notes.append("q_roi_empty")

        e_hsv = _to_hsv(_crop(frame, self._rois["skill_e_icon"]))
        skill_ready = False
        if e_hsv is not None and e_hsv.size:
            skill_ready = _icon_lit_fraction(e_hsv, th.skill_lit_min_val) >= th.skill_ready_fill
        else:
            notes.append("e_roi_empty")

        hp_hsv = _to_hsv(_crop(frame, self._rois["active_char_hp"]))
        active_hp = 1.0
        if hp_hsv is not None and hp_hsv.size:
            active_hp = max(0.0, min(1.0, _hp_bar_ratio(hp_hsv, th)))
        else:
            notes.append("hp_roi_empty")

        chars = self._build_chars(
            n=n,
            active_index=active_index,
            active_hp=active_hp,
            active_energy=energy_ratio,
            active_skill_ready=skill_ready,
            active_burst_ready=burst_ready,
        )

        # Confidence: high when all four ROIs read; degrade per missing ROI.
        empty = sum(1 for note in notes if note.endswith("_empty"))
        confidence = max(0.0, 1.0 - 0.25 * empty)
        if cv2 is None:
            confidence *= 0.8
        return PartyState(chars=chars, active_index=active_index,
                          confidence=confidence, notes=tuple(notes))

    def _build_chars(
        self,
        *,
        n: int,
        active_index: int,
        active_hp: float,
        active_energy: float,
        active_skill_ready: bool,
        active_burst_ready: bool,
    ) -> tuple[CombatCharView, ...]:
        """Assemble per-slot CombatCharViews.

        Only the active slot gets read signals; off-field slots get safe
        defaults (skill/burst NOT ready, energy 0.0, hp 1.0) because their state
        is not on the HUD (residual). Name/element/role come from the roster when
        supplied, else a generic dps placeholder.
        """
        out: list[CombatCharView] = []
        for i in range(n):
            if self._roster and i < len(self._roster):
                name, element, role = self._roster[i]
            else:
                name, element, role = (f"slot{i}", "physical", "dps")
            if i == active_index:
                out.append(CombatCharView(
                    index=i, name=name, element=element,
                    hp_ratio=active_hp, energy_ratio=active_energy,
                    skill_ready=active_skill_ready, burst_ready=active_burst_ready,
                    role=role,
                ))
            else:
                out.append(CombatCharView(
                    index=i, name=name, element=element,
                    hp_ratio=1.0, energy_ratio=0.0,
                    skill_ready=False, burst_ready=False, role=role,
                ))
        return tuple(out)

    @staticmethod
    def _safe_single() -> tuple[CombatCharView, ...]:
        """Single conservative DPS — nothing ready, so controller falls to attack."""
        return (CombatCharView(
            index=0, name="active", element="physical",
            hp_ratio=1.0, energy_ratio=0.0, skill_ready=False,
            burst_ready=False, role="dps",
        ),)

    def inject(self, observation: Any, party: PartyState) -> PartyState:
        """Store ``party`` into ``observation.extensions`` for the combat view.

        Writes the controller-ready tuple under ``"party_state"`` (chars) and the
        active index under ``"party_active_index"`` so
        :func:`build_combat_view` can pick them up when no ``chars`` are passed.
        Also keeps the full :class:`PartyState` under ``"party_state_full"`` for
        telemetry / debugging. Never raises.
        """
        try:
            ext = getattr(observation, "extensions", None)
            if ext is None:
                return party
            ext["party_state"] = party.chars
            ext["party_active_index"] = party.active_index
            ext["party_state_full"] = party
        except Exception:  # pragma: no cover - defensive
            pass
        return party
