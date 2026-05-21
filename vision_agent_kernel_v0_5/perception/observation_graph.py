from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from core.types import Observation
from interaction.ui_anchor import NormalizedRect, UIElement


ObservationNodeKind = Literal[
    "frame",
    "screen_state",
    "ui_element",
    "ocr_block",
    "detected_object",
    "target_track",
    "danger_signal",
    "quest_signal",
    "navigation_signal",
    "boss_phase_signal",
    "telegraph_signal",
    "punish_window_signal",
    "combat_resource_signal",
    "capsule_extension",
]


@dataclass(frozen=True, slots=True)
class ObservationNode:
    node_id: str
    kind: ObservationNodeKind
    frame_id: int
    roi_id: str
    bbox: NormalizedRect | None
    confidence: float
    source: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObservationGraph:
    graph_id: str
    frame_id: int
    viewport: tuple[int, int]
    created_at: float
    nodes: list[ObservationNode] = field(default_factory=list)

    def by_kind(self, kind: ObservationNodeKind) -> list[ObservationNode]:
        return [node for node in self.nodes if node.kind == kind]

    def ui_elements(self) -> list[UIElement]:
        elements: list[UIElement] = []
        for node in self.by_kind("ui_element"):
            if node.bbox is None:
                continue
            elements.append(
                UIElement(
                    element_id=node.node_id,
                    role=str(node.payload.get("role", "")),
                    bbox=node.bbox,
                    confidence=node.confidence,
                    source=node.source,
                    text=str(node.payload.get("text", "")),
                    icon_id=str(node.payload.get("icon_id", "")),
                    detector_class=str(node.payload.get("detector_class", "")),
                    metadata=dict(node.payload.get("metadata", {})),
                )
            )
        return elements

    def screen_state(self) -> str | None:
        states = sorted(self.by_kind("screen_state"), key=lambda node: node.confidence, reverse=True)
        if not states:
            return None
        return str(states[0].payload.get("state", "unknown"))

    def evidence_summary(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "frame_id": self.frame_id,
            "viewport": self.viewport,
            "node_count": len(self.nodes),
            "kinds": {kind: len(self.by_kind(kind)) for kind in _KINDS},
        }


_KINDS: tuple[ObservationNodeKind, ...] = (
    "frame",
    "screen_state",
    "ui_element",
    "ocr_block",
    "detected_object",
    "target_track",
    "danger_signal",
    "quest_signal",
    "navigation_signal",
    "boss_phase_signal",
    "telegraph_signal",
    "punish_window_signal",
    "combat_resource_signal",
    "capsule_extension",
)


class ObservationBuilder:
    """Build a typed observation graph from the existing Observation object."""

    def build(self, observation: Observation, capsule_id: str = "core") -> ObservationGraph:
        nodes: list[ObservationNode] = []
        viewport = observation.viewport_size
        ts = observation.t_processed or time.time()
        nodes.append(
            ObservationNode(
                node_id=f"frame:{observation.frame_id}",
                kind="frame",
                frame_id=observation.frame_id,
                roi_id="full_frame",
                bbox=NormalizedRect(0.0, 0.0, 1.0, 1.0),
                confidence=1.0,
                source="perception_pipeline",
                timestamp=ts,
                payload={"latency_ms": observation.latency_ms, "capsule_id": capsule_id},
            )
        )
        if observation.ui_state is not None:
            nodes.append(
                ObservationNode(
                    node_id=f"screen_state:{observation.ui_state.frame_id}",
                    kind="screen_state",
                    frame_id=observation.frame_id,
                    roi_id="screen",
                    bbox=None,
                    confidence=observation.ui_state.confidence,
                    source="ui_state_estimate",
                    timestamp=observation.ui_state.timestamp,
                    payload={"state": observation.ui_state.state, **observation.ui_state.payload},
                )
            )
        if observation.target_track is not None:
            track = observation.target_track
            bbox = NormalizedRect.from_px(track.bbox_xyxy, viewport) if track.bbox_xyxy else None
            nodes.append(
                ObservationNode(
                    node_id=f"target_track:{track.track_id}",
                    kind="target_track",
                    frame_id=observation.frame_id,
                    roi_id="target",
                    bbox=bbox,
                    confidence=track.confidence,
                    source="tracker",
                    timestamp=ts,
                    payload={
                        "track_id": track.track_id,
                        "class_id": track.class_id,
                        "bearing_deg": track.bearing_deg,
                        "missing_duration_ms": track.missing_duration_ms,
                    },
                )
            )
        nodes.extend(self._nodes_from_extension(observation, "ui_elements", "ui_element"))
        nodes.extend(self._nodes_from_extension(observation, "ocr_blocks", "ocr_block"))
        nodes.extend(self._nodes_from_extension(observation, "detected_objects", "detected_object"))
        nodes.extend(self._nodes_from_extension(observation, "danger_signals", "danger_signal"))
        nodes.extend(self._nodes_from_extension(observation, "quest_signals", "quest_signal"))
        nodes.extend(self._nodes_from_extension(observation, "navigation_signals", "navigation_signal"))
        nodes.extend(self._nodes_from_extension(observation, "boss_phase_signals", "boss_phase_signal"))
        nodes.extend(self._nodes_from_extension(observation, "telegraph_signals", "telegraph_signal"))
        nodes.extend(self._nodes_from_extension(observation, "punish_window_signals", "punish_window_signal"))
        nodes.extend(self._nodes_from_extension(observation, "combat_resource_signals", "combat_resource_signal"))
        for key, value in observation.extensions.items():
            if key in {
                "ui_elements",
                "ocr_blocks",
                "detected_objects",
                "danger_signals",
                "quest_signals",
                "navigation_signals",
                "boss_phase_signals",
                "telegraph_signals",
                "punish_window_signals",
                "combat_resource_signals",
            }:
                continue
            nodes.append(
                ObservationNode(
                    node_id=f"extension:{key}:{observation.frame_id}",
                    kind="capsule_extension",
                    frame_id=observation.frame_id,
                    roi_id=key,
                    bbox=None,
                    confidence=1.0,
                    source="observation.extensions",
                    timestamp=ts,
                    payload={"key": key, "value": value},
                )
            )
        return ObservationGraph(
            graph_id=f"obs:{capsule_id}:{observation.frame_id}",
            frame_id=observation.frame_id,
            viewport=viewport,
            created_at=ts,
            nodes=nodes,
        )

    def _nodes_from_extension(
        self,
        observation: Observation,
        key: str,
        kind: ObservationNodeKind,
    ) -> list[ObservationNode]:
        raw = observation.extensions.get(key, [])
        if isinstance(raw, dict):
            items: Iterable[Any] = [raw]
        elif isinstance(raw, list):
            items = raw
        else:
            return []

        nodes: list[ObservationNode] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            bbox = self._bbox(item, observation.viewport_size)
            confidence = float(item.get("confidence", item.get("score", 1.0)))
            node_id = str(item.get("id") or item.get("node_id") or f"{kind}:{observation.frame_id}:{index}")
            nodes.append(
                ObservationNode(
                    node_id=node_id,
                    kind=kind,
                    frame_id=int(item.get("frame_id", observation.frame_id)),
                    roi_id=str(item.get("roi_id", key)),
                    bbox=bbox,
                    confidence=confidence,
                    source=str(item.get("source", key)),
                    timestamp=float(item.get("timestamp", observation.t_processed)),
                    payload={k: v for k, v in item.items() if k not in {"bbox", "bbox_xyxy", "bbox_norm"}},
                )
            )
        return nodes

    def _bbox(self, item: dict[str, Any], viewport: tuple[int, int]) -> NormalizedRect | None:
        if "bbox_norm" in item:
            x, y, w, h = item["bbox_norm"]
            return NormalizedRect(float(x), float(y), float(w), float(h)).clamp()
        if "bbox_xyxy" in item:
            x1, y1, x2, y2 = item["bbox_xyxy"]
            return NormalizedRect.from_px((float(x1), float(y1), float(x2), float(y2)), viewport)
        if "bbox" in item:
            bbox = item["bbox"]
            if len(bbox) == 4:
                x, y, w, h = bbox
                if max(float(x), float(y), float(w), float(h)) <= 1.0:
                    return NormalizedRect(float(x), float(y), float(w), float(h)).clamp()
                return NormalizedRect.from_px((float(x), float(y), float(x) + float(w), float(y) + float(h)), viewport)
        return None
