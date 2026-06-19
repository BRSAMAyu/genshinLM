"""CodingAgent: LLM-powered code generation and validation.

Generates skill code from natural language descriptions,
validates it through CodeSandboxExecutor, and returns
ready-to-use Python functions.

Phase 1 roadmap: auto-generate skills from task descriptions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app_service.code_sandbox_executor import CodeSandboxExecutor, SandboxResult

log = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Protocol for LLM-based code generation."""

    def generate(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GeneratedSkill:
    skill_id: str
    code: str
    description: str
    validation: SandboxResult
    confidence: float


_CODEGEN_PROMPT_TEMPLATE = """Generate a Python function for the following game skill task.
The function should be named 'execute' and accept a single dict parameter 'context'.
It should return a bool indicating success.

Rules:
- Only use standard library modules (math, random, json, time, etc.)
- No file I/O or network access
- Keep it under 50 lines
- Print progress messages using print()

Task: {task_description}

Game: {game_id}
Category: {category}

Reply with ONLY the Python code, no explanation."""


class CodingAgent:
    """Generate and validate skill code from task descriptions."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm
        self._sandbox = CodeSandboxExecutor()

    def generate_skill(
        self,
        task_description: str,
        game_id: str = "genshin",
        category: str = "general",
        skill_id: str = "",
    ) -> GeneratedSkill:
        """Generate a skill from a task description.

        Pipeline: LLM generates code → Sandbox validates → return result.
        """
        if not skill_id:
            import hashlib
            skill_id = hashlib.md5(task_description.encode()).hexdigest()[:12]

        if self._llm is None:
            return GeneratedSkill(
                skill_id=skill_id,
                code="# No LLM provider configured\n",
                description=task_description,
                validation=SandboxResult(
                    success=False,
                    output="",
                    error="no_llm_provider",
                    execution_time_ms=0.0,
                ),
                confidence=0.0,
            )

        # Step 1: Generate code
        prompt = _CODEGEN_PROMPT_TEMPLATE.format(
            task_description=task_description,
            game_id=game_id,
            category=category,
        )
        try:
            code = self._llm.generate(prompt)
        except Exception as exc:
            return GeneratedSkill(
                skill_id=skill_id,
                code="",
                description=task_description,
                validation=SandboxResult(
                    success=False, output="", error=str(exc), execution_time_ms=0.0,
                ),
                confidence=0.0,
            )

        # Step 2: Clean up code (extract from markdown if present)
        code = self._extract_code(code)

        # Step 3: Validate in sandbox
        validation = self._sandbox.execute(code)

        confidence = 0.8 if validation.success else 0.2

        return GeneratedSkill(
            skill_id=skill_id,
            code=code,
            description=task_description,
            validation=validation,
            confidence=confidence,
        )

    @staticmethod
    def _extract_code(response: str) -> str:
        """Extract Python code from LLM response, handling markdown blocks."""
        if "```python" in response:
            parts = response.split("```python")
            if len(parts) > 1:
                code = parts[1].split("```")[0]
                return code.strip()
        if "```" in response:
            parts = response.split("```")
            if len(parts) > 1:
                code = parts[1].split("```")[0]
                return code.strip()
        return response.strip()
