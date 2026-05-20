from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DangerState:
    score: float
    level: str
    components: dict[str, float]
    dominant_signal: str


class DangerDetector:
    def evaluate(self, signals: dict[str, float], context_priority: float = 0.0) -> DangerState:
        generic_warning = _clamp(signals.get("generic_warning_area", 0.0))
        projectile = _clamp(signals.get("projectile_approaching", 0.0))
        bbox_expand = _clamp(signals.get("target_bbox_fast_expand", 0.0))
        enemy_facing = _clamp(signals.get("enemy_facing_player", 0.0))
        hp_drop = _clamp(signals.get("hp_drop_signal", 0.0))
        scripted = _clamp(signals.get("scripted_testbed_danger", 0.0))
        priority = _clamp(context_priority)

        components = {
            "generic_warning_score": generic_warning * 0.25,
            "projectile_threat_score": projectile * 0.25,
            "distance_closing_score": max(bbox_expand, enemy_facing * 0.75) * 0.20,
            "hp_drop_score": hp_drop * 0.25,
            "scripted_testbed_score": scripted * 0.35,
            "combat_context_priority": priority * 0.20,
        }
        score = _clamp(sum(components.values()))
        level = "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.45 else "LOW"
        dominant_signal = max(components, key=components.get) if components else "none"
        return DangerState(score=score, level=level, components=components, dominant_signal=dominant_signal)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
