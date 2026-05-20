from __future__ import annotations


class AvatarController:
    def expression_for_state(self, overlay_state: str) -> str:
        return {
            "观察中": "neutral",
            "思考中": "thinking",
            "执行中": "focused",
            "遇到问题": "concerned",
            "暂停": "alert",
            "完成": "smile",
        }.get(overlay_state, "neutral")
