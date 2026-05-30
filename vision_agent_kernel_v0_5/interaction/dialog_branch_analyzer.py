from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Keywords that indicate "accept" actions in dialog choices
_ACCEPT_KEYWORDS = {"接受", "同意", "好的", "没问题", "当然", "是", "愿意", "我来", "一起"}
_REJECT_KEYWORDS = {"拒绝", "不了", "不用", "算了", "取消"}


class DialogBranchAnalyzer:
    """Analyze dialog choices and recommend which to select."""

    def analyze_choices(self, choice_texts: list[str], context: dict | None = None) -> int:
        """Return recommended choice index (0-based). Default: first choice.

        For Genshin main storyline, dialog choices don't affect story outcome,
        so default to first choice unless we detect specific keywords.
        """
        if not choice_texts:
            return 0

        # Check for accept/reject keywords
        for i, text in enumerate(choice_texts):
            text_lower = text.lower().strip()
            for kw in _ACCEPT_KEYWORDS:
                if kw in text_lower:
                    return i

        # Default: first option (safest for main storyline)
        return 0
