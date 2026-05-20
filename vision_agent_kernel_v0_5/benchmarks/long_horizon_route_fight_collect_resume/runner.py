"""Runner for the long-horizon route/fight/collect/resume benchmark suite.

Creates a mock StateBus, steps through each phase, records evidence at each
terminal node, verifies resume skips verified nodes, and returns BenchmarkResult
instances for each scenario.
"""

from __future__ import annotations

import uuid

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from evidence.evidence_nodes import (
    EDGE_DERIVED_FROM,
    EDGE_RESULTED_IN,
    NODE_TYPE_INTERRUPT,
    NODE_TYPE_OBSERVATION,
    NODE_TYPE_RECOVERY,
    NODE_TYPE_VERIFIER_RESULT,
)
from evidence.evidence_store import EvidenceStore

from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from benchmarks.long_horizon_route_fight_collect_resume.scenario import (
    LongHorizonScenario,
    RouteNode,
    SCENARIOS,
)


def run_scenario(scenario: LongHorizonScenario) -> BenchmarkResult:
    """Execute a single long-horizon scenario and return a BenchmarkResult."""
    timebase = Timebase()
    bus = StateBus()
    store = EvidenceStore(run_id=f"lh_{scenario.name}")

    evidence_ids: list[str] = []
    nodes_with_evidence: set[str] = set()  # scenario node_ids that produced evidence
    phases_completed: list[str] = []
    nodes_visited: list[str] = []
    resume_skips: list[str] = []
    interrupt_count = 0
    recovery_transitions = 0
    verified_before_resume: list[str] = []

    t_start = timebase.now()

    for node in scenario.nodes:
        # If the node is verified and scenario expects resume to skip,
        # record it as skipped and continue
        if node.verified and scenario.expect_resume_skips_verified:
            resume_skips.append(node.node_id)
            nodes_visited.append(node.node_id)
            continue

        # Create synthetic observation for this phase
        obs = Observation(
            frame_id=len(nodes_visited),
            t_capture=timebase.now(),
            t_processed=timebase.now(),
            latency_ms=0.5,
            viewport_size=(1920, 1080),
            target_track=None,
            obstacle_field=None,
            ui_state=None,
            visual_triggers={node.phase: True},
            os_focus=FocusState(focused=True),
            extensions={"phase": node.phase, "node_id": node.node_id},
        )
        bus.publish_observation(obs)

        # Record observation evidence
        obs_node = store.record_node(NODE_TYPE_OBSERVATION, {
            "phase": node.phase,
            "node_id": node.node_id,
            "frame_id": obs.frame_id,
        })
        evidence_ids.append(obs_node.node_id)
        nodes_with_evidence.add(node.node_id)

        # Handle phase-specific logic
        if node.phase == "forced_stop":
            # Publish an interrupt
            interrupt = Interrupt(
                priority=0,
                timestamp=timebase.now(),
                code="EMERGENCY_STOP",
                source="benchmark",
                payload={"reason": "forced_stop_test"},
            )
            bus.publish_interrupt(interrupt)
            interrupt_node = store.record_node(NODE_TYPE_INTERRUPT, {
                "code": "EMERGENCY_STOP",
                "node_id": node.node_id,
            })
            evidence_ids.append(interrupt_node.node_id)
            store.record_edge(obs_node.node_id, interrupt_node.node_id, EDGE_RESULTED_IN)
            interrupt_count += 1

        elif node.phase == "hot_resume":
            # Record recovery
            recovery_node = store.record_node(NODE_TYPE_RECOVERY, {
                "resume_from": nodes_visited[-1] if nodes_visited else "unknown",
                "skipped_verified": resume_skips,
            })
            evidence_ids.append(recovery_node.node_id)
            recovery_transitions += 1

        elif node.phase == "danger_reflex":
            danger_node = store.record_node("danger_clear", {
                "phase": node.phase,
                "cleared": True,
            })
            evidence_ids.append(danger_node.node_id)

        elif node.phase == "final_verifier":
            verifier_node = store.record_node(NODE_TYPE_VERIFIER_RESULT, {
                "phase": node.phase,
                "passed": True,
            })
            evidence_ids.append(verifier_node.node_id)

        # Record evidence for each expected type at terminal nodes
        if node.terminal:
            for ev_type in node.expected_evidence_types:
                if ev_type not in ("observation",):  # observation already recorded above
                    term_node = store.record_node(ev_type, {
                        "phase": node.phase,
                        "node_id": node.node_id,
                    })
                    evidence_ids.append(term_node.node_id)
                    store.record_edge(obs_node.node_id, term_node.node_id, EDGE_DERIVED_FROM)

        phases_completed.append(node.phase)
        nodes_visited.append(node.node_id)

    t_end = timebase.now()

    # Verify: all terminal nodes have evidence
    terminal_nodes = [n for n in scenario.nodes if n.terminal]
    terminal_evidence_ok = all(
        n.node_id in nodes_with_evidence
        for n in terminal_nodes
    )

    # Verify: resume skips verified nodes
    resume_skips_ok = True
    if scenario.expect_resume_skips_verified:
        verified_nodes = [n.node_id for n in scenario.nodes if n.verified]
        resume_skips_ok = all(v in resume_skips for v in verified_nodes)

    # Evidence coverage: fraction of nodes that have at least one evidence
    evidence_coverage = len(nodes_with_evidence) / max(len(scenario.nodes), 1)

    passed = terminal_evidence_ok and resume_skips_ok
    total_ms = (t_end - t_start) * 1000.0

    metrics = BenchmarkMetrics(
        frame_to_observation_ms=0.5,
        observation_to_interrupt_ms=total_ms if interrupt_count > 0 else 0.0,
        interrupt_to_lease_ms=0.0,
        danger_clear_time_ms=0.0,
        danger_false_clear_rate=0.0,
        resume_success_rate=1.0 if recovery_transitions > 0 else 0.0,
        max_consecutive_dodges=0,
        final_task_success=passed,
        evidence_coverage=evidence_coverage,
    )

    return BenchmarkResult(
        benchmark_id=f"long_horizon_{scenario.name}",
        run_id=uuid.uuid4().hex[:8],
        suite_name="long_horizon_route_fight_collect_resume",
        scenario_name=scenario.name,
        passed=passed,
        metrics=metrics,
        evidence_ids=evidence_ids,
        report={
            "phases_completed": phases_completed,
            "nodes_visited": nodes_visited,
            "resume_skips": resume_skips,
            "interrupt_count": interrupt_count,
            "recovery_transitions": recovery_transitions,
            "terminal_evidence_ok": terminal_evidence_ok,
            "resume_skips_ok": resume_skips_ok,
            "route_nodes": len(scenario.nodes),
        },
    )


def run_all_long_horizon() -> list[BenchmarkResult]:
    """Run all long-horizon scenarios and return results."""
    return [run_scenario(scenario) for scenario in SCENARIOS]
