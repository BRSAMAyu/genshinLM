"""Mainline API — cockpit endpoints for mission control.

Provides a dict-based API (no HTTP framework dependency) that the
desktop app or CLI can call to inspect and control the system.

Endpoints:
- get_state(): current quest context, mission graph, sentinel status
- start(mission_id): begin mission execution
- pause(): pause current mission
- stop(): stop and clean up
- get_claims(): claim graph summary
- get_bagel(): FIG and belief status
- get_skills(): skill registry and promotion status
- run_benchmark(task_id): execute benchmark task
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from bagel.fig_schema import FalsifiableInterventionGraph
from benchmarks.mainline_curriculum.metrics import BenchmarkReport, MetricSnapshot
from benchmarks.mainline_curriculum.tasks import get_task
from control.sentinel.sentinel_runtime import SentinelRuntime
from control.sentinel.somatic_state import SomaticState
from planning.mainline.mainline_runner import MainlineRunner, MissionRunResult
from planning.mainline.mission_graph_v4 import MissionGraphV4
from runtime.claim_runtime import ClaimGraph
from skills.registry import SkillRegistry
from skills.schema import SkillDef


RunnerState = str  # idle | running | paused | stopped | error


@dataclass(slots=True)
class MainlineState:
    """Current system state exposed to cockpit."""
    runner_state: RunnerState = "idle"
    mission_id: str = ""
    active_quest_id: str = ""
    active_mission_node: str = ""
    screen_state: str = ""
    sentinel_budget_remaining: int = 0
    claim_count: int = 0
    belief_count: int = 0
    suspect_belief_count: int = 0
    skill_count: int = 0
    somatic: SomaticState | None = None


class MainlineAPI:
    """Cockpit API for mission control.

    Thread-safe. Wraps the runner, sentinel, FIG, claim graph, and skill
    registry into a unified control surface.
    """

    def __init__(
        self,
        claim_graph: ClaimGraph | None = None,
        fig: FalsifiableInterventionGraph | None = None,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self._claim_graph = claim_graph or ClaimGraph()
        self._fig = fig or FalsifiableInterventionGraph()
        self._skill_registry = skill_registry or SkillRegistry()
        self._sentinel = SentinelRuntime()
        self._runner = MainlineRunner(sentinel=self._sentinel)
        self._state = MainlineState()
        self._lock = threading.Lock()
        self._last_result: MissionRunResult | None = None
        self._benchmark_report = BenchmarkReport()

    def get_state(self) -> dict[str, Any]:
        """GET /mainline/state — current system snapshot."""
        with self._lock:
            self._state.sentinel_budget_remaining = self._sentinel.budget_remaining
            self._state.skill_count = self._skill_registry.size
            self._state.belief_count = len(self._fig.beliefs)
            self._state.suspect_belief_count = len(self._fig.suspect_beliefs())
            return {
                "runner_state": self._state.runner_state,
                "mission_id": self._state.mission_id,
                "active_quest_id": self._state.active_quest_id,
                "active_mission_node": self._state.active_mission_node,
                "sentinel_budget_remaining": self._state.sentinel_budget_remaining,
                "claim_count": self._state.claim_count,
                "belief_count": self._state.belief_count,
                "suspect_belief_count": self._state.suspect_belief_count,
                "skill_count": self._state.skill_count,
            }

    def start(self, graph: MissionGraphV4 | None = None) -> dict[str, Any]:
        """POST /mainline/start — begin mission execution."""
        if graph is None:
            return {"ok": False, "reason": "no_graph"}

        with self._lock:
            if self._state.runner_state == "running":
                return {"ok": False, "reason": "already_running"}

            self._state.runner_state = "running"
            self._state.mission_id = graph.mission_id

        result = self._runner.run(graph)
        with self._lock:
            self._last_result = result
            self._state.runner_state = "completed" if result.success else "error"
        return {"ok": result.success, "completed": result.completed_nodes,
                "failed": result.failed_nodes, "duration_sec": result.duration_sec}

    def pause(self) -> dict[str, Any]:
        """POST /mainline/pause — pause current mission."""
        with self._lock:
            if self._state.runner_state != "running":
                return {"ok": False, "reason": "not_running"}
            self._state.runner_state = "paused"
        return {"ok": True}

    def stop(self) -> dict[str, Any]:
        """POST /mainline/stop — stop and clean up."""
        with self._lock:
            self._state.runner_state = "stopped"
            self._sentinel.reset()
        return {"ok": True}

    def get_claims(self) -> dict[str, Any]:
        """GET /mainline/claims — claim graph summary."""
        with self._lock:
            return {
                "claim_count": self._claim_graph.claim_count,
                "observation_count": self._claim_graph.observation_count,
            }

    def get_bagel(self) -> dict[str, Any]:
        """GET /bagel/fig — FIG and belief status."""
        with self._lock:
            return {
                "graph_id": self._fig.graph_id,
                "version": self._fig.version,
                "belief_count": len(self._fig.beliefs),
                "action_count": len(self._fig.actions),
                "feedback_count": len(self._fig.feedbacks),
                "probe_count": len(self._fig.probes),
                "suspect_beliefs": [
                    {"id": b.belief_id, "hypothesis": b.hypothesis, "lifecycle": b.lifecycle}
                    for b in self._fig.suspect_beliefs()
                ],
                "falsified_beliefs": [
                    {"id": b.belief_id, "hypothesis": b.hypothesis}
                    for b in self._fig.falsified_beliefs()
                ],
            }

    def get_skills(self) -> dict[str, Any]:
        """GET /skills/promotion — skill registry and promotion status."""
        skills = self._skill_registry.all_skills()
        return {
            "total": len(skills),
            "by_tier": self._group_by_tier(skills),
            "skills": [s.to_dict() for s in skills],
        }

    def run_benchmark(self, task_id: str) -> dict[str, Any]:
        """POST /benchmarks/mainline/run — execute benchmark task."""
        task = get_task(task_id)
        if task is None:
            return {"ok": False, "reason": f"unknown task: {task_id}"}

        # Placeholder: real implementation would run the task
        metric = MetricSnapshot(task_id=task_id, tsr=0.0)
        self._benchmark_report.add(metric)
        return {"ok": True, "task_id": task_id, "metric": metric.to_dict()}

    def _group_by_tier(self, skills: list[SkillDef]) -> dict[str, int]:
        tiers: dict[str, int] = {}
        for s in skills:
            tiers[s.tier] = tiers.get(s.tier, 0) + 1
        return tiers
