"""Offline tests for the MiniMax M3 unified multimodal provider.

No network, no API key: a fake transport returns canned responses and lets us
assert the request payload (model id, multimodal message format, base64 image).
"""
from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from llm.minimax_provider import MiniMaxProvider
from llm.vision_provider import ImageInput


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


def make_transport(body_text: str) -> tuple[Any, list[urllib_request_type]]:
    """Return (transport, captured_requests). Each captured request exposes .data."""
    captured: list[Any] = []

    def transport(request: Any, timeout: float) -> _FakeResponse:
        captured.append(request)
        return _FakeResponse(body_text.encode("utf-8"))

    return transport, captured


# urllib.request.Request — just need .data attribute; alias for typing.
urllib_request_type = Any


def _api_body(content: str, usage: dict[str, Any] | None = None) -> str:
    return json.dumps({
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"total_tokens": 7},
    })


def _set_key(monkeypatch) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")


def _last_payload(captured: list[Any]) -> dict[str, Any]:
    return json.loads(captured[-1].data.decode("utf-8"))


# --- planner (text) --------------------------------------------------------


def test_plan_uses_m3_and_parses_chain(monkeypatch) -> None:
    _set_key(monkeypatch)
    content = json.dumps({"skill_chain": ["nav", "combat"], "task_id": "t1", "goal": "x"})
    transport, captured = make_transport(_api_body(content))
    provider = MiniMaxProvider(transport=transport)

    proposal = provider.plan("clear camp", [{"skill_id": "nav"}], "companion")

    assert proposal.provider == "minimax"
    assert proposal.skill_chain == ["nav", "combat"]
    payload = _last_payload(captured)
    assert payload["model"] == "MiniMax-M3"
    assert payload["messages"][0]["role"] == "system"
    # text-only plan → plain-string user content, no image blocks
    assert isinstance(payload["messages"][1]["content"], str)


def test_status_reports_m3_and_image_support(monkeypatch) -> None:
    _set_key(monkeypatch)
    provider = MiniMaxProvider()
    st = provider.status()
    assert st.model == "MiniMax-M3"
    assert st.supports_images is True
    assert st.ok is True


def test_no_key_raises_and_falls_back_upstream(monkeypatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    provider = MiniMaxProvider()
    # direct call surfaces ProviderUnavailable (Planner wraps it into mock fallback)
    from llm.provider_base import ProviderUnavailable
    with pytest.raises(ProviderUnavailable):
        provider.plan("x", [], "p")


# --- vision (multimodal, same M3) ------------------------------------------


def _png() -> bytes:
    return bytes(range(0, 250, 3)) * 2  # arbitrary non-empty bytes


def test_describe_image_sends_multimodal_blocks(monkeypatch) -> None:
    _set_key(monkeypatch)
    transport, captured = make_transport(_api_body("a knight near a cliff"))
    provider = MiniMaxProvider(transport=transport)

    result = provider.describe_image(ImageInput(data=_png()), "describe the scene")

    assert result.text == "a knight near a cliff"
    assert result.model == "MiniMax-M3"
    content = _last_payload(captured)["messages"][1]["content"]
    # multimodal → list of {type:text} + {type:image_url}
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "describe the scene"}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    # round-trips back to the original bytes
    encoded = url.split("base64,", 1)[1]
    assert base64.b64decode(encoded) == _png()


def test_classify_screen_parses_state_and_confidence(monkeypatch) -> None:
    _set_key(monkeypatch)
    content = json.dumps({"screen_state": "combat", "confidence": 0.9})
    transport, captured = make_transport(_api_body(content))
    provider = MiniMaxProvider(transport=transport)

    result = provider.classify_screen(ImageInput(data=_png()), ["combat", "overworld", "menu"])

    assert result.screen_state == "combat"
    assert result.confidence == pytest.approx(0.9)
    # image was attached
    payload = _last_payload(captured)
    assert isinstance(payload["messages"][1]["content"], list)


def test_ground_ui_returns_candidates(monkeypatch) -> None:
    _set_key(monkeypatch)
    content = json.dumps({"candidates": [
        {"label": "Teleport", "bbox_norm": [0.1, 0.2, 0.05, 0.05], "confidence": 0.8, "reason": "map pin"},
    ]})
    transport, _captured = make_transport(_api_body(content))
    provider = MiniMaxProvider(transport=transport)

    result = provider.ground_ui(ImageInput(data=_png()), "teleport button")

    assert result.query == "teleport button"
    assert result.candidates[0]["label"] == "Teleport"
    assert result.candidates[0]["bbox_norm"] == [0.1, 0.2, 0.05, 0.05]


def test_explain_failure_with_image_attaches_screenshot(monkeypatch) -> None:
    _set_key(monkeypatch)
    content = json.dumps({"user_friendly_summary": "stuck on a wall", "technical_summary": "no flow"})
    transport, captured = make_transport(_api_body(content))
    provider = MiniMaxProvider(transport=transport)

    out = provider.explain_failure_with_image({"failure_code": "stuck"}, ImageInput(data=_png()))

    assert out["user_friendly_summary"] == "stuck on a wall"
    assert isinstance(_last_payload(captured)["messages"][1]["content"], list)
