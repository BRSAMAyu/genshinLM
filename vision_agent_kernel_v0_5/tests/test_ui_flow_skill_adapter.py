from __future__ import annotations

from typing import Any

from core.types import InputLease
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter


class _Rect:
    left = 0
    top = 0
    width = 1920
    height = 1080


class _Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def client_rect(self) -> _Rect:
        return _Rect()

    def click_at(self, x: int, y: int, reason: str = "") -> None:
        self.calls.append(("click_at", x, y, reason))

    def key_down(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_down", key, reason))

    def key_up(self, key: str, reason: str = "") -> None:
        self.calls.append(("key_up", key, reason))

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> None:
        self.calls.append(("mouse_scroll", delta, reason))

    def action_intent(self, intent: str, reason: str = "") -> None:
        self.calls.append(("action_intent", intent, reason))

    def is_target_focused(self) -> bool:
        return True


class _Worker:
    def __init__(self, backend: _Backend) -> None:
        self.backend = backend
        self.leases: list[InputLease] = []

    def submit_lease(self, lease: InputLease) -> bool:
        self.leases.append(lease)
        for key, state in lease.key_states.items():
            if state == "DOWN":
                self.backend.key_down(key, reason=lease.reason)
            elif state == "UP":
                self.backend.key_up(key, reason=lease.reason)
        return True


def test_adapter_routes_known_flow_name() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("character_level_up")
    assert adapter.execute_semantic("character_level_up", "", {})

    assert any(call[0] == "click_at" for call in backend.calls)


def test_adapter_routes_semantic_alias_to_flow() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.can_handle("level_up_character")
    assert adapter.execute_semantic("level_up_character", "", {})

    assert any(call[0] == "click_at" for call in backend.calls)


def test_adapter_handles_primitive_action_without_real_input() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert adapter.execute_semantic("navigate_walk", "north", {})

    assert ("action_intent", "navigate_walk:north", "semantic_action_intent") in backend.calls


def test_adapter_rejects_unknown_semantic_action() -> None:
    backend = _Backend()
    adapter = UIFlowSkillAdapter(input_worker=_Worker(backend))  # type: ignore[arg-type]

    assert not adapter.can_handle("not_a_real_action")
    assert not adapter.execute_semantic("not_a_real_action", "", {})
