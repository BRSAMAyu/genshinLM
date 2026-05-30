"""Advanced perception and navigation capabilities.

Covers:
- P-23: Map region name OCR (read map location labels)
- P-24: Material name recognition (backpack/crafting bench)
- P-25: Skill description OCR (talent descriptions)
- P-29: Puzzle state detection (activated/inactive/error)
- N-15: Multi-target path optimization (TSP for waypoints)
- N-18: 3D spatial navigation (multi-layer cave/building)
- I-15: Precise mouse drag (map drag, party config)
- I-16: Scroll wheel operations (map zoom, list scroll)

Integrates with:
- perception/genshin_screen_classifier.py for screen state
- perception/genshin_visual_detectors.py for visual detection
- navigation/genshin_navigator.py for pathfinding
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OCR capabilities (P-23, P-24, P-25)
# ---------------------------------------------------------------------------

class OCRResult:
    """Result from an OCR read operation."""

    __slots__ = ("text", "confidence", "position")

    def __init__(self, text: str, confidence: float = 0.0,
                 position: tuple[int, int] = (0, 0)) -> None:
        self.text = text
        self.confidence = confidence
        self.position = position


@dataclass(slots=True)
class MapRegionInfo:
    """Detected map region information."""
    region_name: str
    subregion_name: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class MaterialInfo:
    """Detected material in inventory/crafting."""
    name: str
    quantity: int = 0
    rarity: int = 1        # 1-5 stars
    category: str = ""


@dataclass(slots=True)
class SkillDescription:
    """Parsed skill/talent description."""
    skill_name: str
    description: str = ""
    effect_type: str = ""  # "damage", "heal", "buff", "shield", "utility"
    scaling_stat: str = ""  # "atk", "hp", "def", "em"


class GameTextReader:
    """Unified OCR reader for game text (P-23, P-24, P-25).

    Wraps the existing GLM OCR provider with game-specific parsing.
    In production, delegates to glm_ocr_provider.py.
    """

    def read_map_region(self, ocr_results: list[OCRResult]) -> MapRegionInfo | None:
        """P-23: Parse map region name from OCR results."""
        if not ocr_results:
            return None
        # Use highest confidence result as region name
        best = max(ocr_results, key=lambda r: r.confidence)
        return MapRegionInfo(
            region_name=best.text.strip(),
            confidence=best.confidence,
        )

    def read_material_info(self, ocr_results: list[OCRResult]) -> MaterialInfo | None:
        """P-24: Parse material name and quantity from OCR results."""
        if not ocr_results:
            return None
        # First result is usually the name, look for quantity in others
        name = ocr_results[0].text.strip()
        quantity = 0
        for r in ocr_results[1:]:
            try:
                quantity = int(r.text.strip().replace(",", "").replace("x", ""))
                break
            except ValueError:
                continue
        return MaterialInfo(name=name, quantity=quantity)

    def read_skill_description(self, ocr_results: list[OCRResult]) -> SkillDescription | None:
        """P-25: Parse skill/talent description from OCR results."""
        if not ocr_results:
            return None
        name = ocr_results[0].text.strip() if ocr_results else ""
        desc = " ".join(r.text for r in ocr_results[1:])
        return SkillDescription(
            skill_name=name,
            description=desc,
        )


# ---------------------------------------------------------------------------
# Puzzle state detection (P-29)
# ---------------------------------------------------------------------------

class PuzzleState(str, Enum):
    INACTIVE = "inactive"
    ACTIVATED = "activated"
    ERROR = "error"          # Wrong configuration
    SOLVED = "solved"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PuzzleDetection:
    """Detected puzzle state from visual analysis."""
    puzzle_type: str          # "torch", "totem", "element_pillar", "pressure_plate", "seelie"
    state: PuzzleState
    position: tuple[int, int] = (0, 0)
    confidence: float = 0.0
    required_element: str = ""  # For element pillar puzzles


class PuzzleDetector:
    """Detects puzzle states from visual analysis (P-29).

    Identifies active/inactive/wrong states for common puzzle types.
    Uses HSV color analysis for glow/activation indicators.
    """

    # Active puzzle glow colors (HSV ranges)
    _ACTIVE_COLORS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        "pyro": ((0, 150, 150), (15, 255, 255)),
        "electro": ((130, 100, 100), (160, 255, 255)),
        "cryo": ((85, 50, 150), (110, 200, 255)),
        "hydro": ((95, 100, 100), (130, 255, 255)),
        "anemo": ((65, 50, 150), (90, 200, 255)),
        "dendro": ((35, 100, 100), (80, 255, 255)),
        "geo": ((15, 100, 100), (35, 255, 255)),
    }

    def detect_puzzle_state(self, puzzle_type: str,
                            is_glowing: bool,
                            has_error_indicator: bool = False,
                            element: str = "",
                            position: tuple[int, int] = (0, 0),
                            ) -> PuzzleDetection:
        """Detect puzzle state from visual indicators."""
        if has_error_indicator:
            state = PuzzleState.ERROR
        elif is_glowing:
            state = PuzzleState.ACTIVATED
        else:
            state = PuzzleState.INACTIVE

        return PuzzleDetection(
            puzzle_type=puzzle_type,
            state=state,
            position=position,
            confidence=0.8,
            required_element=element,
        )

    def check_puzzle_completion(self, detections: list[PuzzleDetection]) -> PuzzleState:
        """Check if a multi-element puzzle is complete (all activated, none in error)."""
        if not detections:
            return PuzzleState.UNKNOWN

        if any(d.state == PuzzleState.ERROR for d in detections):
            return PuzzleState.ERROR

        if all(d.state == PuzzleState.ACTIVATED for d in detections):
            return PuzzleState.SOLVED

        return PuzzleState.INACTIVE


# ---------------------------------------------------------------------------
# Multi-target path optimization (N-15)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PathTarget:
    """A target location for path planning."""
    target_id: str
    position: tuple[float, float]   # (x, y) in world coordinates
    priority: int = 0               # Higher = more important
    estimated_time_sec: float = 60.0


@dataclass(slots=True)
class OptimizedPath:
    """Result of multi-target path optimization."""
    ordered_targets: list[PathTarget] = field(default_factory=list)
    total_distance: float = 0.0
    total_estimated_time: float = 0.0
    savings_vs_greedy: float = 0.0  # Percentage improvement over nearest-neighbor


class MultiTargetPathOptimizer:
    """Optimizes visit order for multiple targets (N-15).

    Uses nearest-neighbor heuristic with 2-opt improvement.
    For the game context, targets are waypoints/chests/oculi.
    """

    def optimize(self, targets: list[PathTarget],
                 start_position: tuple[float, float] = (0.0, 0.0),
                 must_return: bool = False) -> OptimizedPath:
        """Optimize visit order using nearest-neighbor + 2-opt."""
        if not targets:
            return OptimizedPath()

        if len(targets) == 1:
            dist = self._distance(start_position, targets[0].position)
            return OptimizedPath(
                ordered_targets=targets,
                total_distance=dist,
                total_estimated_time=targets[0].estimated_time_sec,
            )

        # Nearest-neighbor
        ordered = self._nearest_neighbor(targets, start_position)
        greedy_dist = self._total_distance(ordered, start_position, must_return)

        # 2-opt improvement (limited iterations for real-time use)
        improved = self._two_opt(ordered, start_position, must_return, max_iterations=50)
        final_dist = self._total_distance(improved, start_position, must_return)

        savings = (greedy_dist - final_dist) / max(greedy_dist, 1.0) * 100

        total_time = sum(t.estimated_time_sec for t in improved)

        return OptimizedPath(
            ordered_targets=improved,
            total_distance=final_dist,
            total_estimated_time=total_time,
            savings_vs_greedy=savings,
        )

    def _nearest_neighbor(self, targets: list[PathTarget],
                          start: tuple[float, float]) -> list[PathTarget]:
        remaining = list(targets)
        ordered: list[PathTarget] = []
        current = start
        while remaining:
            nearest = min(remaining, key=lambda t: self._distance(current, t.position))
            ordered.append(nearest)
            remaining.remove(nearest)
            current = nearest.position
        return ordered

    def _two_opt(self, route: list[PathTarget],
                 start: tuple[float, float],
                 must_return: bool, max_iterations: int) -> list[PathTarget]:
        best = list(route)
        best_dist = self._total_distance(best, start, must_return)

        for _ in range(max_iterations):
            improved = False
            for i in range(len(best) - 1):
                for j in range(i + 1, len(best)):
                    new_route = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                    new_dist = self._total_distance(new_route, start, must_return)
                    if new_dist < best_dist:
                        best = new_route
                        best_dist = new_dist
                        improved = True
            if not improved:
                break

        return best

    def _total_distance(self, route: list[PathTarget],
                        start: tuple[float, float],
                        must_return: bool) -> float:
        if not route:
            return 0.0
        total = self._distance(start, route[0].position)
        for i in range(len(route) - 1):
            total += self._distance(route[i].position, route[i + 1].position)
        if must_return:
            total += self._distance(route[-1].position, start)
        return total

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


# ---------------------------------------------------------------------------
# 3D Spatial Navigation (N-18)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SpatialNode:
    """A node in 3D space for multi-layer navigation."""
    node_id: str
    position: tuple[float, float, float]  # (x, y, z)
    layer: int = 0                         # 0=overworld, 1=surface cave, 2=deep
    connections: list[str] = field(default_factory=list)
    transition_type: str = ""              # "stairs", "elevator", "tunnel", "teleport"


@dataclass(slots=True)
class SpatialPath:
    """A path through 3D space."""
    nodes: list[SpatialNode] = field(default_factory=list)
    total_distance: float = 0.0
    layer_transitions: int = 0


class SpatialNavigator:
    """Navigates multi-layer 3D environments (N-18).

    Handles pathfinding across overworld, caves, and underground areas.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, SpatialNode] = {}

    def add_node(self, node: SpatialNode) -> None:
        self._nodes[node.node_id] = node

    def find_path(self, start_id: str, end_id: str) -> SpatialPath | None:
        """Find shortest path between two spatial nodes using BFS."""
        if start_id not in self._nodes or end_id not in self._nodes:
            return None

        if start_id == end_id:
            return SpatialPath(nodes=[self._nodes[start_id]])

        # BFS
        visited: set[str] = {start_id}
        queue: list[list[str]] = [[start_id]]

        while queue:
            path = queue.pop(0)
            current = path[-1]
            node = self._nodes.get(current)
            if node is None:
                continue

            for neighbor_id in node.connections:
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                new_path = path + [neighbor_id]

                if neighbor_id == end_id:
                    nodes = [self._nodes[nid] for nid in new_path if nid in self._nodes]
                    transitions = sum(
                        1 for i in range(len(nodes) - 1)
                        if nodes[i].layer != nodes[i + 1].layer
                    )
                    return SpatialPath(
                        nodes=nodes,
                        layer_transitions=transitions,
                    )

                queue.append(new_path)

        return None

    def get_nodes_on_layer(self, layer: int) -> list[SpatialNode]:
        return [n for n in self._nodes.values() if n.layer == layer]


# ---------------------------------------------------------------------------
# Input primitives (I-15, I-16)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DragOperation:
    """A mouse drag operation specification."""
    start_x: float     # Normalised 0.0-1.0
    start_y: float
    end_x: float
    end_y: float
    duration_ms: int = 500
    reason: str = ""


@dataclass(slots=True)
class ScrollOperation:
    """A scroll wheel operation specification."""
    delta: int          # Positive=down, negative=up
    position_x: float = 0.5   # Normalised cursor position
    position_y: float = 0.5
    reason: str = ""


class InputPrimitiveBuilder:
    """Builds input primitive operations (I-15, I-16).

    Creates drag and scroll specifications compatible with UIFlowExecutor.
    """

    def build_map_drag(self, from_x: float, from_y: float,
                       dx: float, dy: float) -> DragOperation:
        """I-15: Build a map drag operation."""
        return DragOperation(
            start_x=from_x,
            start_y=from_y,
            end_x=min(max(from_x + dx, 0.0), 1.0),
            end_y=min(max(from_y + dy, 0.0), 1.0),
            duration_ms=300,
            reason="map_drag",
        )

    def build_party_drag(self, from_slot: int, to_slot: int) -> DragOperation:
        """I-15: Build a party slot drag operation."""
        slot_x = [0.25, 0.42, 0.58, 0.75]
        return DragOperation(
            start_x=slot_x[from_slot],
            start_y=0.50,
            end_x=slot_x[to_slot],
            end_y=0.50,
            duration_ms=500,
            reason=f"party_drag_{from_slot}_to_{to_slot}",
        )

    def build_scroll(self, clicks: int, reason: str = "") -> ScrollOperation:
        """I-16: Build a scroll operation."""
        return ScrollOperation(
            delta=clicks,
            reason=reason or "scroll",
        )

    def build_map_zoom(self, zoom_in: bool, clicks: int = 3) -> ScrollOperation:
        """I-16: Build a map zoom scroll operation."""
        return ScrollOperation(
            delta=-clicks if zoom_in else clicks,
            position_x=0.92,
            position_y=0.70,
            reason=f"map_zoom_{'in' if zoom_in else 'out'}",
        )
