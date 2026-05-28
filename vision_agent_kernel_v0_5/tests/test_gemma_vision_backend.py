from __future__ import annotations

from llm.gemma_vision_provider import TransformersGemmaVisionBackend, _parse_fact_bundle
from llm.vision_output_guard import VisionOutputGuard


def test_gemma_fact_parser_accepts_structured_facts_and_rejects_action_text() -> None:
    text = """
    {
      "screen_state": "dialog",
      "uncertainty": 0.2,
      "facts": [
        {
          "fact_id": "f1",
          "fact_type": "ui_grounding",
          "value": "confirm option",
          "confidence": 0.9,
          "evidence_ref": "frame_1",
          "bbox_norm": [0.1, 0.2, 0.3, 0.1]
        },
        {
          "fact_id": "bad",
          "fact_type": "ui_grounding",
          "value": "click at (123,456)",
          "confidence": 0.99,
          "bbox_norm": [0.1, 0.2, 0.3, 0.1]
        }
      ]
    }
    """
    facts, screen_state, uncertainty = _parse_fact_bundle(text, VisionOutputGuard())
    assert screen_state == "dialog"
    assert uncertainty == 0.2
    assert [f.fact_id for f in facts] == ["f1"]


def test_transformers_backend_optional_status_never_raises() -> None:
    status = TransformersGemmaVisionBackend(model_id="gemma4_vision").status()
    assert status.backend == "gemma_transformers"
    assert status.model_id == "gemma4_vision"
    assert isinstance(status.ok, bool)
