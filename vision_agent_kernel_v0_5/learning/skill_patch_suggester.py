from __future__ import annotations

from learning.failure_signature import FailureSignature


class SkillPatchSuggester:
    def suggest(self, failure: FailureSignature) -> dict[str, object]:
        return {
            "requires_user_confirmation": True,
            "skill_id": failure.skill_id,
            "patches": failure.suggested_patch or ["add_timeout_recovery"],
        }

