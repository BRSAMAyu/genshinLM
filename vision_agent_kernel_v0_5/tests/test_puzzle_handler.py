"""Tests for interaction/puzzle_handler.py — exploration puzzle/challenge handling."""
from __future__ import annotations

import threading

import pytest

from interaction.puzzle_handler import (
    PuzzleAction,
    PuzzleHandler,
    PuzzleSolution,
    PuzzleState,
    PuzzleType,
)


class _FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def key_press(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_press", key, reason))

    def click_at_normalized(self, nx: float, ny: float, reason: str = "") -> None:
        self.calls.append(("click", f"{nx:.2f},{ny:.2f}", reason))


# ---------------------------------------------------------------------------
# PuzzleType enum
# ---------------------------------------------------------------------------

class TestPuzzleType:
    def test_all_types_exist(self) -> None:
        assert PuzzleType.ELEMENTAL_MONUMENT.value == "elemental_monument"
        assert PuzzleType.TORCH.value == "torch"
        assert PuzzleType.PRESSURE_PLATE.value == "pressure_plate"
        assert PuzzleType.TIMED_CHALLENGE.value == "timed_challenge"
        assert PuzzleType.WITHERING_ZONE.value == "withering_zone"

    def test_five_types(self) -> None:
        assert len(PuzzleType) == 5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TestDataTypes:
    def test_puzzle_action_frozen(self) -> None:
        action = PuzzleAction(action_type="use_element", element="pyro")
        assert action.element == "pyro"
        with pytest.raises(AttributeError):
            action.element = "hydro"  # type: ignore[misc]

    def test_puzzle_state_mutable(self) -> None:
        state = PuzzleState(puzzle_type=PuzzleType.TORCH)
        state.actions_executed = 3
        assert state.actions_executed == 3

    def test_puzzle_solution_frozen(self) -> None:
        sol = PuzzleSolution(puzzle_type=PuzzleType.TORCH, confidence=0.5)
        assert sol.confidence == 0.5


# ---------------------------------------------------------------------------
# PuzzleHandler — planning
# ---------------------------------------------------------------------------

class TestPuzzlePlanning:

    def test_plan_timed_challenge(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.TIMED_CHALLENGE)
        assert sol.puzzle_type == PuzzleType.TIMED_CHALLENGE
        assert len(sol.actions) == 3
        assert not sol.requires_vlm

    def test_plan_withering_zone(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.WITHERING_ZONE)
        assert len(sol.actions) == 3
        assert any(a.element == "dendro" for a in sol.actions)

    def test_plan_elemental_monument_no_vlm(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.ELEMENTAL_MONUMENT)
        assert sol.requires_vlm is True

    def test_plan_elemental_monument_with_vlm(self) -> None:
        vlm = lambda frame, **kw: {"element": "pyro"}
        h = PuzzleHandler(vlm_analyze=vlm)
        sol = h.plan_solution(PuzzleType.ELEMENTAL_MONUMENT)
        assert len(sol.actions) == 1
        assert sol.actions[0].element == "pyro"

    def test_plan_torch_has_pyro(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.TORCH)
        assert all(a.element == "pyro" for a in sol.actions)

    def test_plan_pressure_plate_has_geo(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.PRESSURE_PLATE)
        assert len(sol.actions) >= 1
        assert sol.actions[0].element == "geo"


# ---------------------------------------------------------------------------
# PuzzleHandler — execution
# ---------------------------------------------------------------------------

class TestPuzzleExecution:

    def test_execute_timed_challenge(self) -> None:
        backend = _FakeBackend()
        h = PuzzleHandler(backend=backend)
        sol = h.plan_solution(PuzzleType.TIMED_CHALLENGE)
        state = h.execute_solution(sol)
        assert state.completed is True
        assert state.actions_executed == 3
        assert len(backend.calls) >= 2

    def test_execute_shutdown_interrupts(self) -> None:
        backend = _FakeBackend()
        h = PuzzleHandler(backend=backend)
        sol = PuzzleSolution(
            puzzle_type=PuzzleType.TORCH,
            actions=tuple(PuzzleAction(action_type="attack", reason=f"a{i}", delay_ms=100) for i in range(10)),
        )
        event = threading.Event()
        event.set()
        state = h.execute_solution(sol, shutdown_event=event)
        assert state.failed is True
        assert state.failure_reason == "shutdown_requested"

    def test_execute_no_backend_no_crash(self) -> None:
        h = PuzzleHandler()
        sol = h.plan_solution(PuzzleType.WITHERING_ZONE)
        state = h.execute_solution(sol)
        assert state.completed is True

    def test_solve_puzzle_end_to_end(self) -> None:
        backend = _FakeBackend()
        h = PuzzleHandler(backend=backend)
        state = h.solve_puzzle(PuzzleType.TIMED_CHALLENGE)
        assert state.completed is True
        assert state.puzzle_type == PuzzleType.TIMED_CHALLENGE


# ---------------------------------------------------------------------------
# VLM integration
# ---------------------------------------------------------------------------

class TestVLMDetection:

    def test_detect_puzzle_type_with_vlm(self) -> None:
        vlm = lambda frame, **kw: {"puzzle_type": "torch"}
        h = PuzzleHandler(vlm_analyze=vlm)
        result = h.detect_puzzle_type("fake_frame")
        assert result == PuzzleType.TORCH

    def test_detect_puzzle_type_no_vlm(self) -> None:
        h = PuzzleHandler()
        result = h.detect_puzzle_type("fake_frame")
        assert result is None

    def test_detect_puzzle_type_vlm_error(self) -> None:
        def bad_vlm(frame, **kw):
            raise RuntimeError("VLM failed")
        h = PuzzleHandler(vlm_analyze=bad_vlm)
        result = h.detect_puzzle_type("fake_frame")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
