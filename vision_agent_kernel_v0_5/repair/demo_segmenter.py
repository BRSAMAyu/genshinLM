"""Segment repair demonstration events into actionable segments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from repair.repair_session import RepairEvent


@dataclass(slots=True)
class DemoSegment:
    """A contiguous group of actions within a demonstration."""

    segment_id: str
    session_id: str
    start_event_id: str
    end_event_id: str
    action_type: str
    params: dict[str, object]


class DemoSegmenter:
    """Break a repair session's events into actionable segments.

    Grouping strategy: consecutive ``action_recorded`` events that share the
    same ``action_type`` are folded into a single segment.  A change of
    ``action_type`` starts a new segment.
    """

    def segment(self, events: list[RepairEvent]) -> list[DemoSegment]:
        """Break a repair session's events into actionable segments."""
        action_events = [e for e in events if e.event_type == "action_recorded"]
        if not action_events:
            return []

        segments: list[DemoSegment] = []
        # Group consecutive events by action_type
        group_start_idx = 0
        current_action_type = action_events[0].payload.get("action_type", "unknown")

        for i in range(1, len(action_events)):
            evt_action = action_events[i].payload.get("action_type", "unknown")
            if evt_action != current_action_type:
                # Close current group
                segments.append(self._build_segment(
                    action_events[group_start_idx:i],
                ))
                group_start_idx = i
                current_action_type = evt_action

        # Close the last group
        segments.append(self._build_segment(
            action_events[group_start_idx:],
        ))
        return segments

    def _build_segment(self, group: list[RepairEvent]) -> DemoSegment:
        """Build a DemoSegment from a list of same-type action events."""
        first = group[0]
        last = group[-1]
        action_type = str(first.payload.get("action_type", "unknown"))
        # Merge params from all events in the group
        merged_params: dict[str, object] = {}
        for evt in group:
            params = evt.payload.get("params")
            if isinstance(params, dict):
                merged_params.update(params)

        return DemoSegment(
            segment_id=str(uuid.uuid4()),
            session_id=first.session_id,
            start_event_id=first.event_id,
            end_event_id=last.event_id,
            action_type=action_type,
            params=merged_params,
        )
