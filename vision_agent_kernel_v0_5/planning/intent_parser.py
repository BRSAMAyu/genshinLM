from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedIntent:
    goal_type: str
    resource_id: str
    target_count: int
    preference: str


class IntentParser:
    def parse(self, text: str) -> ParsedIntent:
        lowered = text.lower()
        resource_id = "material_x" if "material x" in lowered or "材料" in text else lowered.strip().replace(" ", "_")
        count = 10 if "10" in lowered else 1
        preference = "combat_first" if "monster" in lowered or "打怪" in text or "combat" in lowered else "balanced"
        return ParsedIntent("material_collection", resource_id, count, preference)

