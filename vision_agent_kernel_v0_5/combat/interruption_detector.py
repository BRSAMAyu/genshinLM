from __future__ import annotations


class InterruptionDetector:
    def detect(self, signals: dict[str, float]) -> dict[str, object]:
        hitstun = signals.get("hitstun", 0.0) > 0.5 or signals.get("knocked_back", 0.0) > 0.5
        return {"interrupted": hitstun, "reason": "hitstun_or_knockback" if hitstun else "none"}

