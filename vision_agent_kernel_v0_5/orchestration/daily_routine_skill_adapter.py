"""Orchestrate the 3-layer daily routine loop.

Layer 1 (Quick, ~15min): Mail → Commissions ×4 → Katherine → Resin spend → Parametric
Layer 2 (Standard, ~45min): + Boss materials, talent/weapon domains, expeditions
Layer 3 (Deep, ~60min): + Shop purchases, BP tasks, artifact enhancement batch

Coordinates UIFlowSkillAdapter, CombatSkillAdapter, ExplorationSkillAdapter,
QuestSkillAdapter, and resource management modules.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)


class SkillExecutor(Protocol):
    def execute_semantic(self, action: str, target: str = "", context: dict[str, Any] | None = None) -> bool: ...


@dataclass(frozen=True, slots=True)
class DailyRoutineConfig:
    max_commissions: int = 4
    resin_threshold_urgent: int = 160
    resin_threshold_normal: int = 80
    combat_timeout_sec: float = 240.0
    teleport_timeout_sec: float = 30.0
    commission_timeout_sec: float = 300.0


@dataclass(frozen=True, slots=True)
class DailyRoutineResult:
    layer: int
    success: bool
    commissions_done: int
    resin_spent: int
    katheryne_claimed: bool
    domains_done: int
    bosses_done: int
    errors: tuple[str, ...] = ()


class DailyRoutineSkillAdapter:
    """Orchestrate the complete daily routine across 3 layers.

    Each layer builds on the previous one:
    - Layer 1: Core daily (commissions + resin)
    - Layer 2: Extended (domains + bosses)
    - Layer 3: Deep (shop + BP + enhancement)
    """

    def __init__(
        self,
        *,
        skill_executor: SkillExecutor,
        combat_adapter: Any | None = None,
        config: DailyRoutineConfig | None = None,
    ) -> None:
        self._executor = skill_executor
        self._combat = combat_adapter
        self._config = config or DailyRoutineConfig()

    def execute_layer1(self, context: dict[str, Any] | None = None) -> DailyRoutineResult:
        """Quick daily: ~15 minutes. Mail → 4 Commissions → Katherine → Resin."""
        ctx = context or {}
        errors: list[str] = []
        commissions_done = 0
        resin_spent = 0
        katheryne_claimed = False

        log.info("[Daily] === Layer 1: Quick Daily ===")

        # Phase A: Check mail
        self._executor.execute_semantic("open_menu")
        log.info("[Daily] Phase A: Mail check")
        self._executor.execute_semantic("close_menu")

        # Phase B: Check commissions via quest menu
        log.info("[Daily] Phase B: Commission check")
        self._executor.execute_semantic("open_quest_menu")

        # Phase C: Complete 4 commissions
        log.info("[Daily] Phase C: Completing %d commissions", self._config.max_commissions)
        for i in range(self._config.max_commissions):
            log.info("[Daily] Commission %d/%d", i + 1, self._config.max_commissions)
            try:
                # Track commission
                self._executor.execute_semantic("track_quest", context={"semantic_action": "track_quest"})
                # Navigate to commission
                self._executor.execute_semantic("navigate_walk", context={"semantic_action": "navigate_walk"})
                # Execute commission (combat/collect/dialog variant)
                commission_type = ctx.get(f"commission_{i}_type", "combat")
                if commission_type == "combat":
                    self._execute_commission_combat()
                elif commission_type == "dialog":
                    self._execute_commission_dialog()
                else:
                    self._execute_commission_collect()
                commissions_done += 1
            except Exception as exc:
                err = f"commission_{i}_failed: {exc}"
                log.warning("[Daily] %s", err)
                errors.append(err)

        # Phase D: Katherine reward claim
        log.info("[Daily] Phase D: Katherine claim")
        try:
            self._executor.execute_semantic("teleport", "mondstadt")
            self._executor.execute_semantic("interact_npc")
            self._executor.execute_semantic("advance_dialog")
            self._executor.execute_semantic("claim_reward")
            katheryne_claimed = True
        except Exception as exc:
            errors.append(f"katheryne_failed: {exc}")

        # Phase E: Spend resin
        log.info("[Daily] Phase E: Resin spend")
        try:
            self._executor.execute_semantic("domain_enter_and_claim")
            resin_spent += 20
        except Exception as exc:
            errors.append(f"resin_spend_failed: {exc}")

        # Phase F: Wrap-up
        log.info("[Daily] Phase F: Wrap-up")
        self._executor.execute_semantic("close_menu")

        success = commissions_done >= self._config.max_commissions and katheryne_claimed
        log.info("[Daily] Layer 1 done: commissions=%d resin=%d katheryne=%s", commissions_done, resin_spent, katheryne_claimed)

        return DailyRoutineResult(
            layer=1,
            success=success,
            commissions_done=commissions_done,
            resin_spent=resin_spent,
            katheryne_claimed=katheryne_claimed,
            domains_done=0,
            bosses_done=0,
            errors=tuple(errors),
        )

    def execute_layer2(self, context: dict[str, Any] | None = None) -> DailyRoutineResult:
        """Standard daily: ~45 minutes. Layer 1 + domains + bosses."""
        layer1 = self.execute_layer1(context)

        errors = list(layer1.errors)
        domains_done = 0
        bosses_done = 0
        resin_spent = layer1.resin_spent

        log.info("[Daily] === Layer 2: Standard Daily ===")

        # Domain runs (talent/weapon domains based on day schedule)
        domain_count = (context or {}).get("domain_runs", 2)
        for i in range(domain_count):
            log.info("[Daily] Domain run %d/%d", i + 1, domain_count)
            try:
                self._executor.execute_semantic("domain_enter_and_claim")
                domains_done += 1
                resin_spent += 20
            except Exception as exc:
                errors.append(f"domain_{i}_failed: {exc}")

        # World boss
        boss_count = (context or {}).get("boss_runs", 1)
        for i in range(boss_count):
            log.info("[Daily] Boss run %d/%d", i + 1, boss_count)
            try:
                self._executor.execute_semantic("teleport", "world_boss")
                if self._combat is not None:
                    self._combat.execute_combat(
                        team_elements=["pyro", "hydro", "cryo", "anemo"],
                        team_characters=["dps", "support", "sub_dps", "flex"],
                        enemy_id="world_boss",
                    )
                else:
                    self._executor.execute_semantic("attack", context={"semantic_action": "attack"})
                bosses_done += 1
                resin_spent += 40
            except Exception as exc:
                errors.append(f"boss_{i}_failed: {exc}")

        success = layer1.success and domains_done > 0
        log.info("[Daily] Layer 2 done: domains=%d bosses=%d resin=%d", domains_done, bosses_done, resin_spent)

        return DailyRoutineResult(
            layer=2,
            success=success,
            commissions_done=layer1.commissions_done,
            resin_spent=resin_spent,
            katheryne_claimed=layer1.katheryne_claimed,
            domains_done=domains_done,
            bosses_done=bosses_done,
            errors=tuple(errors),
        )

    def execute_layer3(self, context: dict[str, Any] | None = None) -> DailyRoutineResult:
        """Deep daily: ~60 minutes. Layer 2 + shop + BP + enhancement."""
        layer2 = self.execute_layer2(context)

        errors = list(layer2.errors)

        log.info("[Daily] === Layer 3: Deep Daily ===")

        # Shop purchases (Paimon bargains - monthly fates)
        log.info("[Daily] Shop: Paimon bargains")
        try:
            self._executor.execute_semantic("shop_open_paimon_bargains")
            self._executor.execute_semantic("shop_buy_monthly_fates")
        except Exception as exc:
            errors.append(f"shop_failed: {exc}")

        # BP tasks check
        log.info("[Daily] Battle pass check")
        try:
            self._executor.execute_semantic("open_battle_pass")
            self._executor.execute_semantic("claim_all")
            self._executor.execute_semantic("close_menu")
        except Exception as exc:
            errors.append(f"bp_failed: {exc}")

        # Artifact enhancement batch
        log.info("[Daily] Artifact enhancement")
        try:
            self._executor.execute_semantic("artifact_enhance_full")
        except Exception as exc:
            errors.append(f"enhance_failed: {exc}")

        log.info("[Daily] Layer 3 complete")

        return DailyRoutineResult(
            layer=3,
            success=layer2.success,
            commissions_done=layer2.commissions_done,
            resin_spent=layer2.resin_spent,
            katheryne_claimed=layer2.katheryne_claimed,
            domains_done=layer2.domains_done,
            bosses_done=layer2.bosses_done,
            errors=tuple(errors),
        )

    def _execute_commission_combat(self) -> None:
        """Execute a combat-type commission."""
        if self._combat is not None:
            self._combat.execute_combat(
                team_elements=["pyro", "hydro", "cryo", "anemo"],
                team_characters=["dps", "support", "sub_dps", "flex"],
                enemy_id="commission_enemy",
                duration_sec=self._config.commission_timeout_sec,
            )
        else:
            self._executor.execute_semantic("attack", context={"semantic_action": "attack"})
        self._executor.execute_semantic("claim_reward")

    def _execute_commission_dialog(self) -> None:
        """Execute a dialog-type commission."""
        self._executor.execute_semantic("interact_npc")
        self._executor.execute_semantic("advance_dialog")
        self._executor.execute_semantic("advance_dialog")

    def _execute_commission_collect(self) -> None:
        """Execute a collection-type commission."""
        for _ in range(5):
            self._executor.execute_semantic("interact", context={"semantic_action": "interact"})
        self._executor.execute_semantic("claim_reward")
