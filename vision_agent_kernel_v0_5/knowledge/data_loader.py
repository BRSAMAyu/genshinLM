from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge.knowledge_schema import (
    KnowledgePack,
    edge_from_dict,
    resource_from_dict,
    route_from_dict,
    source_node_from_dict,
    waypoint_from_dict,
)


def load_knowledge_pack(path: Path | None = None) -> KnowledgePack:
    if path is None or not path.exists():
        return default_knowledge_pack()
    data = _load_mapping(path)
    return KnowledgePack(
        resources=[resource_from_dict(item) for item in data.get("resources", [])],
        sources=[source_node_from_dict(item) for item in data.get("sources", [])],
        waypoints=[waypoint_from_dict(item) for item in data.get("waypoints", [])],
        edges=[edge_from_dict(item) for item in data.get("edges", [])],
        routes=[route_from_dict(item) for item in data.get("routes", [])],
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load YAML knowledge packs") from exc
        return dict(yaml.safe_load(text) or {})
    return dict(json.loads(text))


def default_knowledge_pack() -> KnowledgePack:
    data = {
        "resources": [
            {
                "resource_id": "material_x",
                "name": "Demo Material X",
                "type": "monster_drop",
                "sources": [{"source_id": "monster_a_group_001", "source_type": "monster_group", "expected_drop": True}],
            }
        ],
        "sources": [
            {
                "source_id": "monster_a_group_001",
                "type": "monster_group",
                "region": "demo_region_a",
                "position": [100.0, 0.0, 40.0],
                "entry_skill": "enter_region_a_v1",
                "acquire_skill": "acquire_monster_a_v1",
                "execution_skill": "safe_combat_playbook_v1",
                "verification": "monster_defeated_or_reward_seen",
                "risk": "medium",
            }
        ],
        "waypoints": [
            {"waypoint_id": "safe_anchor", "region": "demo_region_a", "position": [0.0, 0.0, 0.0]},
            {"waypoint_id": "river_crossing", "region": "demo_region_a", "position": [40.0, 0.0, 20.0]},
            {"waypoint_id": "monster_camp", "region": "demo_region_a", "position": [100.0, 0.0, 40.0]},
        ],
        "edges": [
            {"from": "safe_anchor", "to": "river_crossing", "cost": 25.0},
            {"from": "river_crossing", "to": "monster_camp", "cost": 35.0},
        ],
        "routes": [
            {
                "route_id": "region_a_route_01",
                "entry_point": "safe_anchor",
                "targets": ["monster_a_group_001"],
                "estimated_time_sec": 180,
                "required_profiles": ["default_1920x1080"],
            }
        ],
    }
    return KnowledgePack(
        resources=[resource_from_dict(item) for item in data["resources"]],
        sources=[source_node_from_dict(item) for item in data["sources"]],
        waypoints=[waypoint_from_dict(item) for item in data["waypoints"]],
        edges=[edge_from_dict(item) for item in data["edges"]],
        routes=[route_from_dict(item) for item in data["routes"]],
    )

