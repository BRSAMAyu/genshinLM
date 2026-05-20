"""Scenarios for long-horizon route/fight/collect/resume benchmark suite."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RouteNode:
    """A single node in the long-horizon route chain."""

    node_id: str
    phase: str  # knowledge_resolve, route_choose, enter_region, combat, danger_reflex, collect, forced_stop, hot_resume, final_verifier
    expected_evidence_types: list[str]
    terminal: bool = False
    verified: bool = False


@dataclass(slots=True)
class LongHorizonScenario:
    """A complete long-horizon scenario definition."""

    name: str
    description: str
    nodes: list[RouteNode]
    expect_resume_skips_verified: bool = True
    expect_evidence_at_each_terminal: bool = True


SCENARIOS: list[LongHorizonScenario] = [
    LongHorizonScenario(
        name="full_chain_happy_path",
        description="Complete chain: knowledge -> route -> enter -> combat -> danger -> collect -> stop -> resume -> verifier",
        nodes=[
            RouteNode("n1", "knowledge_resolve", ["observation", "knowledge_result"]),
            RouteNode("n2", "route_choose", ["observation", "route_decision"]),
            RouteNode("n3", "enter_region", ["observation", "region_entered"]),
            RouteNode("n4", "combat", ["observation", "combat_result"], terminal=True),
            RouteNode("n5", "danger_reflex", ["observation", "danger_clear"]),
            RouteNode("n6", "collect", ["observation", "collection_result"], terminal=True),
            RouteNode("n7", "forced_stop", ["interrupt", "emergency_stop"]),
            RouteNode("n8", "hot_resume", ["recovery", "resume_contract"]),
            RouteNode("n9", "final_verifier", ["verifier_result"], terminal=True),
        ],
    ),
    LongHorizonScenario(
        name="combat_recovery_resume",
        description="Combat fails, triggers recovery, hot resume skips verified nodes",
        nodes=[
            RouteNode("n1", "knowledge_resolve", ["observation", "knowledge_result"], verified=True),
            RouteNode("n2", "route_choose", ["observation", "route_decision"], verified=True),
            RouteNode("n3", "combat", ["observation", "combat_result", "failure_signature"], terminal=True),
            RouteNode("n4", "danger_reflex", ["observation", "danger_clear"]),
            RouteNode("n5", "hot_resume", ["recovery", "resume_contract"]),
            RouteNode("n6", "final_verifier", ["verifier_result"], terminal=True),
        ],
    ),
    LongHorizonScenario(
        name="double_interrupt_resume",
        description="Two interrupts during long chain; both resume correctly",
        nodes=[
            RouteNode("n1", "knowledge_resolve", ["observation", "knowledge_result"]),
            RouteNode("n2", "forced_stop", ["interrupt"]),
            RouteNode("n3", "hot_resume", ["recovery", "resume_contract"]),
            RouteNode("n4", "enter_region", ["observation", "region_entered"]),
            RouteNode("n5", "forced_stop", ["interrupt"]),
            RouteNode("n6", "hot_resume", ["recovery", "resume_contract"]),
            RouteNode("n7", "final_verifier", ["verifier_result"], terminal=True),
        ],
    ),
    LongHorizonScenario(
        name="collect_with_danger_interleave",
        description="Danger reflex triggers during collection; resume continues collect",
        nodes=[
            RouteNode("n1", "route_choose", ["observation", "route_decision"]),
            RouteNode("n2", "enter_region", ["observation", "region_entered"]),
            RouteNode("n3", "collect", ["observation", "collection_started"]),
            RouteNode("n4", "danger_reflex", ["observation", "danger_clear"]),
            RouteNode("n5", "hot_resume", ["recovery", "resume_contract"]),
            RouteNode("n6", "collect", ["observation", "collection_result"], terminal=True),
            RouteNode("n7", "final_verifier", ["verifier_result"], terminal=True),
        ],
    ),
]
