from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class HSRCharacterInfo:
    character_id: str
    name: str
    name_en: str
    rarity: int
    path: str
    element: str
    skill_sp_cost: int = 1
    ultimate_sp_cost: int = 0
    basic_sp_gain: int = 1
    skill_name: str = ""
    ultimate_name: str = ""


@dataclass(frozen=True, slots=True)
class HSREnemyInfo:
    enemy_id: str
    name: str
    name_en: str
    class_id: str
    element: str
    weaknesses: tuple[str, ...] = ()
    toughness: int = 30
    danger_signals: tuple[str, ...] = ()
    drops: tuple[str, ...] = ()


class HSRKnowledgeBase:
    """Lazy-loaded knowledge base for Honkai: Star Rail."""

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self._dir = knowledge_dir or Path(__file__).resolve().parent
        self._characters: dict[str, HSRCharacterInfo] | None = None
        self._enemies: dict[str, HSREnemyInfo] | None = None

    @property
    def characters(self) -> dict[str, HSRCharacterInfo]:
        if self._characters is None:
            self._characters = self._load_characters()
        return self._characters

    @property
    def enemies(self) -> dict[str, HSREnemyInfo]:
        if self._enemies is None:
            self._enemies = self._load_enemies()
        return self._enemies

    def get_character(self, character_id: str) -> HSRCharacterInfo | None:
        return self.characters.get(character_id)

    def get_enemy(self, enemy_id: str) -> HSREnemyInfo | None:
        return self.enemies.get(enemy_id)

    def find_characters_by_path(self, path: str) -> list[HSRCharacterInfo]:
        return [c for c in self.characters.values() if c.path == path]

    def find_characters_by_element(self, element: str) -> list[HSRCharacterInfo]:
        return [c for c in self.characters.values() if c.element == element]

    def get_weaknesses(self, enemy_id: str) -> list[str]:
        enemy = self.get_enemy(enemy_id)
        if enemy is None:
            return []
        return list(enemy.weaknesses)

    def _load_characters(self) -> dict[str, HSRCharacterInfo]:
        path = self._dir / "hsr_characters.yaml"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        chars: dict[str, HSRCharacterInfo] = {}
        for entry in data.get("characters", []):
            info = HSRCharacterInfo(
                character_id=entry["character_id"],
                name=entry["name"],
                name_en=entry["name_en"],
                rarity=int(entry["rarity"]),
                path=entry["path"],
                element=entry["element"],
                skill_sp_cost=int(entry.get("skill_sp_cost", 1)),
                ultimate_sp_cost=int(entry.get("ultimate_sp_cost", 0)),
                basic_sp_gain=int(entry.get("basic_sp_gain", 1)),
                skill_name=entry.get("skill_name", ""),
                ultimate_name=entry.get("ultimate_name", ""),
            )
            chars[info.character_id] = info
        return chars

    def _load_enemies(self) -> dict[str, HSREnemyInfo]:
        path = self._dir / "hsr_enemies.yaml"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        enemies: dict[str, HSREnemyInfo] = {}
        for entry in data.get("enemies", []):
            info = HSREnemyInfo(
                enemy_id=entry["enemy_id"],
                name=entry["name"],
                name_en=entry["name_en"],
                class_id=entry.get("class_id", "enemy_normal"),
                element=entry.get("element", "none"),
                weaknesses=tuple(entry.get("weaknesses", [])),
                toughness=int(entry.get("toughness", 30)),
                danger_signals=tuple(entry.get("danger_signals", [])),
                drops=tuple(entry.get("drops", [])),
            )
            enemies[info.enemy_id] = info
        return enemies
