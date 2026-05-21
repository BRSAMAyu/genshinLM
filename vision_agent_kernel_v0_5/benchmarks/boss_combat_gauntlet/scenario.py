from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BossBenchFrame:
    boss_hp_ratio: float
    danger_score: float
    telegraph_type: str = ""
    target_visible: bool = True
    hp_ratios: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    combo_broken: bool = False
    combat_ended: bool = False


@dataclass(frozen=True, slots=True)
class BossBenchScenario:
    name: str
    group: str
    boss_id: str
    team_characters: list[str]
    team_elements: list[str]
    frames: list[BossBenchFrame]
    expected_clear: bool = True
    expected_safe_abort: bool = False
    expected_heal: bool = False
    expected_reacquire: bool = False


SCENARIOS: list[BossBenchScenario] = [
    BossBenchScenario(
        name="ground_aoe_clear",
        group="boss_pattern",
        boss_id="aoe_boss",
        team_characters=["hu_tao", "xingqiu", "zhongli", "albedo"],
        team_elements=["pyro", "hydro", "geo", "geo"],
        frames=[
            BossBenchFrame(0.95, 0.8, "ground_danger_zone"),
            BossBenchFrame(0.95, 0.1, "ground_danger_zone"),
            BossBenchFrame(0.75, 0.1, ""),
            BossBenchFrame(0.04, 0.0, "", combat_ended=True),
        ],
    ),
    BossBenchScenario(
        name="projectile_target_reacquire",
        group="boss_pattern",
        boss_id="projectile_boss",
        team_characters=["xiangling", "bennett", "xingqiu", "sucrose"],
        team_elements=["pyro", "pyro", "hydro", "anemo"],
        frames=[
            BossBenchFrame(0.8, 0.75, "projectile_approaching"),
            BossBenchFrame(0.8, 0.0, "projectile_approaching", target_visible=False),
            BossBenchFrame(0.6, 0.1, "", target_visible=True),
            BossBenchFrame(0.03, 0.0, "", combat_ended=True),
        ],
        expected_reacquire=True,
    ),
    BossBenchScenario(
        name="team_no_healer_survives_conservative",
        group="team_diversity",
        boss_id="aoe_boss",
        team_characters=["diluc", "fischl", "xiangling", "sucrose"],
        team_elements=["pyro", "electro", "pyro", "anemo"],
        frames=[
            BossBenchFrame(0.9, 0.1, "", hp_ratios=[0.3, 0.8, 0.8, 0.8]),
            BossBenchFrame(0.7, 0.1, ""),
            BossBenchFrame(0.05, 0.0, "", combat_ended=True),
        ],
    ),
    BossBenchScenario(
        name="emergency_hp_blocks_food_during_danger",
        group="survival",
        boss_id="phase_shift_boss",
        team_characters=["unknown_pyro", "unknown_hydro"],
        team_elements=["pyro", "hydro"],
        frames=[
            BossBenchFrame(0.7, 0.9, "boss_windup", hp_ratios=[0.12, 0.7]),
            BossBenchFrame(0.7, 0.1, "boss_windup", hp_ratios=[0.12, 0.7]),
            BossBenchFrame(0.03, 0.0, "", hp_ratios=[0.6, 0.7], combat_ended=True),
        ],
    ),
    BossBenchScenario(
        name="food_profile_missing_safe_abort",
        group="survival",
        boss_id="projectile_boss",
        team_characters=["unknown_pyro"],
        team_elements=["pyro"],
        frames=[
            BossBenchFrame(0.6, 0.1, "", hp_ratios=[0.1]),
        ],
        expected_clear=False,
        expected_safe_abort=True,
    ),
    BossBenchScenario(
        name="long_fight_phase_shift",
        group="long_fight",
        boss_id="phase_shift_boss",
        team_characters=["alhaitham", "nahida", "xingqiu", "kuki_shinobu"],
        team_elements=["dendro", "dendro", "hydro", "electro"],
        frames=[
            BossBenchFrame(0.95, 0.2, "teleport_slash"),
            BossBenchFrame(0.52, 0.65, "shield_flash"),
            BossBenchFrame(0.52, 0.1, "shield_flash"),
            BossBenchFrame(0.22, 0.8, "repeated_flash"),
            BossBenchFrame(0.22, 0.0, "repeated_flash"),
            BossBenchFrame(0.04, 0.0, "", combat_ended=True),
        ],
    ),
]
