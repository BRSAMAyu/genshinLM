from __future__ import annotations

import logging
from planning.mainline.mission_graph_v4 import ClaimContract, MissionEdgeV4, MissionGraphV4, MissionNodeV4

log = logging.getLogger(__name__)


class BagelJitRouter:
    """Mutates active MissionGraphV4 topological structure upon belief falsification

    to heal the path and unlock waypoint nodes dynamically.
    """

    def __init__(self, graph: MissionGraphV4) -> None:
        self._graph = graph

    def handle_belief_falsification(self, falsified_belief_id: str, failed_node_id: str) -> bool:
        """Detects belief falsification (e.g. teleport waypoint not unlocked),

        and dynamically injects healing nodes in front of the failed node.
        Returns True if a graph mutation occurred.
        """
        log.info(
            "[BagelJitRouter] Handling falsification: belief=%s on node=%s",
            falsified_belief_id,
            failed_node_id,
        )
        failed_node = self._graph.get_node(failed_node_id)
        if not failed_node:
            return False

        # Check if the falsification is about a teleport waypoint not being unlocked
        is_teleport_falsified = (
            "teleport" in failed_node.node_type
            or "waypoint" in falsified_belief_id
            or "teleport" in falsified_belief_id
        )

        if is_teleport_falsified:
            log.info("[BagelJitRouter] Waypoint falsified. Injecting walk-and-unlock healing subgraph.")
            return self._inject_walk_and_unlock_waypoint(failed_node_id)

        # Resolve Gap 23: Elemental Puzzle Attribute Roster Validation
        elif "elemental" in falsified_belief_id.lower() or "puzzle" in failed_node.node_type:
            log.info("[BagelJitRouter] Elemental puzzle attribute missing. Injecting party-switch healing node.")
            return self._inject_party_switch(failed_node_id, falsified_belief_id)

        # Resolve Gap 19: Loot Occlusion & Physics Oscillation target bypass
        elif "loot" in failed_node.node_type or "drop" in falsified_belief_id.lower() or "collect" in failed_node_id:
            log.info("[BagelJitRouter] Target drop unreachable/occluded. Injecting bypass routing.")
            return self._bypass_occluded_target(failed_node_id)

        return False

    def _inject_walk_and_unlock_waypoint(self, failed_node_id: str) -> bool:
        """Inserts new nodes to walk to and unlock the waypoint, bypassing or resolving

        the failed teleport node.
        """
        # Create new nodes: walk and unlock
        walk_node_id = f"{failed_node_id}_walk_healing"
        unlock_node_id = f"{failed_node_id}_unlock_healing"

        # If already injected, don't repeat
        if self._graph.get_node(walk_node_id) or self._graph.get_node(unlock_node_id):
            return False

        # Construct new MissionNodeV4s
        walk_node = MissionNodeV4(
            node_id=walk_node_id,
            node_type="walk_to_target",
            risk_level="medium",
            skill_candidates=("quest_follow",),
            input_claims=(),
            output_claims=(ClaimContract(claim_type="location", target="waypoint_proximity"),),
        )

        unlock_node = MissionNodeV4(
            node_id=unlock_node_id,
            node_type="interact_waypoint",
            risk_level="medium",
            skill_candidates=("interact",),
            input_claims=(ClaimContract(claim_type="location", target="waypoint_proximity"),),
            output_claims=(ClaimContract(claim_type="waypoint_unlocked", target="teleport_active"),),
        )

        # Add nodes to graph
        self._graph.add_node(walk_node)
        self._graph.add_node(unlock_node)

        # Re-wire predecessor edges of failed_node_id to point to walk_node_id instead
        preds = list(self._graph.predecessors(failed_node_id))
        for pred in preds:
            if failed_node_id in self._graph._edges.get(pred, set()):
                self._graph._edges[pred].remove(failed_node_id)
            if pred in self._graph._reverse_edges.get(failed_node_id, set()):
                self._graph._reverse_edges[failed_node_id].remove(pred)
            cond = self._graph._edge_conditions.pop((pred, failed_node_id), "success")

            # Add edge pred -> walk_node
            self._graph.add_edge(MissionEdgeV4(from_node=pred, to_node=walk_node_id, condition=cond))

        # Add walk_node -> unlock_node -> failed_node_id sequential chain
        self._graph.add_edge(MissionEdgeV4(from_node=walk_node_id, to_node=unlock_node_id, condition="success"))
        self._graph.add_edge(MissionEdgeV4(from_node=unlock_node_id, to_node=failed_node_id, condition="success"))

        log.info(
            "[BagelJitRouter] Re-wired graph. New path: predecessors -> %s -> %s -> %s",
            walk_node_id,
            unlock_node_id,
            failed_node_id,
        )
        return True

    def _inject_party_switch(self, failed_node_id: str, falsified_belief_id: str) -> bool:
        """Inserts a party-switch configuration node to add the required elemental character to active team."""
        switch_node_id = f"{failed_node_id}_switch_party_healing"
        if self._graph.get_node(switch_node_id):
            return False

        # Determine required element from belief id
        req_element = "pyro"
        for elem in ("pyro", "hydro", "electro", "anemo", "geo", "cryo", "dendro", "bow"):
            if elem in falsified_belief_id.lower():
                req_element = elem
                break

        switch_node = MissionNodeV4(
            node_id=switch_node_id,
            node_type="switch_party",
            risk_level="low",
            skill_candidates=("ui_flow:switch_party_setup",),
            input_claims=(),
            output_claims=(ClaimContract(claim_type="party_config", target=f"has_{req_element}_active"),),
            metadata={"required_element": req_element}
        )

        self._graph.add_node(switch_node)

        # Wire: predecessors -> switch_node -> failed_node
        preds = list(self._graph.predecessors(failed_node_id))
        for pred in preds:
            if failed_node_id in self._graph._edges.get(pred, set()):
                self._graph._edges[pred].remove(failed_node_id)
            if pred in self._graph._reverse_edges.get(failed_node_id, set()):
                self._graph._reverse_edges[failed_node_id].remove(pred)
            cond = self._graph._edge_conditions.pop((pred, failed_node_id), "success")
            self._graph.add_edge(MissionEdgeV4(from_node=pred, to_node=switch_node_id, condition=cond))

        self._graph.add_edge(MissionEdgeV4(from_node=switch_node_id, to_node=failed_node_id, condition="success"))
        log.info("[BagelJitRouter] Injected party switch healing node: %s for element %s", switch_node_id, req_element)
        return True

    def _bypass_occluded_target(self, failed_node_id: str) -> bool:
        """Bypasses an occluded/unreachable loot target, routing directly to successive nodes to avoid lockups."""
        successors = list(self._graph.successors(failed_node_id))
        predecessors = list(self._graph.predecessors(failed_node_id))

        if not successors:
            log.warning("[BagelJitRouter] Cannot bypass failed loot node %s: no successors in graph", failed_node_id)
            return False

        log.info("[BagelJitRouter] Bypassing unreachable loot node %s. Connecting predecessors directly to successors.", failed_node_id)
        
        # Connect each predecessor directly to each successor
        for pred in predecessors:
            cond = self._graph._edge_conditions.get((pred, failed_node_id), "success")
            for succ in successors:
                self._graph.add_edge(MissionEdgeV4(from_node=pred, to_node=succ, condition=cond))

        # Remove failed node's incoming/outgoing edges to isolate it
        for pred in predecessors:
            if failed_node_id in self._graph._edges.get(pred, set()):
                self._graph._edges[pred].remove(failed_node_id)
            if pred in self._graph._reverse_edges.get(failed_node_id, set()):
                self._graph._reverse_edges[failed_node_id].remove(pred)
            self._graph._edge_conditions.pop((pred, failed_node_id), None)

        for succ in successors:
            if succ in self._graph._edges.get(failed_node_id, set()):
                self._graph._edges[failed_node_id].remove(succ)
            if failed_node_id in self._graph._reverse_edges.get(succ, set()):
                self._graph._reverse_edges[succ].remove(failed_node_id)
            self._graph._edge_conditions.pop((failed_node_id, succ), None)

        log.info("[BagelJitRouter] Isolated failed loot node %s. Reroute complete.", failed_node_id)
        return True
