from __future__ import annotations

from dataclasses import asdict
from typing import Any

from knowledge.resource_db import ResourceDB


class SourceResolver:
    def __init__(self, db: ResourceDB | None = None) -> None:
        self._db = db or ResourceDB()

    def resolve(self, goal: str) -> dict[str, Any]:
        resource = self._db.resolve_resource(goal) or self._db.resolve_resource(_extract_resource_id(goal))
        if resource is None:
            return {"ok": False, "resource": None, "sources": [], "message": "Resource is unknown; ask user to add knowledge or record a skill."}
        sources = self._db.list_sources(resource)
        return {"ok": True, "resource": asdict(resource), "sources": [asdict(item) for item in sources], "message": "resolved"}


def _extract_resource_id(goal: str) -> str:
    lowered = goal.lower()
    if "material x" in lowered or "材料 x" in lowered or "材料x" in lowered:
        return "material_x"
    return lowered.strip().replace(" ", "_")

