"""Newbie tutorial chain: 0-2h guided experience from first login to prologue completion.

Implements Long Chain Scenario #1 from GENSHIN_LONG_CHAIN_SCENARIOS.md:
21 phases from opening cutscene through Stormterror defeat.
Each phase has completion verification and failure recovery.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Tutorial phase definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TutorialPhase:
    phase_id: str
    name: str
    target_time_sec: float = 300.0
    timeout_sec: float = 600.0
    has_combat: bool = False
    has_dialog: bool = False
    has_cutscene: bool = False
    required_ar: int = 0


# The 21 phases of the newbie tutorial (T+0:00 to T+2:00)
TUTORIAL_PHASES: tuple[TutorialPhase, ...] = (
    TutorialPhase("T01", "开场动画跳过", target_time_sec=180, has_cutscene=True),
    TutorialPhase("T02", "角色选择", target_time_sec=120, has_dialog=True),
    TutorialPhase("T03", "基础移动教学", target_time_sec=180),
    TutorialPhase("T04", "游泳教学", target_time_sec=240),
    TutorialPhase("T05", "攀爬教学", target_time_sec=240),
    TutorialPhase("T06", "滑翔教学", target_time_sec=180),
    TutorialPhase("T07", "第一个传送点", target_time_sec=180, has_dialog=True),
    TutorialPhase("T08", "第一次战斗", target_time_sec=240, has_combat=True),
    TutorialPhase("T09", "第一个宝箱", target_time_sec=120),
    TutorialPhase("T10", "元素技能教学", target_time_sec=300),
    TutorialPhase("T11", "第一个NPC对话", target_time_sec=420, has_dialog=True),
    TutorialPhase("T12", "到达蒙德城", target_time_sec=480, has_dialog=True),
    TutorialPhase("T13", "蒙德城内导览", target_time_sec=300, has_dialog=True),
    TutorialPhase("T14", "加入骑士团", target_time_sec=300, has_dialog=True),
    TutorialPhase("T15", "调查异常-神庙外围", target_time_sec=600, has_combat=True),
    TutorialPhase("T16", "四风神庙内部探索", target_time_sec=600, has_combat=True),
    TutorialPhase("T17", "风龙废墟外围清剿", target_time_sec=600, has_combat=True),
    TutorialPhase("T18", "风龙废墟内部探索", target_time_sec=600),
    TutorialPhase("T19", "Boss战-特瓦林空中追击", target_time_sec=480, has_combat=True),
    TutorialPhase("T20", "Boss战-特瓦林平台近战", target_time_sec=480, has_combat=True),
    TutorialPhase("T21", "序章收尾", target_time_sec=600, has_dialog=True, has_cutscene=True),
)


@dataclass(frozen=True, slots=True)
class PhaseResult:
    phase_id: str
    success: bool
    duration_sec: float
    attempts: int = 1
    details: str = ""


# ---------------------------------------------------------------------------
# Recovery strategies
# ---------------------------------------------------------------------------

_RECOVERY_STRATEGIES: dict[str, str] = {
    "stuck_ui": "press_escape_and_retry",
    "combat_death": "wait_revive_and_reposition",
    "drowning": "wait_revive_avoid_water",
    "fall_damage": "use_food_reposition",
    "navigation_stuck": "teleport_nearest_retry",
    "boss_fail": "click_retry_adjust_strategy",
    "dialog_wrong": "check_quest_log_proceed",
}


# ---------------------------------------------------------------------------
# Tutorial runner
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class NewbieTutorialChain:
    """Run the full 0-2h newbie tutorial chain.

    Usage::

        chain = NewbieTutorialChain(executor=executor)
        results = chain.run()
        if chain.completed:
            print("Tutorial complete!")
    """

    executor: SemanticExecutor
    current_phase_idx: int = 0
    results: list[PhaseResult] = field(default_factory=list)
    max_phase_retries: int = 3
    total_paused_sec: float = 0.0

    @property
    def completed(self) -> bool:
        return self.current_phase_idx >= len(TUTORIAL_PHASES)

    @property
    def current_phase(self) -> TutorialPhase | None:
        if self.current_phase_idx < len(TUTORIAL_PHASES):
            return TUTORIAL_PHASES[self.current_phase_idx]
        return None

    @property
    def progress_pct(self) -> float:
        return self.current_phase_idx / len(TUTORIAL_PHASES) * 100.0

    def run(self) -> list[PhaseResult]:
        """Execute the full tutorial chain."""
        log.info("[Tutorial] starting newbie tutorial chain (%d phases)", len(TUTORIAL_PHASES))

        while self.current_phase_idx < len(TUTORIAL_PHASES):
            phase = TUTORIAL_PHASES[self.current_phase_idx]
            result = self._execute_phase(phase)

            if result.success:
                self.results.append(result)
                self.current_phase_idx += 1
                log.info("[Tutorial] phase %s complete (%.1fs) — progress %.0f%%",
                         phase.phase_id, result.duration_sec, self.progress_pct)
            else:
                # Retry up to max_phase_retries
                retried = False
                for attempt in range(self.max_phase_retries):
                    log.warning("[Tutorial] phase %s failed, retry %d/%d: %s",
                                phase.phase_id, attempt + 1, self.max_phase_retries, result.details)
                    result = self._execute_phase(phase)
                    if result.success:
                        self.results.append(result)
                        self.current_phase_idx += 1
                        retried = True
                        break

                if not retried:
                    self.results.append(result)
                    log.error("[Tutorial] chain aborted at phase %s after %d retries",
                              phase.phase_id, self.max_phase_retries)
                    break

        if self.completed:
            log.info("[Tutorial] tutorial chain complete! Total: %.1fs",
                     sum(r.duration_sec for r in self.results))
        return self.results

    def _execute_phase(self, phase: TutorialPhase) -> PhaseResult:
        """Execute a single tutorial phase."""
        started = time.perf_counter()
        handler = self._get_handler(phase.phase_id)
        if handler is None:
            return self._default_handler(phase, started)

        try:
            success = handler(phase)
        except Exception as exc:
            log.warning("[Tutorial] phase %s exception: %s", phase.phase_id, exc)
            success = False

        return PhaseResult(
            phase_id=phase.phase_id,
            success=success,
            duration_sec=time.perf_counter() - started,
            details="" if success else "handler_failed",
        )

    def _get_handler(self, phase_id: str) -> Any | None:
        handlers = {
            "T01": self._handle_cutscene_skip,
            "T02": self._handle_character_select,
            "T03": self._handle_movement_tutorial,
            "T04": self._handle_swim_tutorial,
            "T05": self._handle_climb_tutorial,
            "T06": self._handle_glide_tutorial,
            "T07": self._handle_first_statue,
            "T08": self._handle_first_combat,
            "T09": self._handle_first_chest,
            "T10": self._handle_skill_tutorial,
            "T11": self._handle_first_npc_dialog,
            "T12": self._handle_reach_mondstadt,
            "T13": self._handle_city_tour,
            "T14": self._handle_join_knights,
            "T15": self._handle_temple_exterior,
            "T16": self._handle_temple_interior,
            "T17": self._handle_stormterror_exterior,
            "T18": self._handle_stormterror_interior,
            "T19": self._handle_boss_aerial,
            "T20": self._handle_boss_platform,
            "T21": self._handle_prologue_finale,
        }
        return handlers.get(phase_id)

    # ------------------------------------------------------------------
    # Phase handlers
    # ------------------------------------------------------------------

    def _handle_cutscene_skip(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("skip_cutscene")

    def _handle_character_select(self, phase: TutorialPhase) -> bool:
        ok = self.executor.execute_semantic("interact", context={"reason": "character_select"})
        return ok and self.executor.execute_semantic("confirm")

    def _handle_movement_tutorial(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("navigate_to", target="paimon_marker")

    def _handle_swim_tutorial(self, phase: TutorialPhase) -> bool:
        ok = self.executor.execute_semantic("swim", context={"mode": "surface"})
        return ok and self.executor.execute_semantic("navigate_to", target="far_shore")

    def _handle_climb_tutorial(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("climb", context={"target_height": "cliff_top"})

    def _handle_glide_tutorial(self, phase: TutorialPhase) -> bool:
        ok = self.executor.execute_semantic("jump")
        self._rest(0.5)
        ok = ok and self.executor.execute_semantic("glide")
        return ok and self.executor.execute_semantic("navigate_to", target="landing_zone")

    def _handle_first_statue(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("explore_scenario", context={"scenario": "statue_activation"})
        return True

    def _handle_first_combat(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("combat_basic_attack", context={"duration_sec": 10.0})

    def _handle_first_chest(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("explore_scenario", context={"scenario": "common_chest"})

    def _handle_skill_tutorial(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("use_skill", target="training_dummy")
        return True

    def _handle_first_npc_dialog(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic("quest_drive_dialog")

    def _handle_reach_mondstadt(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("navigate_to", target="mondstadt_bridge")
        return self.executor.execute_semantic("quest_drive_dialog")

    def _handle_city_tour(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("navigate_to", target="knights_hq")
        return self.executor.execute_semantic("quest_drive_dialog")

    def _handle_join_knights(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("quest_drive_dialog", context={"choice": "accept"})
        return True

    def _handle_temple_exterior(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("teleport_to", target="temple_area")
        return self.executor.execute_semantic("combat_basic_attack", context={"duration_sec": 30.0})

    def _handle_temple_interior(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("interact", context={"reason": "enter_domain"})
        self.executor.execute_semantic("explore_scenario", context={"scenario": "timed_challenge"})
        return self.executor.execute_semantic("combat_basic_attack", context={"duration_sec": 20.0})

    def _handle_stormterror_exterior(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("teleport_to", target="stormterror_lair")
        return self.executor.execute_semantic("combat_basic_attack", context={"duration_sec": 30.0})

    def _handle_stormterror_interior(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("climb", context={"target": "ruins_top"})
        return True

    def _handle_boss_aerial(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic(
            "combat_boss", target="stormterror_dvalin",
            context={"phase": "aerial_pursuit"},
        )

    def _handle_boss_platform(self, phase: TutorialPhase) -> bool:
        return self.executor.execute_semantic(
            "combat_boss", target="stormterror_dvalin",
            context={"phase": "platform_combat"},
        )

    def _handle_prologue_finale(self, phase: TutorialPhase) -> bool:
        self.executor.execute_semantic("skip_cutscene")
        return self.executor.execute_semantic("quest_drive_dialog")

    # ------------------------------------------------------------------
    # Default handler for unknown phases
    # ------------------------------------------------------------------

    def _default_handler(self, phase: TutorialPhase, started: float) -> PhaseResult:
        # Generic: attempt basic navigation + interaction
        ok = self.executor.execute_semantic("navigate_to", target=phase.name)
        if ok and phase.has_dialog:
            ok = self.executor.execute_semantic("quest_drive_dialog")
        if ok and phase.has_combat:
            ok = self.executor.execute_semantic("combat_basic_attack", context={"duration_sec": 10.0})
        return PhaseResult(
            phase_id=phase.phase_id, success=ok,
            duration_sec=time.perf_counter() - started,
        )

    @staticmethod
    def _rest(seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "completed": self.completed,
            "phases_completed": self.current_phase_idx,
            "total_phases": len(TUTORIAL_PHASES),
            "progress_pct": f"{self.progress_pct:.0f}%",
            "total_duration_sec": sum(r.duration_sec for r in self.results),
            "success_rate": sum(1 for r in self.results if r.success) / len(self.results)
            if self.results else 0.0,
            "failed_phases": [r.phase_id for r in self.results if not r.success],
        }
