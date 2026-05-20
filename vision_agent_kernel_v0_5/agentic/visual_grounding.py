from __future__ import annotations

from dataclasses import dataclass


DESTRUCTIVE_TERMS = {"分解", "删除", "解散", "消耗", "确认删除", "destroy", "delete", "discard", "consume", "dismantle"}


@dataclass(frozen=True, slots=True)
class GroundedElement:
    label: str
    bbox: tuple[int, int, int, int]
    confidence: float
    destructive: bool = False


class VisualGrounding:
    def ground(self, ocr_items: list[dict]) -> list[GroundedElement]:
        elements = []
        for item in ocr_items:
            label = str(item.get("text", ""))
            destructive = any(term in label.lower() for term in DESTRUCTIVE_TERMS)
            bbox = tuple(item.get("bbox", (0, 0, 0, 0)))
            elements.append(GroundedElement(label, bbox, float(item.get("confidence", 0.5)), destructive))
        return elements

