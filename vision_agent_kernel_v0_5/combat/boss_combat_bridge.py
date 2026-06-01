"""Boss combat bridge: wires BossCombatRuntime to StateBus.combat_signal + InputWorker.

Fixes P0.3 and P1.3 — connects the isolated BossCombatRuntime to the main loop.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from combat.boss_combat_runtime import BossCombatDecision, BossCombatInput, BossCombatRuntime
from core.types import InputLease

if TYPE_CHECKING:
    from combat.team_capability import TeamCombatPlan, TeamProfile
    from combat.boss_schema import BossProfile
    from core.state_bus import StateBus
    from execution.input_worker import InputWorker
    from reflex.scheduler import ReflexScheduler
    from combat.survival_runtime import SurvivalPolicyEngine

log = logging.getLogger(__name__)


def combat_signal_to_boss_input(
    signal: object,
    frame_id: int,
) -> BossCombatInput:
    """Convert a StateBus CombatSignal to BossCombatInput."""
    return BossCombatInput(
        frame_id=frame_id,
        boss_hp_ratio=getattr(signal, "enemy_hp_ratio", 1.0),
        danger_score=getattr(signal, "danger_score", 0.0),
        telegraph_type=getattr(signal, "boss_mechanic_active", ""),
        target_visible=getattr(signal, "enemy_visible", False),
        hp_ratios=[getattr(signal, "player_hp_ratio", 1.0)] * 4,
        combo_broken=getattr(signal, "combo_broken", False),
        combat_ended=False,
    )


class BossCombatBridge:
    """Live bridge between StateBus.combat_signal → BossCombatRuntime → InputWorker.

    Consumes CombatSignal from StateBus, converts to BossCombatInput, runs
    BossCombatRuntime.tick(), and submits resulting InputLease to InputWorker.
    """

    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        boss_profile: BossProfile | None,
        team_profile: TeamProfile,
        team_plan: TeamCombatPlan,
        survival_engine: SurvivalPolicyEngine | None = None,
        reflex: ReflexScheduler | None = None,
        tick_interval_sec: float = 0.15,
    ) -> None:
        self._bus = state_bus
        self._worker = input_worker
        self._runtime = BossCombatRuntime(
            boss_profile=boss_profile,
            team_profile=team_profile,
            team_plan=team_plan,
            survival_engine=survival_engine,
            reflex=reflex,
        )
        self._tick_interval = tick_interval_sec
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_frame_id = 0
        self._decision_count = 0

    @property
    def runtime(self) -> BossCombatRuntime:
        return self._runtime

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="boss-combat-bridge", daemon=True)
        self._thread.start()
        log.info("[BossCombatBridge] started")

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("[BossCombatBridge] stopped after %d decisions", self._decision_count)

    def tick_once(self) -> BossCombatDecision | None:
        """Single tick: read combat_signal → convert → tick → submit lease."""
        signal = self._bus.combat_signal.get()
        if signal is None:
            return None

        # Use timestamp as change detector instead of frame_id (which defaults to 0)
        timestamp = getattr(signal, "timestamp", 0.0)
        if timestamp == 0.0 and self._last_frame_id == 0:
            # First tick with default signal — process it anyway
            pass
        elif getattr(signal, "frame_id", 0) == self._last_frame_id and self._last_frame_id != 0:
            # Skip duplicate frame_id to avoid re-processing
            return None

        frame_id = getattr(signal, "frame_id", 0)
        self._last_frame_id = frame_id

        boss_input = combat_signal_to_boss_input(signal, frame_id)
        now = time.perf_counter()
        decision = self._runtime.tick(boss_input, now)
        self._decision_count += 1

        self._execute_decision(decision)
        return decision

    def _execute_decision(self, decision: BossCombatDecision) -> None:
        """Submit lease to InputWorker if present, or execute directly."""
        if decision.lease is not None:
            self._submit_lease(decision.lease)
        elif decision.action == "release_all":
            self._release_all()

    def _submit_lease(self, lease: InputLease) -> None:
        """Submit a lease from BossCombatRuntime to InputWorker."""
        try:
            ok = self._worker.submit_lease(lease)
            if ok:
                log.debug(
                    "[BossCombatBridge] lease submitted: %s action=%s",
                    lease.lease_id, lease.reason,
                )
            else:
                log.warning("[BossCombatBridge] lease rejected by InputWorker: %s", lease.lease_id)
        except Exception as exc:
            log.warning("[BossCombatBridge] lease submit failed: %s", exc)

    def _release_all(self) -> None:
        """Release all held inputs."""
        backend = self._worker.backend
        if hasattr(backend, "release_all"):
            try:
                backend.release_all(reason="boss_combat_release_all")
            except Exception as exc:
                log.warning("[BossCombatBridge] release_all failed: %s", exc)

    def _run(self) -> None:
        """Background loop: tick at regular intervals."""
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception as exc:
                log.warning("[BossCombatBridge] tick error: %s", exc)
            self._stop.wait(self._tick_interval)
