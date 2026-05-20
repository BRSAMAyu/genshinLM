from __future__ import annotations

from learning.failure_signature import FailureSignature


class ProfilePatchSuggester:
    def suggest(self, failure: FailureSignature) -> dict[str, object]:
        if failure.observation.get("visual_pollution_high"):
            return {"requires_user_confirmation": True, "patch": "narrow_roi_or_add_privacy_mask"}
        return {"requires_user_confirmation": True, "patch": "no_profile_patch"}

