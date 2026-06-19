from __future__ import annotations

import logging
import time
from typing import Any

from core.state_bus import StateBus
from execution.crash_recovery import CrashCheckpoint, CrashRecoveryOrchestrator
from execution.input_worker import InputWorker
from execution.loading_waiter import LoadingWaiter
from execution.safe_window_backend import SafeWindowInputBackend
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter
from navigation.quest_marker_follower import QuestMarkerFollower
from navigation.minimap_quest_reader import MinimapQuestReader
from control.sentinel.somatic_state_supervisor import SomaticStateSupervisor
from control.sentinel.sentinel_runtime import SentinelRuntime
from planning.mainline.mission_graph_v4 import MissionGraphV4
from planning.mainline.mainline_runner import MainlineRunner, MissionRunResult
from planning.mainline.mainline_runner import (
    StateBusSnapshotProvider,
    DefaultClaimVerifier,
    MainlineCheckpointPublisher,
)
from planning.mainline.mainline_skill_executor import MainlineSkillExecutor
from bagel.runtime import BagelRuntime
from combat.boss_combat_bridge import BossCombatBridge
from combat.team_capability import TeamProfile, TeamCombatPlan, CharacterCapability
from planning.skill_registry import SkillRegistry
from planning.quest_state_machine import QuestStateMachine

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


class MainlineLiveBridge:
    """Connects the high-level MainlineRunner/SkillExecutor with the live physical game window

    through InputWorker, UIFlowSkillAdapter, QuestMarkerFollower, and SomaticStateSupervisor.
    """

    def __init__(
        self,
        window_title: str = "原神",
        state_bus: StateBus | None = None,
        input_worker: InputWorker | None = None,
        bagel: BagelRuntime | None = None,
        enable_bagel_experimental: bool = False,
        checkpoint_store: Any | None = None,
    ) -> None:
        self._window_title = window_title
        self._bus = state_bus or StateBus()
        self._enable_bagel_experimental = bool(enable_bagel_experimental or bagel is not None)
        self._bagel = bagel if bagel is not None else (BagelRuntime() if self._enable_bagel_experimental else None)

        # 1. Initialize physical window backend
        self._backend = SafeWindowInputBackend(
            target_window_title=window_title,
            pixels_per_degree=8.0,
            alt_window_titles=["Genshin Impact"],
        )

        # 2. Initialize input worker with window backend
        self._worker = input_worker or InputWorker(
            backend=self._backend,
            state_bus=self._bus,
            target_window_title=window_title,
        )
        if not self._worker.is_alive:
            self._worker.start()

        # 3. Initialize quest follower
        minimap_reader = MinimapQuestReader()
        self._quest_follower = QuestMarkerFollower(backend=self._backend, reader=minimap_reader)

        # 3b. Initialize screen classifier (for loading detection, state monitoring)
        #     Prefer capsule provider; fall back to direct import if capsule not installed.
        from capsules.detector_resolver import get_screen_classifier
        self._classifier = get_screen_classifier()

        # 3c. Initialize QuestStateMachine and publish initial state to StateBus
        self._quest_sm = QuestStateMachine()
        self._publish_quest_state()

        # 4. Initialize somatic state supervisor
        self._somatic_supervisor = SomaticStateSupervisor()
        self._sentinel = SentinelRuntime()

        # 5. Initialize SkillRegistry (enables composite combat/exploration/quest actions)
        self._skill_registry = SkillRegistry(skill_executor=None, state_bus=self._bus)

        # 5b. Initialize DecisionMemory for strategy learning
        from learning.decision_memory import DecisionMemory
        self._decision_memory = DecisionMemory()

        # 6. Initialize UI Flow Skill Adapter with skill_registry
        self._skill_adapter = UIFlowSkillAdapter(
            state_bus=self._bus,
            input_worker=self._worker,
            quest_follower=self._quest_follower,
            somatic_supervisor=self._somatic_supervisor,
            skill_registry=self._skill_registry,
        )
        # Wire registry executor back to adapter so composite actions flow correctly
        self._skill_registry.set_executor(self._skill_adapter)

        # 7. Initialize Mainline Skill Executor
        self._skill_executor = MainlineSkillExecutor(
            action_executor=self._skill_adapter,
            bagel_runtime=self._bagel,
            enable_bagel_attribution=self._enable_bagel_experimental,
            raise_on_failure=False,
        )

        # 8. Initialize BossCombatBridge (combat_signal → BossCombatRuntime → InputWorker)
        default_team = TeamProfile(
            characters=[CharacterCapability(
                character_id="traveler",
                slot=1,
                element="anemo",
                role="on_field_dps",
            )],
        )
        default_plan = TeamCombatPlan(
            conservative_level=1,
            main_chain=["anemo"],
            survival_chain=["dodge"],
            low_resource_chain=["normal_attack"],
            fallback_chain=["safe_abort"],
            reason="default_live_bridge",
        )
        self._boss_bridge = BossCombatBridge(
            state_bus=self._bus,
            input_worker=self._worker,
            boss_profile=None,
            team_profile=default_team,
            team_plan=default_plan,
        )

        # 9. Initialize MainlineRunner with Phase 8 closure: snapshot, claims, checkpoint
        snapshot_provider = StateBusSnapshotProvider(self._bus)
        if checkpoint_store is None:
            from runtime.session_checkpoint import CheckpointStore
            checkpoint_store = CheckpointStore()
        checkpoint_publisher = MainlineCheckpointPublisher(self._bus, disk_store=checkpoint_store)
        self._runner = MainlineRunner(
            sentinel=self._sentinel,
            skill_execute_fn=self._skill_executor.execute_node_skill,
            snapshot_provider=snapshot_provider,
            claim_verifier=DefaultClaimVerifier(),
            checkpoint_publisher=checkpoint_publisher,
            enable_bagel_jit_router=self._enable_bagel_experimental,
            decision_memory=self._decision_memory,
        )

        # 10. Initialize crash recovery orchestrator and wire to runner (Issue #7)
        self._crash_recovery = CrashRecoveryOrchestrator(state_bus=self._bus)
        self._runner.set_crash_recovery_orchestrator(self._crash_recovery)

    def execute_live_mission(self, graph: MissionGraphV4) -> MissionRunResult:
        """Locks window focus, monitors sentinel watchdogs, and executes the mission graph

        against the live game. Pre-checks for loading screens before execution.
        On crash detection, delegates to CrashRecoveryOrchestrator before final failure.
        """
        log.info("[MainlineLiveBridge] Preparing for live mission execution of graph: %s", graph.graph_id)
        self._ensure_foreground_focus()

        # Pre-mission loading check — wait if game is mid-transition
        self._wait_if_loading()

        # Start combat bridge to consume combat_signal from perception
        self._boss_bridge.start()

        try:
            # Run the mission runner against the live game!
            result = self._runner.run(graph)
        finally:
            # Always stop combat bridge when mission ends
            self._boss_bridge.stop(timeout=2.0)

        # If runner failed due to crash, attempt recovery via CrashRecoveryOrchestrator
        if not result.success and self._crash_recovery.current_phase.value != "detect":
            log.warning(
                "[MainlineLiveBridge] Mission failed with crash in phase %s — "
                "running CrashRecoveryOrchestrator",
                self._crash_recovery.current_phase.value,
            )
            recovery_result = self._crash_recovery.execute_recovery_loop()
            log.info(
                "[MainlineLiveBridge] Crash recovery completed: success=%s, time=%.1fs",
                recovery_result.get("success", False),
                recovery_result.get("total_time_sec", 0.0),
            )

        # On success, advance quest state machine and publish updated state
        if result.success:
            self._quest_sm.advance(evidence="live_success")
            self._publish_quest_state()

        log.info(
            "[MainlineLiveBridge] Live mission execution completed. Success: %s, duration: %.2fs",
            result.success,
            result.duration_sec,
        )
        return result

    def _wait_if_loading(self, timeout: float = 30.0) -> bool:
        """Wait for any active loading screen to complete before proceeding."""
        waiter = LoadingWaiter(classifier=self._classifier, max_wait=timeout)
        try:
            return waiter.wait_for_load_complete(
                frame_source=self._backend.capture_frame,
            )
        except Exception as e:
            log.warning("[MainlineLiveBridge] Loading check failed (non-fatal): %s", e)
            return True

    def _ensure_foreground_focus(self) -> None:
        """Brings the target game window to the foreground."""
        log.info("[MainlineLiveBridge] Ensuring target window %r is focused", self._window_title)
        try:
            self._backend.focus_target_window()
            _chunked_sleep(0.5)  # brief wait for focus transition
            if not self._backend.is_target_focused():
                log.warning("[MainlineLiveBridge] Target window %r could not be focused", self._window_title)
        except Exception as e:
            log.error("[MainlineLiveBridge] Error bringing window to foreground: %s", e)

    def _publish_quest_state(self) -> None:
        """Publish current quest state to StateBus.quest_state for other components."""
        try:
            step = self._quest_sm.current_step
            state_data = {
                "quest_idx": self._quest_sm._current_quest_idx,
                "step_idx": self._quest_sm._current_step_idx,
                "current_step_id": step.step_id if step else None,
                "progress": self._quest_sm.progress,
                "mainline_complete": self._quest_sm.is_mainline_complete(),
            }
            self._bus.quest_state.put(state_data)
            log.debug("[MainlineLiveBridge] Published quest state: %s", state_data)
        except Exception:
            pass

    def stop(self) -> None:
        self._boss_bridge.stop(timeout=2.0)
        if self._worker.is_alive:
            self._worker.stop()
