"""Tests for CodingAgent."""
from __future__ import annotations

from app_service.coding_agent import CodingAgent, GeneratedSkill


class _MockLLM:
    def __init__(self, code: str = "") -> None:
        self.code = code

    def generate(self, prompt: str) -> str:
        return self.code


class TestCodingAgent:
    def test_no_llm_returns_low_confidence(self) -> None:
        agent = CodingAgent(llm=None)
        skill = agent.generate_skill("open chest", skill_id="test_1")
        assert skill.confidence == 0.0
        assert not skill.validation.success

    def test_valid_code_generation(self) -> None:
        code = "def execute(context):\n    print('opening chest')\n    return True"
        agent = CodingAgent(llm=_MockLLM(code))
        skill = agent.generate_skill("open chest", skill_id="test_2")
        assert skill.validation.success
        assert skill.confidence > 0.5

    def test_invalid_code_generation(self) -> None:
        code = "x = 1 / 0"
        agent = CodingAgent(llm=_MockLLM(code))
        skill = agent.generate_skill("broken skill", skill_id="test_3")
        assert not skill.validation.success
        assert skill.confidence < 0.5

    def test_markdown_code_extraction(self) -> None:
        code = "Some text\n```python\ndef execute(ctx):\n    return True\n```\nMore text"
        assert "def execute" in CodingAgent._extract_code(code)

    def test_plain_code_extraction(self) -> None:
        code = "def execute(ctx):\n    return True"
        assert CodingAgent._extract_code(code) == code

    def test_auto_skill_id(self) -> None:
        agent = CodingAgent(llm=None)
        skill = agent.generate_skill("open chest")
        assert len(skill.skill_id) == 12

    def test_llm_error_handling(self) -> None:
        class FailingLLM:
            def generate(self, prompt: str) -> str:
                raise RuntimeError("API unavailable")

        agent = CodingAgent(llm=FailingLLM())
        skill = agent.generate_skill("test", skill_id="err_1")
        assert skill.confidence == 0.0
        assert "API unavailable" in skill.validation.error
