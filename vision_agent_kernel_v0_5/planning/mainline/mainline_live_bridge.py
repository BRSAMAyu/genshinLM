from __future__ import annotations

import logging
import time
from typing import Any

from core.state_bus import StateBus
from execution.input_worker import InputWorker
from execution.safe_window_backend import SafeWindowInputBackend
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter
from navigation.quest_marker_follower import QuestMarkerFollower
from navigation.minimap_quest_reader import MinimapQuestReader
from control.sentinel.somatic_state_supervisor import SomaticStateSupervisor
from control.sentinel.sentinel_runtime import SentinelRuntime
from planning.mainline.mission_graph_v4 import MissionGraphV4
from planning.mainline.mainline_runner import MainlineRunner, MissionRunResult
from planning.mainline.mainline_skill_executor import MainlineSkillExecutor
from bagel.runtime import BagelRuntime

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
    ) -> None:
        self._window_title = window_title
        self._bus = state_bus or StateBus()
        self._bagel = bagel or BagelRuntime()

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

        # 4. Initialize somatic state supervisor
        self._somatic_supervisor = SomaticStateSupervisor()
        self._sentinel = SentinelRuntime()

        # 5. Initialize UI Flow Skill Adapter
        self._skill_adapter = UIFlowSkillAdapter(
            state_bus=self._bus,
            input_worker=self._worker,
            quest_follower=self._quest_follower,
            somatic_supervisor=self._somatic_supervisor,
        )

        # 6. Initialize Mainline Skill Executor
        self._skill_executor = MainlineSkillExecutor(
            action_executor=self._skill_adapter,
            bagel_runtime=self._bagel,
            raise_on_failure=False,
        )

        # 7. Initialize MainlineRunner with the real skill executor
        self._runner = MainlineRunner(
            sentinel=self._sentinel,
            skill_execute_fn=self._skill_executor.execute_node_skill,
        )

    def execute_live_mission(self, graph: MissionGraphV4) -> MissionRunResult:
        """Locks window focus, monitors sentinel watchdogs, and executes the mission graph

        against the live game.
        """
        log.info("[MainlineLiveBridge] Preparing for live mission execution of graph: %s", graph.graph_id)
        self._ensure_foreground_focus()

        # Run the mission runner against the live game!
        result = self._runner.run(graph)

        log.info(
            "[MainlineLiveBridge] Live mission execution completed. Success: %s, duration: %.2fs",
            result.success,
            result.duration_sec,
        )
        return result

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

    def stop(self) -> None:
        if self._worker.is_alive:
            self._worker.stop()
