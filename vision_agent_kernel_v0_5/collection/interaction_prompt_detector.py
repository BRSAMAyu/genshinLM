from __future__ import annotations


class InteractionPromptDetector:
    def detect(self, ocr_text: str = "", visual_hint: bool = False) -> dict[str, object]:
        text = ocr_text.lower()
        visible = visual_hint or any(word in text for word in ["interact", "collect", "采集", "拾取"])
        return {"visible": visible, "confidence": 0.85 if visible else 0.2}

