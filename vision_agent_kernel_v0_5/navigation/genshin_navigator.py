from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
import yaml
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NavigationState:
    active: bool
    target_waypoint: str
    current_region: str
    progress: float
    method: str
    eta_seconds: float


@dataclass(frozen=True, slots=True)
class _GraphEdge:
    to_id: str
    cost: float
    method: str


class GenshinNavigator:
    """In-game navigation using minimap and teleport system."""

    _WAYPOINT_ALIASES: dict[str, str] = {
        "mondstadt_windrise": "mon_windrise",
        "sumeru_city": "sum_sumeru_city",
        "fontaine_court": "fon_court",
        "natlan_stadium": "nat_stadium",
    }

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self._state = NavigationState(False, "", "unknown", 0.0, "idle", 0.0)
        self._waypoint_reached_threshold_px = 30
        self._adj: dict[str, list[_GraphEdge]] = {}
        self._waypoint_regions: dict[str, str] = {}
        self._waypoint_positions: dict[str, list[float]] = {}
        self._loaded = False
        self._knowledge_dir = _resolve_knowledge_dir(knowledge_dir)

    def _ensure_graph(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        graph_path = self._knowledge_dir / "genshin_world_graph.yaml"
        if not graph_path.exists():
            return
        raw = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}

        for wp in raw.get("waypoints", []):
            wid = str(wp["waypoint_id"])
            self._waypoint_regions[wid] = str(wp.get("region", "unknown"))
            self._waypoint_positions[wid] = [float(v) for v in wp.get("position", [0, 0, 0])]

        for edge in raw.get("edges", []):
            from_id = str(edge["from_id"])
            to_id = str(edge["to_id"])
            cost = float(edge.get("cost", 1.0))
            method = str(edge.get("method", "walk"))
            self._adj.setdefault(from_id, []).append(_GraphEdge(to_id, cost, method))
            self._adj.setdefault(to_id, []).append(_GraphEdge(from_id, cost, method))

        for alias, canonical in self._WAYPOINT_ALIASES.items():
            if canonical not in self._waypoint_regions:
                continue
            self._waypoint_regions[alias] = self._waypoint_regions[canonical]
            self._waypoint_positions[alias] = list(self._waypoint_positions.get(canonical, [0.0, 0.0, 0.0]))
            self._adj.setdefault(alias, []).append(_GraphEdge(canonical, 0.0, "alias"))
            self._adj.setdefault(canonical, []).append(_GraphEdge(alias, 0.0, "alias"))

    def plan_route(self, from_id: str, to_id: str) -> list[str]:
        """Plan shortest route between two waypoints using world graph.

        Uses Dijkstra's algorithm on the world graph edges.
        Returns ordered list of waypoint IDs to traverse.
        """
        self._ensure_graph()
        if from_id == to_id:
            return [from_id]

        queue: list[tuple[float, str, list[str]]] = [(0.0, from_id, [from_id])]
        best: dict[str, float] = {from_id: 0.0}

        while queue:
            cost, node, path = heapq.heappop(queue)
            if node == to_id:
                return path
            if cost > best.get(node, math.inf):
                continue
            for edge in self._adj.get(node, []):
                next_cost = cost + edge.cost
                if next_cost < best.get(edge.to_id, math.inf):
                    best[edge.to_id] = next_cost
                    heapq.heappush(queue, (next_cost, edge.to_id, [*path, edge.to_id]))

        return []

    def detect_minimap_direction(self, minimap_roi: np.ndarray) -> float:
        """Detect quest marker direction from minimap.

        Returns angle in degrees (0=up, clockwise positive).
        Quest markers appear as colored indicators on the minimap.
        """
        if minimap_roi.size == 0:
            return 0.0

        hsv = _to_hsv(minimap_roi)

        yellow_mask = ((hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 35)
                       & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 100))

        blue_mask = ((hsv[:, :, 0] >= 100) & (hsv[:, :, 0] <= 130)
                     & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 100))

        combined = yellow_mask | blue_mask
        if not combined.any():
            return 0.0

        ys, xs = np.nonzero(combined)
        h, w = minimap_roi.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        marker_x = float(np.mean(xs))
        marker_y = float(np.mean(ys))

        dx = marker_x - cx
        dy = cy - marker_y  # y-axis inverted: up is negative in image coords

        angle = math.degrees(math.atan2(dx, dy))
        if angle < 0:
            angle += 360.0
        return angle

    def compute_movement(self, target_angle: float) -> tuple[str, float]:
        """Convert target angle to WASD movement.

        Args:
            target_angle: Angle to target in degrees (0=forward)

        Returns:
            (movement_keys, duration_ms) e.g. ("w", 500), ("wd", 300)
        """
        a = target_angle % 360.0

        if a < 22.5 or a >= 337.5:
            return ("w", 500)
        if a < 67.5:
            return ("wd", 400)
        if a < 112.5:
            return ("d", 500)
        if a < 157.5:
            return ("sd", 400)
        if a < 202.5:
            return ("s", 500)
        if a < 247.5:
            return ("sa", 400)
        if a < 292.5:
            return ("a", 500)
        return ("wa", 400)

    def check_arrival(self, minimap_roi: np.ndarray) -> bool:
        """Check if we've arrived at destination.

        Arrival indicators: quest marker centered, interaction prompt visible,
        or waypoint icon changes on minimap.
        """
        if minimap_roi.size == 0:
            return False

        hsv = _to_hsv(minimap_roi)

        yellow_mask = ((hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 35)
                       & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 100))

        if not yellow_mask.any():
            return False

        ys, xs = np.nonzero(yellow_mask)
        h, w = minimap_roi.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        dist = math.hypot(float(np.mean(xs)) - cx, float(np.mean(ys)) - cy)
        return dist < self._waypoint_reached_threshold_px

    def execute_teleport_sequence(self) -> list[dict]:
        """Generate the input sequence for teleporting.

        Steps:
        1. Press M to open map
        2. Wait for map screen
        3. Select region tab (if needed)
        4. Click on target waypoint
        5. Click teleport button
        6. Wait for loading screen to end

        Returns list of input actions.
        """
        return [
            {"input": "press_key", "key": "m", "label": "open_map"},
            {"input": "wait_screen", "screen": "map_screen", "timeout_ms": 2000},
            {"input": "click_at", "target": "map_waypoint", "label": "select_waypoint"},
            {"input": "click_at", "target": "teleport_button", "label": "confirm_teleport"},
            {"input": "wait_screen", "screen": "world_hud", "timeout_ms": 15000},
        ]

    @property
    def state(self) -> NavigationState:
        return self._state

    def get_waypoint_region(self, waypoint_id: str) -> str:
        self._ensure_graph()
        return self._waypoint_regions.get(waypoint_id, "unknown")


def _to_hsv(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        image = image[:, :, np.newaxis]
        image = np.repeat(image, 3, axis=2)
    if image.shape[2] == 4:
        image = image[:, :, :3]
    import cv2
    return cv2.cvtColor(image, cv2.COLOR_BGR2HSV)


def _resolve_knowledge_dir(knowledge_dir: Path | None) -> Path:
    module_dir = Path(__file__).resolve().parents[1] / "knowledge"
    if knowledge_dir is None:
        return module_dir
    path = Path(knowledge_dir)
    if path.exists():
        return path
    if not path.is_absolute():
        fallback = module_dir.parent / path
        if fallback.exists():
            return fallback
        if path.name == module_dir.name:
            return module_dir
    return path
