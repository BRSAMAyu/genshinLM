from __future__ import annotations

import pytest

from planning.mainline.bagel_jit_router import BagelJitRouter
from planning.mainline.mission_graph_v4 import ClaimContract, MissionEdgeV4, MissionGraphV4, MissionNodeV4


def test_bagel_jit_router_teleport_healing() -> None:
    # 1. Setup a simple graph: Start -> TeleportNode -> End
    graph = MissionGraphV4(mission_id="m1")

    start_node = MissionNodeV4(node_id="start", node_type="story")
    teleport_node = MissionNodeV4(
        node_id="teleport_act",
        node_type="teleport_waypoint",
        output_claims=(ClaimContract("location", "target_region"),),
    )
    end_node = MissionNodeV4(node_id="end", node_type="story")

    graph.add_node(start_node)
    graph.add_node(teleport_node)
    graph.add_node(end_node)

    graph.add_edge(MissionEdgeV4("start", "teleport_act"))
    graph.add_edge(MissionEdgeV4("teleport_act", "end"))

    # Initial order
    initial_order = graph.topological_order()
    assert initial_order == ["start", "teleport_act", "end"]

    # 2. Invoke JIT router upon falsification
    router = BagelJitRouter(graph)
    mutated = router.handle_belief_falsification(
        falsified_belief_id="teleport_act_belief_0",
        failed_node_id="teleport_act",
    )

    assert mutated is True

    # 3. Verify graph mutation and new topological order
    new_order = graph.topological_order()
    assert new_order is not None

    # Expected sequential sequence:
    # start -> teleport_act_walk_healing -> teleport_act_unlock_healing -> teleport_act -> end
    assert "teleport_act_walk_healing" in new_order
    assert "teleport_act_unlock_healing" in new_order

    walk_idx = new_order.index("teleport_act_walk_healing")
    unlock_idx = new_order.index("teleport_act_unlock_healing")
    teleport_idx = new_order.index("teleport_act")

    assert new_order[0] == "start"
    assert walk_idx < unlock_idx
    assert unlock_idx < teleport_idx
    assert new_order[-1] == "end"


def test_bagel_jit_router_non_teleport_no_healing() -> None:
    graph = MissionGraphV4(mission_id="m2")
    node = MissionNodeV4(node_id="normal_combat", node_type="combat")
    graph.add_node(node)

    router = BagelJitRouter(graph)
    mutated = router.handle_belief_falsification(
        falsified_belief_id="normal_combat_belief_0",
        failed_node_id="normal_combat",
    )

    assert mutated is False
    assert len(graph.node_ids) == 1
