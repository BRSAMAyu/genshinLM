# Knowledge And Planning

The knowledge layer resolves user goals into resources, source candidates, spatial routes, and MissionQueues.

## Spatial Topology

`knowledge/world_graph.py` provides a Waypoint Graph/NavMesh Proxy. Every `SourceNode` has:

- `region`
- `position: [x, y, z]`
- skill bindings
- verification rule

`RouteSelector.rank_routes` must use waypoint traversal cost. LLMs may rank existing routes, but they must not invent routes that bypass the waypoint graph.

## Mission Planning

`planning/` converts intent into `MissionQueue`.

Every node must include:

- skill binding or explicit verifier-only role
- verifier
- failure policy
- bounded loop/retry behavior

LLM-generated plans require schema validation and user confirmation before execution.

