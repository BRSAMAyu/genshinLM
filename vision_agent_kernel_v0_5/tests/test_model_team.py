"""Offline tests for the dual-model coordinator (GLM-5.2 reason + MiniMax M3 see).

Separate fake transports per provider let us assert WHO handled WHAT (routing) and
that the perceive → reason pipelines chain the two models correctly.
"""
from __future__ import annotations

import json
from typing import Any

from llm.glm_provider import GLMProvider
from llm.minimax_provider import MiniMaxProvider
from llm.model_team import DualModelCoordinator
from llm.vision_provider import ImageInput


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *a: Any) -> bool:
        return False


class FakeTransport:
    """Returns canned content; records every request's payload."""

    def __init__(self, content_fn) -> None:
        # content_fn(payload) -> response content string
        self._content_fn = content_fn
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float) -> _FakeResp:
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append(payload)
        content = self._content_fn(payload)
        body = json.dumps({"choices": [{"message": {"content": content}}], "usage": {"t": 1}})
        return _FakeResp(body.encode("utf-8"))

    @property
    def last(self) -> dict[str, Any]:
        return self.requests[-1]

    def models_used(self) -> list[str]:
        return [r["model"] for r in self.requests]


def _png() -> bytes:
    return bytes(range(0, 250, 3)) * 2


def _set_keys(monkeypatch) -> None:
    monkeypatch.setenv("GLM_API_KEY", "k-glm")
    monkeypatch.setenv("MINIMAX_API_KEY", "k-mm")


# --- routing ---------------------------------------------------------------


def test_vision_calls_route_to_minimax_m3(monkeypatch) -> None:
    _set_keys(monkeypatch)
    glm_t = FakeTransport(lambda p: "{}")
    mm_t = FakeTransport(lambda p: json.dumps({"screen_state": "combat", "confidence": 0.9}))
    team = DualModelCoordinator(reasoner=GLMProvider(transport=glm_t), vision=MiniMaxProvider(transport=mm_t))

    team.classify_screen(ImageInput(data=_png()), ["combat", "overworld"])

    assert mm_t.requests and mm_t.last["model"] == "MiniMax-M3"
    assert glm_t.requests == []  # reasoning model not touched for pure vision


def test_reasoning_calls_route_to_glm52(monkeypatch) -> None:
    _set_keys(monkeypatch)
    glm_t = FakeTransport(lambda p: "because the target moved off-screen")
    mm_t = FakeTransport(lambda p: "{}")
    team = DualModelCoordinator(reasoner=GLMProvider(transport=glm_t), vision=MiniMaxProvider(transport=mm_t))

    out, _usage = team.reason("be concise", "why did aiming fail?")

    assert "target moved" in out
    assert glm_t.last["model"] == "glm-5.2"
    assert mm_t.requests == []


# --- perceive → reason pipelines ------------------------------------------


def test_perceive_uses_m3_then_plan_augments_goal_for_glm(monkeypatch) -> None:
    _set_keys(monkeypatch)
    glm_t = FakeTransport(lambda p: json.dumps({"skill_chain": ["combat"], "task_id": "t1", "goal": "x"}))
    mm_t = FakeTransport(lambda p: (
        json.dumps({"screen_state": "combat", "confidence": 0.95})
        if "screen_state" in p["messages"][0]["content"]
        else "a hilichurl camp with three enemies, boss enraged"
    ))
    team = DualModelCoordinator(reasoner=GLMProvider(transport=glm_t), vision=MiniMaxProvider(transport=mm_t))

    proposal = team.perceive_and_plan(ImageInput(data=_png()), "clear the camp", [{"skill_id": "combat"}])

    assert proposal.skill_chain == ["combat"]
    # M3 was used for vision (classify + describe)
    assert any(r["model"] == "MiniMax-M3" for r in mm_t.requests)
    assert any("image_url" in str(r["messages"][1]["content"]) for r in mm_t.requests)
    # GLM-5.2 received the M3-derived screen_state inside the augmented goal
    assert glm_t.last["model"] == "glm-5.2"
    glm_user = glm_t.last["messages"][1]["content"]
    assert "combat" in glm_user and "perceived_situation" in glm_user


def test_diagnose_failure_chains_m3_evidence_then_glm_attribution(monkeypatch) -> None:
    _set_keys(monkeypatch)
    glm_t = FakeTransport(lambda p: json.dumps({
        "user_friendly_summary": "ran into a wall",
        "technical_summary": "no forward progress; pose stuck",
        "suggested_next_steps": ["back up", "re-aim"],
    }))
    mm_t = FakeTransport(lambda p: (
        json.dumps({"screen_state": "overworld", "confidence": 0.8})
        if "screen_state" in p["messages"][0]["content"]
        else "player facing a cliff wall, no path ahead"
    ))
    team = DualModelCoordinator(reasoner=GLMProvider(transport=glm_t), vision=MiniMaxProvider(transport=mm_t))

    diag = team.diagnose_failure(ImageInput(data=_png()), {"failure_code": "stuck"})

    assert diag.user_friendly_summary == "ran into a wall"
    assert diag.suggested_next_steps == ["back up", "re-aim"]
    assert diag.reasoning_provider == "glm" and diag.vision_provider == "minimax"
    # GLM saw the M3-produced visual evidence in its prompt
    assert "cliff wall" in glm_t.last["messages"][1]["content"] or "overworld" in glm_t.last["messages"][1]["content"]


def test_plan_combat_strategy_routes_scene_to_m3_decision_to_glm(monkeypatch) -> None:
    _set_keys(monkeypatch)
    glm_t = FakeTransport(lambda p: json.dumps({
        "active_character_to_switch": "xiangling",
        "rotation": [{"step": 1, "action": "skill", "reason": "apply pyro"}],
        "reaction_target_element": "hydro",
        "burst_when": "enemy < 30% hp",
        "risks": ["enemy shield"],
    }))
    mm_t = FakeTransport(lambda p: (
        json.dumps({"screen_state": "combat", "confidence": 0.9})
        if "screen_state" in p["messages"][0]["content"]
        else "three hilichurls, one with hydro shield, player HP full"
    ))
    team = DualModelCoordinator(reasoner=GLMProvider(transport=glm_t), vision=MiniMaxProvider(transport=mm_t))

    strat = team.plan_combat_strategy(ImageInput(data=_png()), "defeat the camp")

    assert strat["active_character_to_switch"] == "xiangling"
    assert strat["reaction_target_element"] == "hydro"
    # combat scene went to M3 (multimodal), strategy came from GLM-5.2
    assert any("image_url" in str(r["messages"][1]["content"]) for r in mm_t.requests)
    assert glm_t.last["model"] == "glm-5.2"
    assert "hilichurl" in glm_t.last["messages"][1]["content"]
