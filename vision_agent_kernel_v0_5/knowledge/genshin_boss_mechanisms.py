"""Boss mechanic visual features extension (C-48, C-49, C-50, C-51).

Extends genshin_monsters.yaml with detailed visual feature definitions
for tracking boss-specific mechanics during weekly boss fights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Platform Sinking Visual Features (Dvalin C-48)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PlatformSinkingFeature:
    """Visual characteristics of a sinking platform."""
    crack_pattern: str           # "edge", "center", "radial"
    color_shift: tuple[int, int, int]  # RGB delta when sinking
    particle_density: float      # 0.0-1.0 falling particle intensity
    shake_frequency_hz: float     # Platform vibration frequency
    sink_rate_pct_per_sec: float  # How fast platform sinks


DVALIN_PLATFORM_FEATURES: dict[str, PlatformSinkingFeature] = {
    # Main platform (center tower)
    "main_platform": PlatformSinkingFeature(
        crack_pattern="radial",
        color_shift=(-30, -20, 10),  # Brownish shift
        particle_density=0.8,
        shake_frequency_hz=3.0,
        sink_rate_pct_per_sec=5.0,
    ),
    # Side platforms (left/right)
    "side_platform": PlatformSinkingFeature(
        crack_pattern="edge",
        color_shift=(-20, -15, 5),
        particle_density=0.5,
        shake_frequency_hz=4.0,
        sink_rate_pct_per_sec=8.0,  # Sinks faster
    ),
    # Bridge platforms
    "bridge_platform": PlatformSinkingFeature(
        crack_pattern="center",
        color_shift=(-40, -25, 15),
        particle_density=0.9,
        shake_frequency_hz=2.5,
        sink_rate_pct_per_sec=12.0,  # Very fast
    ),
}


# ---------------------------------------------------------------------------
# Form Transition Visual Signals (Childe C-49)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FormTransitionSignal:
    """Visual signal for boss form transition."""
    pre_transition_duration_ms: int    # How long warning appears before transition
    transition_duration_ms: int        # Duration of transition animation
    element_color: tuple[int, int, int]  # BGR color of form element
    weapon_visible: str                 # "sword", "bow", "spear"
    particle_effect: str                # Particle effect name
    aura_shape: str                    # "circle", "triangle", "none"


CHILDE_FORM_SIGNALS: dict[str, FormTransitionSignal] = {
    # Melee form (default)
    "melee": FormTransitionSignal(
        pre_transition_duration_ms=0,
        transition_duration_ms=0,
        element_color=(80, 60, 200),    # Hydro blue in BGR
        weapon_visible="sword",
        particle_effect="hydro_slash",
        aura_shape="none",
    ),
    # Ranged form
    "ranged": FormTransitionSignal(
        pre_transition_duration_ms=500,
        transition_duration_ms=800,
        element_color=(60, 120, 255),   # Bright hydro blue BGR
        weapon_visible="bow",
        particle_effect="hydro_arrow",
        aura_shape="circle",
    ),
    # Electro form (enraged)
    "electro": FormTransitionSignal(
        pre_transition_duration_ms=1000,
        transition_duration_ms=1500,
        element_color=(200, 50, 180),   # Electro purple BGR
        weapon_visible="spear",
        particle_effect="lightning_delusion",
        aura_shape="triangle",
    ),
}


# ---------------------------------------------------------------------------
# Temperature Gauge Visual Features (Signora C-50)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TempGaugeFeature:
    """Visual characteristics of temperature gauge."""
    gauge_position: tuple[float, float, float, float]  # x1, y1, x2, y2 normalized
    fill_direction: str                         # "right_to_left", "left_to_right", "bottom_to_top"
    gauge_colors: tuple[str, ...]               # Color stops for gauge fill
    threshold_colors: tuple[str, ...]           # Colors at danger thresholds


SIGNORA_TEMP_FEATURES: dict[str, TempGaugeFeature] = {
    # Heat gauge (for cryo phase)
    "heat_gauge": TempGaugeFeature(
        gauge_position=(0.72, 0.08, 0.93, 0.14),
        fill_direction="left_to_right",
        gauge_colors=("cyan", "yellow", "orange", "red"),
        threshold_colors=("normal", "warning", "danger", "critical"),
    ),
    # Cold gauge (for pyro phase)
    "cold_gauge": TempGaugeFeature(
        gauge_position=(0.72, 0.16, 0.93, 0.22),
        fill_direction="left_to_right",
        gauge_colors=("white", "light_blue", "blue", "dark_blue"),
        threshold_colors=("normal", "warning", "danger", "critical"),
    ),
}


# ---------------------------------------------------------------------------
# Raiden Eye Visual Detection (C-51)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RaidenEyeFeature:
    """Visual characteristics of Raiden eye attack telegraph."""
    eye_color_active: tuple[int, int, int]      # BGR color when eye is active
    eye_color_charging: tuple[int, int, int]    # BGR color during charge
    eye_color_inactive: tuple[int, int, int]    # BGR color when inactive
    charge_duration_ms: int                      # Time from charge start to attack
    sword_count: int                             # Number of swords that appear
    warning_text: str                            # Chinese warning text


RAIDEN_EYE_FEATURES: dict[str, RaidenEyeFeature] = {
    # Eye region on character model
    "character_eye": RaidenEyeFeature(
        eye_color_active=(200, 180, 255),        # Bright electro purple BGR
        eye_color_charging=(150, 100, 200),      # Charging purple BGR
        eye_color_inactive=(80, 80, 120),        # Dim inactive BGR
        charge_duration_ms=2500,                  # 2.5 second charge
        sword_count=3,                            # Three swords on field
        warning_text="无想的一刀",               # Warning text
    ),
}


# ---------------------------------------------------------------------------
# Boss Mechanism Integration (BOSS_PHASES extension)
# ---------------------------------------------------------------------------

# Extended mechanism info for BOSS_PHASES integration
BOSS_MECHANISM_EXTENSIONS: dict[str, dict[str, Any]] = {
    "dvalin": {
        "mechanism_type": "platform_tracking",
        "tracked_states": ["stable", "warning", "critical", "collapsed"],
        "visual_indicators": ["platform_color", "crack_pattern", "shake", "particles"],
        "critical_threshold": 0.3,  # Stability below 30% = critical
        "recommended_actions": {
            "stable": "engage_boss",
            "warning": "finish_attack_then_prepare",
            "critical": "evacuate_immediately",
            "collapsed": "find_alternate_platform",
        },
    },
    "childe": {
        "mechanism_type": "form_tracking",
        "tracked_forms": ["melee", "ranged", "electro"],
        "visual_indicators": ["weapon_visible", "element_color", "aura_shape", "particle_effect"],
        "form_durations": {
            "melee": 45.0,     # 45 seconds average
            "ranged": 25.0,   # 25 seconds average
            "electro": 15.0,  # 15 seconds (dangerous)
        },
        "recommended_actions": {
            "melee": "maintain_close_range",
            "ranged": "keep_distance",
            "electro": "burst_during_opening",
        },
    },
    "signora": {
        "mechanism_type": "temperature_tracking",
        "tracked_phases": ["cryo", "pyro"],
        "visual_indicators": ["gauge_fill", "thermometer_color", "collectible_spawn"],
        "phase_transition_threshold": 0.8,  # 80% gauge triggers phase change
        "dangerous_gauge_threshold": 0.9,  # 90% = very dangerous
        "recommended_actions": {
            "cryo_high_heat": "collect_cold_items",
            "pyro_high_cold": "collect_hot_items",
            "gauge_normal": "attack_boss",
        },
    },
    "raiden_shogun": {
        "mechanism_type": "eye_tracking",
        "tracked_states": ["inactive", "charging", "active", "cooldown"],
        "visual_indicators": ["eye_glow", "sword_count", "warning_text", "screen_effect"],
        "charge_duration_ms": 2500,
        "attack_duration_ms": 1500,
        "cooldown_duration_ms": 3000,
        "recommended_actions": {
            "inactive": "normal_attack",
            "charging": "prepare_dodge_or_iframe",
            "active": "wait_out_attack",
            "cooldown": "burst_window",
        },
    },
}


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def get_boss_mechanism_info(boss_id: str) -> dict[str, Any] | None:
    """Get boss mechanism info from extension data."""
    return BOSS_MECHANISM_EXTENSIONS.get(boss_id)


def get_platform_feature(platform_type: str) -> PlatformSinkingFeature | None:
    """Get platform sinking features for Dvalin."""
    return DVALIN_PLATFORM_FEATURES.get(platform_type)


def get_form_signal(form: str) -> FormTransitionSignal | None:
    """Get form transition signal for Childe."""
    return CHILDE_FORM_SIGNALS.get(form)


def get_temp_gauge_feature(gauge_type: str) -> TempGaugeFeature | None:
    """Get temperature gauge features for Signora."""
    return SIGNORA_TEMP_FEATURES.get(gauge_type)


def get_raiden_eye_feature(eye_type: str = "character_eye") -> RaidenEyeFeature | None:
    """Get Raiden eye features."""
    return RAIDEN_EYE_FEATURES.get(eye_type)