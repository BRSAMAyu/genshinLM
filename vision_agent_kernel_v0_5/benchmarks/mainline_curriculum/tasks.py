"""Benchmark task definitions.

Each task is a dict with:
- task_id: C0-C11 identifier
- name: human-readable name
- description: what the task tests
- category: which subsystem is primarily tested
- difficulty: 1-5
- success_criteria: list of conditions for passing
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    task_id: str
    name: str
    description: str
    category: str
    difficulty: int
    success_criteria: tuple[str, ...]
    time_limit_sec: float = 300.0


TASKS: tuple[BenchmarkTask, ...] = (
    BenchmarkTask(
        task_id="C0",
        name="Bootstrap Startup",
        description="System initializes: claim graph created, BAGEL FIG ready, "
                    "sentinel starts, screen state tree builds from synthetic frame",
        category="system",
        difficulty=1,
        success_criteria=(
            "claim_graph_created",
            "fig_initialized",
            "sentinel_running",
            "screen_state_tree_built",
        ),
        time_limit_sec=30.0,
    ),
    BenchmarkTask(
        task_id="C1",
        name="Dialogue Progression",
        description="Advance through 5 dialogue turns, detect text changes, "
                    "select correct option from 3 choices",
        category="dialogue",
        difficulty=2,
        success_criteria=(
            "dialogue_advanced_5_turns",
            "option_selected_correctly",
            "dialogue_claim_produced",
        ),
        time_limit_sec=60.0,
    ),
    BenchmarkTask(
        task_id="C2",
        name="Quest Tracking",
        description="Detect quest objective change, update ActiveQuestContext, "
                    "handle OCR dropout and recovery",
        category="quest",
        difficulty=2,
        success_criteria=(
            "objective_change_detected",
            "context_version_incremented",
            "ocr_dropout_handled",
        ),
        time_limit_sec=60.0,
    ),
    BenchmarkTask(
        task_id="C3",
        name="Map Teleport",
        description="Open map, select nearest unlocked waypoint, confirm teleport, "
                    "verify arrival via loading → world transition claim",
        category="navigation",
        difficulty=3,
        success_criteria=(
            "map_opened",
            "waypoint_selected",
            "teleport_confirmed",
            "arrival_claim_produced",
        ),
        time_limit_sec=120.0,
    ),
    BenchmarkTask(
        task_id="C4",
        name="Short Navigation",
        description="Navigate from teleport point to quest marker via heading servo, "
                    "detect arrival within 10m",
        category="navigation",
        difficulty=3,
        success_criteria=(
            "heading_servo_active",
            "progress_made",
            "arrival_detected",
        ),
        time_limit_sec=90.0,
    ),
    BenchmarkTask(
        task_id="C5",
        name="Interaction Collect",
        description="Interact with NPC to start collection quest, collect 3 items, "
                    "verify inventory claim",
        category="interaction",
        difficulty=3,
        success_criteria=(
            "interaction_started",
            "items_collected_3",
            "inventory_claim_produced",
        ),
        time_limit_sec=120.0,
    ),
    BenchmarkTask(
        task_id="C6",
        name="Basic Combat",
        description="Engage 3 enemies, survive with >50% HP, kill all, "
                    "produce combat_end claim",
        category="combat",
        difficulty=4,
        success_criteria=(
            "combat_started",
            "survived_50hp",
            "all_enemies_killed",
            "combat_end_claim",
        ),
        time_limit_sec=180.0,
    ),
    BenchmarkTask(
        task_id="C7",
        name="Recovery Gauntlet",
        description="Trigger and recover from 3 different failure modes "
                    "(stuck, UI lost, low health) within budget",
        category="recovery",
        difficulty=3,
        success_criteria=(
            "3_recoveries_completed",
            "no_budget_exhaustion",
            "claims_produced_for_each",
        ),
        time_limit_sec=120.0,
    ),
    BenchmarkTask(
        task_id="C8",
        name="Skill Induction Unknown UI",
        description="Explore unknown UI, induce a new skill from trace, "
                    "promote to draft tier with anchors bound",
        category="skill_induction",
        difficulty=4,
        success_criteria=(
            "trace_recorded",
            "skill_induced",
            "anchors_bound",
            "promoted_to_draft",
        ),
        time_limit_sec=120.0,
    ),
    BenchmarkTask(
        task_id="C9",
        name="Multi-Node Mainline",
        description="Execute a 5+ node mission graph with mixed node types "
                    "(observe, dialog, navigate, combat, claim_reward)",
        category="mission",
        difficulty=4,
        success_criteria=(
            "all_nodes_completed",
            "no_sentinel_intervention",
            "terminal_claims_produced",
        ),
        time_limit_sec=300.0,
    ),
    BenchmarkTask(
        task_id="C10",
        name="Boss Failure Revision",
        description="Fail boss fight, attribute failure via BAGEL, revise belief, "
                    "succeed on retry",
        category="bagel",
        difficulty=5,
        success_criteria=(
            "boss_attempt_1_failed",
            "failure_attributed",
            "belief_revised",
            "boss_attempt_2_succeeded",
        ),
        time_limit_sec=600.0,
    ),
    BenchmarkTask(
        task_id="C11",
        name="Long Horizon 2h Resume",
        description="Execute for 30+ minutes, save checkpoint, stop, resume from "
                    "checkpoint, complete remaining nodes",
        category="persistence",
        difficulty=5,
        success_criteria=(
            "checkpoint_saved",
            "session_stopped_cleanly",
            "resumed_from_checkpoint",
            "completed_after_resume",
        ),
        time_limit_sec=7200.0,
    ),
)


def get_task(task_id: str) -> BenchmarkTask | None:
    for t in TASKS:
        if t.task_id == task_id:
            return t
    return None


def all_tasks() -> tuple[BenchmarkTask, ...]:
    return TASKS
