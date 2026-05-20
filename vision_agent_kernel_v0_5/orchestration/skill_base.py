from __future__ import annotations

from typing import Protocol

from core.types import SkillResult


class Skill(Protocol):
    name: str

    def run(self) -> SkillResult: ...
