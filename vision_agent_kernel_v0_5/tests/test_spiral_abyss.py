"""Tests for combat aiming and Spiral Abyss systems (C-06, C-25~C-28)."""
from __future__ import annotations

import pytest

from combat.spiral_abyss import (
    AbyssBlessing,
    AbyssChamber,
    AbyssCharacter,
    AbyssFloorState,
    AbyssRoom,
    AbyssTeam,
    AbyssTeamRole,
    AimDecision,
    AimTarget,
    BowAimController,
    ChamberStatus,
    SpiralAbyssBlessingSelector,
    SpiralAbyssRunner,
    SpiralAbyssRoomAnalyzer,
    SpiralAbyssTeamBuilder,
    WeakPointType,
)


# ---------------------------------------------------------------------------
# BowAimController (C-06)
# ---------------------------------------------------------------------------
class TestBowAimController:
    def test_start_aiming(self) -> None:
        ctrl = BowAimController()
        dec = ctrl.start_aiming()
        assert dec.action == "aim"
        assert ctrl.state.is_aiming

    def test_cancel_aim(self) -> None:
        ctrl = BowAimController()
        ctrl.start_aiming()
        dec = ctrl.cancel_aim()
        assert dec.action == "cancel"
        assert not ctrl.state.is_aiming

    def test_no_target_cancels(self) -> None:
        ctrl = BowAimController()
        ctrl.start_aiming()
        dec = ctrl.update(None, 0)
        assert dec.action == "cancel"

    def test_charging(self) -> None:
        ctrl = BowAimController()
        ctrl.start_aiming()
        target = AimTarget(position=(500, 300), weak_point=WeakPointType.HEAD)
        dec = ctrl.update(target, 500)
        assert dec.action == "charge"
        assert ctrl.state.charge_level == pytest.approx(1.0 / 3.0)

    def test_fully_charged_release(self) -> None:
        ctrl = BowAimController(charge_time_ms=1000)
        ctrl.start_aiming()
        target = AimTarget(position=(500, 300), weak_point=WeakPointType.HEAD,
                           confidence=0.9)
        dec = ctrl.update(target, 1000)
        assert dec.action == "release"
        assert ctrl.state.should_release

    def test_moving_target_waits(self) -> None:
        ctrl = BowAimController(charge_time_ms=1000)
        ctrl.start_aiming()
        target = AimTarget(position=(500, 300), weak_point=WeakPointType.HEAD,
                           confidence=0.5)
        dec = ctrl.update(target, 1000, target_moving=True)
        assert dec.action == "charge"

    def test_not_aiming_returns_aim(self) -> None:
        ctrl = BowAimController()
        target = AimTarget(position=(500, 300), weak_point=WeakPointType.HEAD)
        dec = ctrl.update(target, 1000)
        assert dec.action == "aim"


# ---------------------------------------------------------------------------
# AbyssTeam (C-25)
# ---------------------------------------------------------------------------
class TestAbyssTeam:
    def _make_team(self) -> AbyssTeam:
        return AbyssTeam(
            team_id=1,
            characters=[
                AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
                AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
                AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
                AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
            ],
        )

    def test_is_valid(self) -> None:
        team = self._make_team()
        assert team.is_valid

    def test_not_valid_too_few(self) -> None:
        team = AbyssTeam(team_id=1, characters=[
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
        ])
        assert not team.is_valid

    def test_elements(self) -> None:
        team = self._make_team()
        assert "pyro" in team.elements
        assert "hydro" in team.elements

    def test_has_healer(self) -> None:
        team = self._make_team()
        assert team.has_healer

    def test_no_healer(self) -> None:
        team = AbyssTeam(team_id=1, characters=[
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
            AbyssCharacter("fischl", "electro", AbyssTeamRole.SUB_DPS),
        ])
        assert not team.has_healer

    def test_dps_element(self) -> None:
        team = self._make_team()
        assert team.dps_element == "pyro"

    def test_has_shield(self) -> None:
        team = AbyssTeam(team_id=1, characters=[
            AbyssCharacter("zhongli", "geo", AbyssTeamRole.SHIELD),
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
        ])
        assert team.has_shield


# ---------------------------------------------------------------------------
# SpiralAbyssTeamBuilder (C-25)
# ---------------------------------------------------------------------------
class TestSpiralAbyssTeamBuilder:
    def _make_roster(self, count: int = 10) -> list[AbyssCharacter]:
        chars = [
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("raidenshogun", "electro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("fischl", "electro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
            AbyssCharacter("xiangling", "pyro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
            AbyssCharacter("zhongli", "geo", AbyssTeamRole.SHIELD),
            AbyssCharacter("mona", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("barbara", "hydro", AbyssTeamRole.HEALER),
        ]
        return chars[:count]

    def test_build_teams_success(self) -> None:
        builder = SpiralAbyssTeamBuilder()
        result = builder.build_teams(self._make_roster(10))
        assert result is not None
        t1, t2 = result
        assert t1.is_valid
        assert t2.is_valid

    def test_insufficient_characters(self) -> None:
        builder = SpiralAbyssTeamBuilder()
        result = builder.build_teams(self._make_roster(6))
        assert result is None

    def test_insufficient_dps(self) -> None:
        chars = [
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUPPORT),
            AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
            AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
            AbyssCharacter("zhongli", "geo", AbyssTeamRole.SHIELD),
            AbyssCharacter("fischl", "electro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("mona", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("barbara", "hydro", AbyssTeamRole.HEALER),
        ]
        builder = SpiralAbyssTeamBuilder()
        result = builder.build_teams(chars)
        assert result is None  # Only 1 DPS

    def test_unbuilt_characters_excluded(self) -> None:
        chars = self._make_roster(10)
        chars[1].is_built = False  # 2nd DPS unbuilt
        builder = SpiralAbyssTeamBuilder()
        result = builder.build_teams(chars)
        assert result is None  # Only 1 built DPS

    def test_each_team_has_sustain(self) -> None:
        builder = SpiralAbyssTeamBuilder()
        result = builder.build_teams(self._make_roster(10))
        assert result is not None
        t1, t2 = result
        # At least one team should have healer or shield
        assert t1.has_healer or t2.has_healer


# ---------------------------------------------------------------------------
# SpiralAbyssRoomAnalyzer (C-26)
# ---------------------------------------------------------------------------
class TestSpiralAbyssRoomAnalyzer:
    def test_shield_counter(self) -> None:
        analyzer = SpiralAbyssRoomAnalyzer()
        room = AbyssRoom(room_id=1, element_shields=["hydro"])
        result = analyzer.analyze_room(room)
        assert "shield_counters" in result

    def test_aoe_tactics(self) -> None:
        analyzer = SpiralAbyssRoomAnalyzer()
        room = AbyssRoom(room_id=1, enemy_count=8)
        result = analyzer.analyze_room(room)
        assert result["tactics"] == "aoe_focus"

    def test_single_target(self) -> None:
        analyzer = SpiralAbyssRoomAnalyzer()
        room = AbyssRoom(room_id=1, enemy_count=1)
        result = analyzer.analyze_room(room)
        assert result["tactics"] == "single_target_burst"

    def test_balanced(self) -> None:
        analyzer = SpiralAbyssRoomAnalyzer()
        room = AbyssRoom(room_id=1, enemy_count=3)
        result = analyzer.analyze_room(room)
        assert result["tactics"] == "balanced"


# ---------------------------------------------------------------------------
# SpiralAbyssBlessingSelector (C-27)
# ---------------------------------------------------------------------------
class TestSpiralAbyssBlessingSelector:
    def test_select_best_synergy(self) -> None:
        selector = SpiralAbyssBlessingSelector()
        blessings = [
            AbyssBlessing("b1", "Pyro Boost", buff_type="atk", element_affinity="pyro"),
            AbyssBlessing("b2", "Cryo Boost", buff_type="atk", element_affinity="cryo"),
        ]
        team1 = AbyssTeam(team_id=1, characters=[
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
            AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
        ])
        team2 = AbyssTeam(team_id=2, characters=[
            AbyssCharacter("raidenshogun", "electro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("fischl", "electro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("xiangling", "pyro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("zhongli", "geo", AbyssTeamRole.SHIELD),
        ])
        result = selector.select_blessing(blessings, team1, team2)
        assert result is not None
        assert result.blessing_id == "b1"  # Pyro synergy with both teams

    def test_no_blessings(self) -> None:
        selector = SpiralAbyssBlessingSelector()
        team = AbyssTeam(team_id=1, characters=[])
        assert selector.select_blessing([], team, team) is None


# ---------------------------------------------------------------------------
# AbyssBlessing synergy
# ---------------------------------------------------------------------------
class TestAbyssBlessingSynergy:
    def test_element_match_boost(self) -> None:
        b = AbyssBlessing("b1", "Pyro", buff_type="atk", element_affinity="pyro")
        score = b.synergy_score(["pyro", "hydro"])
        assert score > 1.0

    def test_no_match_base(self) -> None:
        b = AbyssBlessing("b1", "Cryo", buff_type="atk", element_affinity="cryo")
        score = b.synergy_score(["pyro", "hydro"])
        assert score == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# SpiralAbyssRunner (C-28)
# ---------------------------------------------------------------------------
class TestSpiralAbyssRunner:
    def _make_roster(self) -> list[AbyssCharacter]:
        return [
            AbyssCharacter("hutao", "pyro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("raidenshogun", "electro", AbyssTeamRole.MAIN_DPS),
            AbyssCharacter("xingqiu", "hydro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("fischl", "electro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("sucrose", "anemo", AbyssTeamRole.SUPPORT),
            AbyssCharacter("xiangling", "pyro", AbyssTeamRole.SUB_DPS),
            AbyssCharacter("bennett", "pyro", AbyssTeamRole.HEALER),
            AbyssCharacter("zhongli", "geo", AbyssTeamRole.SHIELD),
        ]

    def _make_chambers(self) -> list[AbyssChamber]:
        return [
            AbyssChamber(chamber_id=1, first_half=AbyssRoom(room_id=1, enemy_count=3),
                         second_half=AbyssRoom(room_id=2, enemy_count=2)),
            AbyssChamber(chamber_id=2, first_half=AbyssRoom(room_id=1, enemy_count=4),
                         second_half=AbyssRoom(room_id=2, enemy_count=3)),
            AbyssChamber(chamber_id=3, first_half=AbyssRoom(room_id=1, enemy_count=1),
                         second_half=AbyssRoom(room_id=2, enemy_count=1)),
        ]

    def test_prepare_floor(self) -> None:
        runner = SpiralAbyssRunner()
        state = runner.prepare_floor(12, self._make_roster(), self._make_chambers())
        assert state.floor_number == 12
        assert state.team1 is not None
        assert state.team2 is not None
        assert len(state.chambers) == 3

    def test_advance_chamber(self) -> None:
        runner = SpiralAbyssRunner()
        state = runner.prepare_floor(12, self._make_roster(), self._make_chambers())
        result = runner.advance_chamber(state, stars=3)
        assert state.total_stars == 3
        assert state.chambers[0].status == ChamberStatus.COMPLETED

    def test_complete_all_chambers(self) -> None:
        runner = SpiralAbyssRunner()
        state = runner.prepare_floor(12, self._make_roster(), self._make_chambers())
        runner.advance_chamber(state, 3)
        runner.advance_chamber(state, 3)
        runner.advance_chamber(state, 2)
        assert state.is_complete
        assert state.total_stars == 8

    def test_fail_chamber(self) -> None:
        runner = SpiralAbyssRunner()
        state = runner.prepare_floor(12, self._make_roster(), self._make_chambers())
        result = runner.fail_chamber(state)
        assert result == ChamberStatus.FAILED
        assert state.chambers[0].status == ChamberStatus.FAILED

    def test_max_possible_stars(self) -> None:
        runner = SpiralAbyssRunner()
        state = runner.prepare_floor(12, self._make_roster(), self._make_chambers())
        assert state.max_possible_stars == 9


# ---------------------------------------------------------------------------
# AbyssFloorState
# ---------------------------------------------------------------------------
class TestAbyssFloorState:
    def test_current_chamber_first(self) -> None:
        chambers = [
            AbyssChamber(chamber_id=1),
            AbyssChamber(chamber_id=2),
        ]
        state = AbyssFloorState(floor_number=12, chambers=chambers)
        assert state.current_chamber is not None
        assert state.current_chamber.chamber_id == 1

    def test_current_chamber_after_completion(self) -> None:
        chambers = [
            AbyssChamber(chamber_id=1, status=ChamberStatus.COMPLETED),
            AbyssChamber(chamber_id=2),
        ]
        state = AbyssFloorState(floor_number=12, chambers=chambers)
        assert state.current_chamber is not None
        assert state.current_chamber.chamber_id == 2

    def test_no_current_chamber_when_complete(self) -> None:
        chambers = [
            AbyssChamber(chamber_id=1, status=ChamberStatus.COMPLETED),
            AbyssChamber(chamber_id=2, status=ChamberStatus.COMPLETED),
        ]
        state = AbyssFloorState(floor_number=12, chambers=chambers)
        assert state.current_chamber is None
        assert state.is_complete
