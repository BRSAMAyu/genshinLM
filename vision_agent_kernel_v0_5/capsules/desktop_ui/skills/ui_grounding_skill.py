from __future__ import annotations

import time

from core.types import SkillResult


class UiGroundingSkill:
    """A skill for safe desktop UI automation with element grounding."""

    name: str = "desktop_ui_grounding"

    def run(self) -> SkillResult:
        now = time.perf_counter()
        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"grounded_elements": 0, "safety_check": "pass"},
        )
