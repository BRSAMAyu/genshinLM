# World State Graph Specification

> **Purpose**: 3D pathfinding, landmark tracking, target tracking, route claims for spatial navigation.
> **Status**: Partially implemented (navigation/map_navigation_runtime.py, knowledge/world_graph.py)
> **Parent**: SPARKLE_AGENT_KERNEL_DESIGN.md

---

## Overview

**WorldStateGraph** is the 3D spatial representation of the game world, complementary
to DesktopTree's 2D UI focus. It provides:

- **Waypoint graph**: Known locations with connections (teleport/walk/swim).
- **Landmark tracking**: Visual landmarks for ego-centric positioning.
- **Route planning**: From current position to target via NavigationPlan.
- **Route claims**: Verifiable assertions about navigation progress.

```
Current Position (from minimap/camera)
  → WaypointGraph (from knowledge/world_graph.yaml)
  → MapNavigationRuntime.select_destination()
  → NavigationPlan (sequence of NavigationLegs)
  → Execution via NavigationController
  → RouteClaim verification (arrived at destination)
```

## Core Types

### NavigationPlan

```python
@dataclass(frozen=True, slots=True)
class NavigationPlan:
    plan_id: str
    legs: tuple[NavigationLeg, ...]
    arrived: bool
    arrived_leg_index: int
```

### NavigationLeg

```python
@dataclass(frozen=True, slots=True)
class NavigationLeg:
    method: str        # "teleport" | "walk" | "swim" | "climb" | "glide"
    waypoint_id: str
    target_xy: tuple[float, float]
    expected_duration_sec: float
```

### WaypointGraph

Loaded from `knowledge/genshin_world_graph.yaml`:
- 230+ waypoints
- 420+ edges
- 7 regions (Mondstadt, Liyue, Inazuma, Sumeru, Fontaine, Natlan, Snezhnaya)

## RouteClaim

A verifiable assertion about navigation progress:

```python
@dataclass(frozen=True, slots=True)
class RouteClaim:
    plan_id: str
    leg_index: int
    claimed_position: tuple[float, float]  # normalized world coordinates
    confidence: float
    evidence: str  # "minimap_landmark" | "quest_marker" | "teleport_confirm"
```

Verification: compare claimed position with minimap/landmark detection.

## LandmarkClaim

```python
@dataclass(frozen=True, slots=True)
class LandmarkClaim:
    landmark_id: str
    landmark_type: str  # "statue" | "waypoint" | "domain" | "npc" | "boss"
    world_position: tuple[float, float]
    detected_from: str  # "minimap" | "visual" | "quest_marker"
    confidence: float
```

## Components

| Component | File | Role |
|-----------|------|------|
| MapNavigationRuntime | navigation/map_navigation_runtime.py | Route planning |
| WaypointGraph | knowledge/world_graph.py | Graph data |
| QuestMarkerFollower | navigation/quest_marker_follower.py | Visual marker tracking |
| TeleportSequence | navigation/teleport_sequence.py | Teleport execution |
| MinimapQuestReader | navigation/minimap_quest_reader.py | Minimap parsing |
| LostRecovery | navigation/lost_recovery.py | Recovery when lost |
| NavigationController | control/navigation_runtime.py | Heading servo + stuck detection |

## Design Principles

1. **DesktopTree for UI, WorldStateGraph for 3D** — these are parallel abstractions.
2. **Route claims are verifiable** — every navigation step produces a claim that can be verified by visual feedback.
3. **Waypoint data is game-specific** — lives in capsule YAML, not kernel code.
4. **Recovery is mandatory** — stuck detection + lost recovery must always be active during navigation.

## HSR Cross-Validation

To verify the kernel doesn't have Genshin-specific assumptions baked in, a minimal
HSR navigation loop should be implementable using the same WorldStateGraph abstraction
with different waypoint data and detection heuristics.

---

*Source: `navigation/map_navigation_runtime.py`, `knowledge/world_graph.py`, `control/navigation_runtime.py`*
