from __future__ import annotations

import time

from core.types import SkillResult


class DummySkill:
    """A simple skill that returns a successful SkillResult."""

    name: str = "demo_arpg_dummy"

    def run(self) -> SkillResult:
        now = time.perf_counter()
        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"demo": True},
        )
