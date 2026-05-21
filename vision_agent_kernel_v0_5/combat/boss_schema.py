from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class AttackPattern:
    pattern_id: str
    telegraph_signals: list[str]
    danger_type: str
    time_to_impact_ms: int
    safe_response: str
    priority: int = 50


@dataclass(frozen=True, slots=True)
class PunishWindow:
    window_id: str
    phase_id: str
    duration_ms: int
    recommended_action: str


@dataclass(frozen=True, slots=True)
class BossPhase:
    phase_id: str
    hp_min: float
    hp_max: float
    tactic: str
    attack_patterns: list[str] = field(default_factory=list)
    shield_state: str = ""

    def matches_hp(self, hp_ratio: float) -> bool:
        return self.hp_min <= hp_ratio <= self.hp_max


@dataclass(frozen=True, slots=True)
class BossProfile:
    boss_id: str
    display_name: str
    phases: list[BossPhase]
    attack_patterns: dict[str, AttackPattern]
    punish_windows: list[PunishWindow] = field(default_factory=list)
    elemental_resistance: dict[str, float] = field(default_factory=dict)
    shield_states: list[str] = field(default_factory=list)
    mobility_profile: str = "unknown"
    enrage_rules: list[str] = field(default_factory=list)
    recommended_reactions: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)

    def phase_for_hp(self, hp_ratio: float) -> BossPhase:
        for phase in self.phases:
            if phase.matches_hp(hp_ratio):
                return phase
        if not self.phases:
            return BossPhase("unknown", 0.0, 1.0, "safe_loop")
        return self.phases[-1] if hp_ratio < self.phases[-1].hp_min else self.phases[0]

    def pattern(self, pattern_id: str) -> AttackPattern | None:
        return self.attack_patterns.get(pattern_id)


@dataclass(frozen=True, slots=True)
class BossSignal:
    boss_id: str
    phase_id: str
    telegraph_type: str
    attack_pattern_id: str
    time_to_impact_ms: int
    safe_response: str
    confidence: float
    frame_id: int
    roi_id: str
    evidence_id: str


def conservative_unknown_boss(boss_id: str = "unknown_boss") -> BossProfile:
    pattern = AttackPattern(
        pattern_id="unknown_high_risk",
        telegraph_signals=["unknown_motion", "hp_drop", "generic_warning_area"],
        danger_type="unknown",
        time_to_impact_ms=250,
        safe_response="dodge_then_keep_distance",
        priority=0,
    )
    phase = BossPhase(
        phase_id="unknown",
        hp_min=0.0,
        hp_max=1.0,
        tactic="safe_loop",
        attack_patterns=[pattern.pattern_id],
    )
    return BossProfile(
        boss_id=boss_id,
        display_name=boss_id,
        phases=[phase],
        attack_patterns={pattern.pattern_id: pattern},
        mobility_profile="unknown",
        recommended_reactions=[],
        failure_modes=["UNKNOWN_BOSS_PROFILE"],
    )


def load_boss_profiles(path: str | Path) -> dict[str, BossProfile]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    profiles: dict[str, BossProfile] = {}
    for item in raw.get("bosses", []):
        patterns = {
            str(pattern["pattern_id"]): AttackPattern(
                pattern_id=str(pattern["pattern_id"]),
                telegraph_signals=list(pattern.get("telegraph_signals", [])),
                danger_type=str(pattern.get("danger_type", "unknown")),
                time_to_impact_ms=int(pattern.get("time_to_impact_ms", 300)),
                safe_response=str(pattern.get("safe_response", "dodge")),
                priority=int(pattern.get("priority", 50)),
            )
            for pattern in item.get("attack_patterns", [])
        }
        phases = [
            BossPhase(
                phase_id=str(phase["phase_id"]),
                hp_min=float(phase.get("hp_min", 0.0)),
                hp_max=float(phase.get("hp_max", 1.0)),
                tactic=str(phase.get("tactic", "safe_loop")),
                attack_patterns=list(phase.get("attack_patterns", [])),
                shield_state=str(phase.get("shield_state", "")),
            )
            for phase in item.get("phases", [])
        ]
        punish_windows = [
            PunishWindow(
                window_id=str(window["window_id"]),
                phase_id=str(window.get("phase_id", "")),
                duration_ms=int(window.get("duration_ms", 0)),
                recommended_action=str(window.get("recommended_action", "")),
            )
            for window in item.get("punish_windows", [])
        ]
        profile = BossProfile(
            boss_id=str(item["boss_id"]),
            display_name=str(item.get("display_name", item["boss_id"])),
            phases=phases,
            attack_patterns=patterns,
            punish_windows=punish_windows,
            elemental_resistance=dict(item.get("elemental_resistance", {})),
            shield_states=list(item.get("shield_states", [])),
            mobility_profile=str(item.get("mobility_profile", "unknown")),
            enrage_rules=list(item.get("enrage_rules", [])),
            recommended_reactions=list(item.get("recommended_reactions", [])),
            failure_modes=list(item.get("failure_modes", [])),
        )
        profiles[profile.boss_id] = profile
    return profiles


def boss_signal_from_observation(
    profile: BossProfile,
    *,
    hp_ratio: float,
    telegraph_type: str,
    frame_id: int,
    roi_id: str,
    confidence: float,
) -> BossSignal:
    phase = profile.phase_for_hp(hp_ratio)
    selected_pattern = ""
    for pattern_id in phase.attack_patterns:
        pattern = profile.pattern(pattern_id)
        if pattern and (telegraph_type in pattern.telegraph_signals or not selected_pattern):
            selected_pattern = pattern_id
            if telegraph_type in pattern.telegraph_signals:
                break
    pattern = profile.pattern(selected_pattern) if selected_pattern else None
    if pattern is None:
        fallback = conservative_unknown_boss(profile.boss_id)
        pattern = next(iter(fallback.attack_patterns.values()))
    return BossSignal(
        boss_id=profile.boss_id,
        phase_id=phase.phase_id,
        telegraph_type=telegraph_type,
        attack_pattern_id=pattern.pattern_id,
        time_to_impact_ms=pattern.time_to_impact_ms,
        safe_response=pattern.safe_response,
        confidence=confidence,
        frame_id=frame_id,
        roi_id=roi_id,
        evidence_id=f"boss:{profile.boss_id}:{phase.phase_id}:{frame_id}:{roi_id}",
    )
