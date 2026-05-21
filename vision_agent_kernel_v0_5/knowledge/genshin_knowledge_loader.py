from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

import yaml


@dataclass(frozen=True, slots=True)
class ResourceInfo:
    resource_id: str
    name: str
    name_en: str
    type: str
    detection_class: str
    interaction: str
    respawn_hours: int
    regions: list[str]
    visual: str
    attack_count: int = 0
    subregion: str = ""
    element: str = ""


@dataclass(frozen=True, slots=True)
class MonsterInfo:
    monster_id: str
    name: str
    name_en: str
    class_id: str
    element: str
    hp_segments: int
    danger_signals: list[str]
    weaknesses: list[str]
    drops: list[str]
    weakpoints: list[str] | None = None
    shield_element: str = ""
    resin_cost: int = 0
    respawn_minutes: int = 0
    visual: str = ""


@dataclass(frozen=True, slots=True)
class RegionInfo:
    region_id: str
    name: str
    name_en: str
    color_palette: str
    theme: str
    visual_signature: str
    element_theme: str


@dataclass(frozen=True, slots=True)
class WaypointInfo:
    waypoint_id: str
    name: str
    position: list[float]
    region: str
    type: str


@dataclass(frozen=True, slots=True)
class EdgeInfo:
    from_id: str
    to_id: str
    cost: float
    method: str
    danger_level: str


def _build_resource(data: dict[str, Any]) -> ResourceInfo:
    return ResourceInfo(
        resource_id=str(data["resource_id"]),
        name=str(data["name"]),
        name_en=str(data["name_en"]),
        type=str(data.get("type", "")),
        detection_class=str(data.get("detection_class", "")),
        interaction=str(data.get("interaction", "")),
        respawn_hours=int(data.get("respawn_hours", 0)),
        regions=list(data.get("regions", [])),
        visual=str(data.get("visual", "")),
        attack_count=int(data.get("attack_count", 0)),
        subregion=str(data.get("subregion", "")),
        element=str(data.get("element", "")),
    )


def _build_monster(data: dict[str, Any]) -> MonsterInfo:
    weakpoints_raw = data.get("weakpoints")
    return MonsterInfo(
        monster_id=str(data["monster_id"]),
        name=str(data["name"]),
        name_en=str(data.get("name_en", data["monster_id"])),
        class_id=str(data.get("class_id", "")),
        element=str(data.get("element", "")),
        hp_segments=int(data.get("hp_segments", 1)),
        danger_signals=list(data.get("danger_signals", [])),
        weaknesses=list(data.get("weaknesses", [])),
        drops=list(data.get("drops", [])),
        weakpoints=list(weakpoints_raw) if weakpoints_raw else None,
        shield_element=str(data.get("shield_element", "")),
        resin_cost=int(data.get("resin_cost", 0)),
        respawn_minutes=int(data.get("respawn_minutes", 0)),
        visual=str(data.get("visual", "")),
    )


def _build_region(data: dict[str, Any]) -> RegionInfo:
    return RegionInfo(
        region_id=str(data["region_id"]),
        name=str(data["name"]),
        name_en=str(data["name_en"]),
        color_palette=str(data.get("color_palette", "")),
        theme=str(data.get("theme", "")),
        visual_signature=str(data.get("visual_signature", "")),
        element_theme=str(data.get("element_theme", "")),
    )


def _build_waypoint(data: dict[str, Any]) -> WaypointInfo:
    return WaypointInfo(
        waypoint_id=str(data["waypoint_id"]),
        name=str(data["name"]),
        position=[float(v) for v in data.get("position", [0.0, 0.0, 0.0])],
        region=str(data.get("region", "")),
        type=str(data.get("type", "")),
    )


def _build_edge(data: dict[str, Any]) -> EdgeInfo:
    return EdgeInfo(
        from_id=str(data["from_id"]),
        to_id=str(data["to_id"]),
        cost=float(data.get("cost", 0.0)),
        method=str(data.get("method", "")),
        danger_level=str(data.get("danger_level", "")),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^(\s*name_en:\s*)([^\"'\[\{].*:.*)$", r'\1"\2"', text, flags=re.MULTILINE)
    result: dict[str, Any] = yaml.safe_load(text) or {}
    return result


def _collect_resources(raw: dict[str, Any]) -> dict[str, ResourceInfo]:
    items: dict[str, ResourceInfo] = {}
    for _category, entries in raw.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and "resource_id" in entry:
                info = _build_resource(entry)
                items[info.resource_id] = info
    return items


class GenshinKnowledgeBase:
    _WAYPOINT_ALIASES: dict[str, str] = {
        "mondstadt_windrise": "mon_windrise",
        "sumeru_city": "sum_sumeru_city",
        "fontaine_court": "fon_court",
        "natlan_stadium": "nat_stadium",
    }

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self._dir = knowledge_dir or Path("knowledge")
        self._resources: dict[str, ResourceInfo] | None = None
        self._monsters: dict[str, MonsterInfo] | None = None
        self._regions: dict[str, RegionInfo] | None = None
        self._waypoints: dict[str, WaypointInfo] | None = None
        self._edges: list[EdgeInfo] | None = None

    def _load_resources(self) -> dict[str, ResourceInfo]:
        path = self._dir / "genshin_resources.yaml"
        raw = _load_yaml(path)
        return _collect_resources(raw)

    def _load_monsters(self) -> dict[str, MonsterInfo]:
        path = self._dir / "genshin_monsters.yaml"
        raw = _load_yaml(path)
        entries = raw.get("monsters", [])
        result: dict[str, MonsterInfo] = {}
        for e in entries:
            info = _build_monster(e)
            result[info.monster_id] = info
        return result

    def _load_regions(self) -> dict[str, RegionInfo]:
        path = self._dir / "genshin_world_graph.yaml"
        raw = _load_yaml(path)
        entries = raw.get("regions", [])
        return {_build_region(e).region_id: _build_region(e) for e in entries}

    def _load_waypoints(self) -> dict[str, WaypointInfo]:
        path = self._dir / "genshin_world_graph.yaml"
        raw = _load_yaml(path)
        entries = raw.get("waypoints", [])
        waypoints = {_build_waypoint(e).waypoint_id: _build_waypoint(e) for e in entries}
        for alias, canonical in self._WAYPOINT_ALIASES.items():
            if alias in waypoints or canonical not in waypoints:
                continue
            source = waypoints[canonical]
            waypoints[alias] = WaypointInfo(
                waypoint_id=alias,
                name=source.name,
                position=list(source.position),
                region=source.region,
                type=source.type,
            )
        return waypoints

    def _load_edges(self) -> list[EdgeInfo]:
        path = self._dir / "genshin_world_graph.yaml"
        raw = _load_yaml(path)
        entries = raw.get("edges", [])
        return [_build_edge(e) for e in entries]

    @property
    def resources(self) -> dict[str, ResourceInfo]:
        if self._resources is None:
            self._resources = self._load_resources()
        return self._resources

    @property
    def monsters(self) -> dict[str, MonsterInfo]:
        if self._monsters is None:
            self._monsters = self._load_monsters()
        return self._monsters

    @property
    def regions(self) -> dict[str, RegionInfo]:
        if self._regions is None:
            self._regions = self._load_regions()
        return self._regions

    @property
    def waypoints(self) -> dict[str, WaypointInfo]:
        if self._waypoints is None:
            self._waypoints = self._load_waypoints()
        return self._waypoints

    @property
    def edges(self) -> list[EdgeInfo]:
        if self._edges is None:
            self._edges = self._load_edges()
        return self._edges

    def get_resource(self, resource_id: str) -> ResourceInfo | None:
        return self.resources.get(resource_id)

    def get_monster(self, monster_id: str) -> MonsterInfo | None:
        return self.monsters.get(monster_id)

    def get_region(self, region_id: str) -> RegionInfo | None:
        return self.regions.get(region_id)

    def find_resources_by_region(self, region: str) -> list[ResourceInfo]:
        return [r for r in self.resources.values() if region in r.regions]

    def find_monsters_by_class(self, class_id: str) -> list[MonsterInfo]:
        return [m for m in self.monsters.values() if m.class_id == class_id]

    def get_weakness(self, monster_id: str) -> list[str]:
        monster = self.get_monster(monster_id)
        if monster is None:
            return []
        return list(monster.weaknesses)
