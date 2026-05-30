"""Tests for advanced perception, navigation, and input capabilities."""
from __future__ import annotations

import pytest

from perception.advanced_perception import (
    DragOperation,
    GameTextReader,
    InputPrimitiveBuilder,
    MapRegionInfo,
    MaterialInfo,
    MultiTargetPathOptimizer,
    OCRResult,
    PathTarget,
    PuzzleDetection,
    PuzzleDetector,
    PuzzleState,
    ScrollOperation,
    SkillDescription,
    SpatialNavigator,
    SpatialNode,
    SpatialPath,
)


# ---------------------------------------------------------------------------
# GameTextReader (P-23, P-24, P-25)
# ---------------------------------------------------------------------------
class TestGameTextReader:
    def test_read_map_region(self) -> None:
        reader = GameTextReader()
        result = reader.read_map_region([
            OCRResult("Liyue Harbor", 0.9),
            OCRResult("Qingce Village", 0.7),
        ])
        assert result is not None
        assert result.region_name == "Liyue Harbor"
        assert result.confidence == pytest.approx(0.9)

    def test_read_map_region_empty(self) -> None:
        reader = GameTextReader()
        assert reader.read_map_region([]) is None

    def test_read_material_info(self) -> None:
        reader = GameTextReader()
        result = reader.read_material_info([
            OCRResult("Damaged Mask"),
            OCRResult("x15"),
        ])
        assert result is not None
        assert result.name == "Damaged Mask"
        assert result.quantity == 15

    def test_read_material_info_no_quantity(self) -> None:
        reader = GameTextReader()
        result = reader.read_material_info([OCRResult("Some Item")])
        assert result is not None
        assert result.quantity == 0

    def test_read_skill_description(self) -> None:
        reader = GameTextReader()
        result = reader.read_skill_description([
            OCRResult("Elemental Skill"),
            OCRResult("Deals Pyro DMG"),
        ])
        assert result is not None
        assert result.skill_name == "Elemental Skill"
        assert "Pyro DMG" in result.description

    def test_read_skill_empty(self) -> None:
        reader = GameTextReader()
        assert reader.read_skill_description([]) is None


# ---------------------------------------------------------------------------
# PuzzleDetector (P-29)
# ---------------------------------------------------------------------------
class TestPuzzleDetector:
    def test_inactive_puzzle(self) -> None:
        det = PuzzleDetector()
        result = det.detect_puzzle_state("torch", is_glowing=False)
        assert result.state == PuzzleState.INACTIVE

    def test_activated_puzzle(self) -> None:
        det = PuzzleDetector()
        result = det.detect_puzzle_state("element_pillar", is_glowing=True,
                                          element="pyro")
        assert result.state == PuzzleState.ACTIVATED
        assert result.required_element == "pyro"

    def test_error_state(self) -> None:
        det = PuzzleDetector()
        result = det.detect_puzzle_state("totem", is_glowing=True,
                                          has_error_indicator=True)
        assert result.state == PuzzleState.ERROR

    def test_check_completion_solved(self) -> None:
        det = PuzzleDetector()
        detections = [
            PuzzleDetection("torch", PuzzleState.ACTIVATED),
            PuzzleDetection("torch", PuzzleState.ACTIVATED),
            PuzzleDetection("torch", PuzzleState.ACTIVATED),
        ]
        assert det.check_puzzle_completion(detections) == PuzzleState.SOLVED

    def test_check_completion_error(self) -> None:
        det = PuzzleDetector()
        detections = [
            PuzzleDetection("torch", PuzzleState.ACTIVATED),
            PuzzleDetection("torch", PuzzleState.ERROR),
        ]
        assert det.check_puzzle_completion(detections) == PuzzleState.ERROR

    def test_check_completion_incomplete(self) -> None:
        det = PuzzleDetector()
        detections = [
            PuzzleDetection("torch", PuzzleState.ACTIVATED),
            PuzzleDetection("torch", PuzzleState.INACTIVE),
        ]
        assert det.check_puzzle_completion(detections) == PuzzleState.INACTIVE

    def test_check_completion_empty(self) -> None:
        det = PuzzleDetector()
        assert det.check_puzzle_completion([]) == PuzzleState.UNKNOWN


# ---------------------------------------------------------------------------
# MultiTargetPathOptimizer (N-15)
# ---------------------------------------------------------------------------
class TestMultiTargetPathOptimizer:
    def test_empty_targets(self) -> None:
        opt = MultiTargetPathOptimizer()
        result = opt.optimize([])
        assert len(result.ordered_targets) == 0

    def test_single_target(self) -> None:
        opt = MultiTargetPathOptimizer()
        targets = [PathTarget("t1", (10.0, 0.0))]
        result = opt.optimize(targets, start_position=(0.0, 0.0))
        assert len(result.ordered_targets) == 1
        assert result.total_distance == pytest.approx(10.0)

    def test_multiple_targets_ordered(self) -> None:
        opt = MultiTargetPathOptimizer()
        targets = [
            PathTarget("t1", (1.0, 0.0)),
            PathTarget("t2", (3.0, 0.0)),
            PathTarget("t3", (5.0, 0.0)),
        ]
        result = opt.optimize(targets, start_position=(0.0, 0.0))
        assert len(result.ordered_targets) == 3
        # Should visit in order along x-axis
        ids = [t.target_id for t in result.ordered_targets]
        assert ids == ["t1", "t2", "t3"]

    def test_nearest_neighbor_routing(self) -> None:
        opt = MultiTargetPathOptimizer()
        targets = [
            PathTarget("far", (100.0, 100.0)),
            PathTarget("near1", (1.0, 0.0)),
            PathTarget("near2", (2.0, 0.0)),
        ]
        result = opt.optimize(targets, start_position=(0.0, 0.0))
        # Near targets should come first
        ids = [t.target_id for t in result.ordered_targets]
        assert ids.index("near1") < ids.index("far")
        assert ids.index("near2") < ids.index("far")

    def test_return_trip_adds_distance(self) -> None:
        opt = MultiTargetPathOptimizer()
        targets = [
            PathTarget("t1", (5.0, 0.0)),
            PathTarget("t2", (10.0, 0.0)),
        ]
        result_no_return = opt.optimize(targets, (0.0, 0.0), must_return=False)
        result_return = opt.optimize(targets, (0.0, 0.0), must_return=True)
        assert result_return.total_distance > result_no_return.total_distance


# ---------------------------------------------------------------------------
# SpatialNavigator (N-18)
# ---------------------------------------------------------------------------
class TestSpatialNavigator:
    def test_add_and_find(self) -> None:
        nav = SpatialNavigator()
        nav.add_node(SpatialNode("a", (0, 0, 0), connections=["b"]))
        nav.add_node(SpatialNode("b", (10, 0, 1), layer=1, connections=["a"]))
        path = nav.find_path("a", "b")
        assert path is not None
        assert len(path.nodes) == 2
        assert path.layer_transitions == 1

    def test_same_node(self) -> None:
        nav = SpatialNavigator()
        nav.add_node(SpatialNode("a", (0, 0, 0)))
        path = nav.find_path("a", "a")
        assert path is not None
        assert len(path.nodes) == 1

    def test_no_path(self) -> None:
        nav = SpatialNavigator()
        nav.add_node(SpatialNode("a", (0, 0, 0)))
        nav.add_node(SpatialNode("b", (10, 0, 0)))  # No connections
        path = nav.find_path("a", "b")
        assert path is None

    def test_multi_hop(self) -> None:
        nav = SpatialNavigator()
        nav.add_node(SpatialNode("a", (0, 0, 0), connections=["b"]))
        nav.add_node(SpatialNode("b", (5, 0, 1), layer=1, connections=["a", "c"]))
        nav.add_node(SpatialNode("c", (10, 0, 2), layer=2, connections=["b"]))
        path = nav.find_path("a", "c")
        assert path is not None
        assert len(path.nodes) == 3
        assert path.layer_transitions == 2

    def test_missing_node(self) -> None:
        nav = SpatialNavigator()
        assert nav.find_path("missing", "also_missing") is None

    def test_layer_filter(self) -> None:
        nav = SpatialNavigator()
        nav.add_node(SpatialNode("a", (0, 0, 0), layer=0))
        nav.add_node(SpatialNode("b", (5, 0, 1), layer=1))
        nav.add_node(SpatialNode("c", (10, 0, 1), layer=1))
        layer1 = nav.get_nodes_on_layer(1)
        assert len(layer1) == 2


# ---------------------------------------------------------------------------
# InputPrimitiveBuilder (I-15, I-16)
# ---------------------------------------------------------------------------
class TestInputPrimitiveBuilder:
    def test_map_drag(self) -> None:
        builder = InputPrimitiveBuilder()
        drag = builder.build_map_drag(0.5, 0.5, 0.1, -0.1)
        assert drag.start_x == pytest.approx(0.5)
        assert drag.end_x == pytest.approx(0.6)
        assert drag.end_y == pytest.approx(0.4)
        assert drag.reason == "map_drag"

    def test_map_drag_clamped(self) -> None:
        builder = InputPrimitiveBuilder()
        drag = builder.build_map_drag(0.95, 0.95, 0.2, 0.2)
        assert drag.end_x <= 1.0
        assert drag.end_y <= 1.0

    def test_party_drag(self) -> None:
        builder = InputPrimitiveBuilder()
        drag = builder.build_party_drag(0, 3)
        assert drag.start_x == pytest.approx(0.25)
        assert drag.end_x == pytest.approx(0.75)

    def test_scroll(self) -> None:
        builder = InputPrimitiveBuilder()
        scroll = builder.build_scroll(5, "list_scroll")
        assert scroll.delta == 5
        assert scroll.reason == "list_scroll"

    def test_map_zoom_in(self) -> None:
        builder = InputPrimitiveBuilder()
        scroll = builder.build_map_zoom(zoom_in=True, clicks=3)
        assert scroll.delta == -3
        assert "zoom_in" in scroll.reason

    def test_map_zoom_out(self) -> None:
        builder = InputPrimitiveBuilder()
        scroll = builder.build_map_zoom(zoom_in=False)
        assert scroll.delta > 0
        assert "zoom_out" in scroll.reason
