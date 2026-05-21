from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from interaction.ui_anchor import NormalizedRect
from perception.observation_graph import ObservationGraph


DesktopNodeRole = Literal["window", "panel", "list", "button", "text", "icon", "selected_item", "modal", "unknown"]


@dataclass(frozen=True, slots=True)
class DesktopNode:
    node_id: str
    role: DesktopNodeRole
    bbox: NormalizedRect | None
    confidence: float
    source: str
    text: str = ""
    state: str = "unknown"
    children: list[str] = field(default_factory=list)
    evidence_ref: str = ""
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DesktopTree:
    tree_id: str
    root_id: str
    screen_state: str
    viewport: tuple[int, int]
    nodes: dict[str, DesktopNode]

    def by_role(self, role: DesktopNodeRole) -> list[DesktopNode]:
        return [node for node in self.nodes.values() if node.role == role]

    def find_text(self, needle: str) -> list[DesktopNode]:
        lowered = needle.lower()
        return [node for node in self.nodes.values() if lowered in node.text.lower()]


class DesktopTreeBuilder:
    """Build a fallback universal UI tree from observation evidence."""

    def build(self, graph: ObservationGraph) -> DesktopTree:
        root_id = f"desktop_root:{graph.graph_id}"
        nodes: dict[str, DesktopNode] = {
            root_id: DesktopNode(
                node_id=root_id,
                role="window",
                bbox=NormalizedRect(0.0, 0.0, 1.0, 1.0),
                confidence=1.0,
                source="observation_graph",
                state=graph.screen_state() or "unknown",
                evidence_ref=graph.graph_id,
            )
        }
        child_ids: list[str] = []
        for element in graph.ui_elements():
            role = _role_from(element.role, element.text, element.icon_id)
            node = DesktopNode(
                node_id=element.element_id,
                role=role,
                bbox=element.bbox,
                confidence=element.confidence,
                source=element.source,
                text=element.text,
                state=str(element.metadata.get("state", "unknown")),
                evidence_ref=element.element_id,
                payload={"icon_id": element.icon_id, "detector_class": element.detector_class},
            )
            nodes[node.node_id] = node
            child_ids.append(node.node_id)
        for node in graph.by_kind("ocr_block"):
            if node.node_id in nodes:
                continue
            nodes[node.node_id] = DesktopNode(
                node_id=node.node_id,
                role="text",
                bbox=node.bbox,
                confidence=node.confidence,
                source=node.source,
                text=str(node.payload.get("text", "")),
                evidence_ref=node.node_id,
            )
            child_ids.append(node.node_id)
        nodes[root_id] = DesktopNode(
            node_id=root_id,
            role="window",
            bbox=NormalizedRect(0.0, 0.0, 1.0, 1.0),
            confidence=1.0,
            source="observation_graph",
            state=graph.screen_state() or "unknown",
            children=child_ids,
            evidence_ref=graph.graph_id,
        )
        return DesktopTree(
            tree_id=f"tree:{graph.graph_id}",
            root_id=root_id,
            screen_state=graph.screen_state() or "unknown",
            viewport=graph.viewport,
            nodes=nodes,
        )


def _role_from(role: str, text: str, icon_id: str) -> DesktopNodeRole:
    lowered = role.lower()
    if lowered in {"button", "list", "panel", "icon", "modal"}:
        return lowered  # type: ignore[return-value]
    if icon_id:
        return "icon"
    if text:
        return "text" if lowered not in {"btn", "clickable"} else "button"
    return "unknown"
