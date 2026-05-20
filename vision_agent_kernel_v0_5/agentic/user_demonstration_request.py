from __future__ import annotations


class UserDemonstrationRequest:
    def build(self, missing_skill: str, reason: str) -> dict[str, object]:
        return {
            "required": True,
            "missing_skill": missing_skill,
            "reason": reason,
            "message": "Please demonstrate this step in the authorized test window; the recorder will convert it into a SkillDraft.",
        }
