from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app_service.product_e2e import ALLOWED_SAFE_WINDOW_MARKERS


@dataclass(frozen=True, slots=True)
class RecorderContext:
    active_window_title: str
    focus_state: str
    roi_profile: str
    observation_frame_id: int | None = None
    target_state: str = "UNKNOWN"
    visual_triggers: dict[str, bool] = field(default_factory=dict)


class RecorderBackend(Protocol):
    name: str

    def validate_context(self, context: RecorderContext) -> None:
        ...

    def seed_events(self, context: RecorderContext) -> list[dict[str, Any]]:
        ...


class MockRecorderBackend:
    name = "mock"

    def validate_context(self, context: RecorderContext) -> None:
        del context

    def seed_events(self, context: RecorderContext) -> list[dict[str, Any]]:
        now = time.time()
        return [
            {
                "event_type": "visual_snapshot_summary",
                "timestamp": now,
                "payload": {"summary": "target visible at center-ish"},
                "target_state": "TRACKED",
                "visual_triggers": {"target_visible": True},
            },
            {"event_type": "key_down", "timestamp": now + 0.05, "payload": {"key": "E"}, "target_state": "TRACKED"},
            {"event_type": "key_up", "timestamp": now + 0.13, "payload": {"key": "E"}, "target_state": "TRACKED"},
            {"event_type": "wait", "timestamp": now + 0.31, "payload": {"duration_ms": 180}, "target_state": "TRACKED"},
            {
                "event_type": "visual_snapshot_summary",
                "timestamp": now + 0.48,
                "payload": {"summary": "action completed"},
                "target_state": "TRACKED",
                "visual_triggers": {"action_completed": True, "target_visible": True},
                "visual_trigger_marker": "action_completed",
            },
        ]


class TestWindowRecorderBackend:
    name = "test-window"

    def validate_context(self, context: RecorderContext) -> None:
        title = context.active_window_title.lower()
        if not any(marker.lower() in title for marker in ALLOWED_SAFE_WINDOW_MARKERS):
            raise RuntimeError(
                "TestWindowRecorderBackend only records authorized pseudo3d/testbed/QA sandbox windows."
            )
        if context.focus_state != "FOCUSED":
            raise RuntimeError("Target test window must be focused before recording.")

    def seed_events(self, context: RecorderContext) -> list[dict[str, Any]]:
        now = time.time()
        return [
            {
                "event_type": "active_window",
                "timestamp": now,
                "payload": {"title": context.active_window_title},
                "target_state": context.target_state,
            },
            {
                "event_type": "visual_snapshot_summary",
                "timestamp": now + 0.01,
                "payload": {"frame_id": context.observation_frame_id, "roi_profile": context.roi_profile},
                "target_state": context.target_state,
                "visual_triggers": context.visual_triggers,
            },
        ]


class GlobalHookBackend:
    name = "global-hook"

    def validate_context(self, context: RecorderContext) -> None:
        del context
        raise RuntimeError(
            "GlobalHookBackend is intentionally disabled by default. Enable only for authorized test environments."
        )

    def seed_events(self, context: RecorderContext) -> list[dict[str, Any]]:
        del context
        return []


def backend_by_name(name: str) -> RecorderBackend:
    if name == "test-window":
        return TestWindowRecorderBackend()
    if name == "global-hook":
        return GlobalHookBackend()
    return MockRecorderBackend()
