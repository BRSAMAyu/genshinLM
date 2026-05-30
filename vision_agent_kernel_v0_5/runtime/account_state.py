"""Account state data model with JSON serialization/deserialization.

Implements the account state schema from GENSHIN_SESSION_PERSISTENCE_MODEL.md:
- Static account info (uid, server, AR, WL, characters, weapons, artifacts)
- Dynamic session state (location, quest, resources, daily/weekly completion)
- Atomic write-rename for safe persistence
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CharacterInfo:
    character_id: str
    constellation: int = 0
    level: int = 1
    ascension_phase: int = 0
    friendship_level: int = 1
    equipped_weapon_id: str = ""
    talents: tuple[int, int, int] = (1, 1, 1)  # normal, skill, burst

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "constellation": self.constellation,
            "level": self.level,
            "ascension_phase": self.ascension_phase,
            "friendship_level": self.friendship_level,
            "equipped_weapon_id": self.equipped_weapon_id,
            "talents": {"normal_attack": self.talents[0], "elemental_skill": self.talents[1], "elemental_burst": self.talents[2]},
        }


@dataclass(frozen=True, slots=True)
class WeaponInfo:
    weapon_id: str
    level: int = 1
    ascension_phase: int = 0
    refinement_rank: int = 1
    equipped_to_character: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_id": self.weapon_id,
            "level": self.level,
            "ascension_phase": self.ascension_phase,
            "refinement_rank": self.refinement_rank,
            "equipped_to_character": self.equipped_to_character,
        }


@dataclass(frozen=True, slots=True)
class ResourceState:
    original_resin: int = 160
    resin_updated_at: float = 0.0
    condensed_resin: int = 0
    fragile_resin: int = 0
    mora: int = 0
    primogems: int = 0
    stardust: int = 0
    starglitter: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_resin": self.original_resin,
            "resin_updated_at": self.resin_updated_at,
            "condensed_resin": self.condensed_resin,
            "fragile_resin": self.fragile_resin,
            "mora": self.mora,
            "primogems": self.primogems,
            "stardust": self.stardust,
            "starglitter": self.starglitter,
        }


@dataclass(frozen=True, slots=True)
class QuestProgress:
    quest_id: str
    current_step_index: int = 0
    current_step_objective: str = ""
    status: str = "not_started"  # not_started, in_progress, completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "current_step_index": self.current_step_index,
            "current_step_objective": self.current_step_objective,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class LocationState:
    region: str = ""
    subregion: str = ""
    waypoint_near: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "subregion": self.subregion,
            "waypoint_near": self.waypoint_near,
        }


@dataclass(frozen=True, slots=True)
class DailyCompletion:
    date: str = ""  # ISO date
    commissions_completed: int = 0
    commission_rewards_claimed: bool = False
    ley_lines_blue: int = 0
    ley_lines_gold: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "commissions_completed": self.commissions_completed,
            "commission_rewards_claimed": self.commission_rewards_claimed,
            "ley_lines_blue": self.ley_lines_blue,
            "ley_lines_gold": self.ley_lines_gold,
        }


@dataclass(frozen=True, slots=True)
class TeamSlot:
    character_id: str
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"character_id": self.character_id, "role": self.role}


@dataclass(frozen=True, slots=True)
class WeeklyCompletion:
    week_start: str = ""
    trounce_discounts_used: int = 0
    trounce_discounts_remaining: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start,
            "trounce_discounts_used": self.trounce_discounts_used,
            "trounce_discounts_remaining": self.trounce_discounts_remaining,
        }


# ---------------------------------------------------------------------------
# Full account state
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AccountState:
    """Complete account state with JSON persistence.

    Usage::

        state = AccountState(uid="123456789", store_dir=Path("accounts/123456789"))
        state.ar = 35
        state.save()
    """

    uid: str = ""
    server: str = ""
    ar: int = 0
    world_level: int = 0
    characters: list[CharacterInfo] = field(default_factory=list)
    weapons: list[WeaponInfo] = field(default_factory=list)
    unlocked_regions: list[str] = field(default_factory=list)
    unlocked_waypoints: list[str] = field(default_factory=list)
    activated_statues: list[str] = field(default_factory=list)
    location: LocationState = field(default_factory=LocationState)
    active_quest: QuestProgress = field(default_factory=lambda: QuestProgress(quest_id=""))
    resources: ResourceState = field(default_factory=ResourceState)
    daily: DailyCompletion = field(default_factory=DailyCompletion)
    weekly: WeeklyCompletion = field(default_factory=WeeklyCompletion)
    active_team: tuple[TeamSlot, ...] = ()
    archon_quest_progress: dict[str, Any] = field(default_factory=dict)
    store_dir: Path = field(default_factory=lambda: Path("accounts/default"))
    last_saved_at: float = 0.0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Atomic write-rename save."""
        self.store_dir.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        data["last_saved_at"] = time.perf_counter()
        target = self.store_dir / "account_state.json"
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.store_dir), prefix=".account_state_", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(target))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self.last_saved_at = time.perf_counter()
        log.info("[AccountState] saved to %s", target)

    @classmethod
    def load(cls, store_dir: Path) -> AccountState:
        """Load account state from disk."""
        path = store_dir / "account_state.json"
        if not path.exists():
            state = cls(store_dir=store_dir)
            log.info("[AccountState] no existing state at %s, using defaults", path)
            return state
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, store_dir=store_dir)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "server": self.server,
            "ar": self.ar,
            "world_level": self.world_level,
            "characters": [c.to_dict() for c in self.characters],
            "weapons": [w.to_dict() for w in self.weapons],
            "unlocked_regions": list(self.unlocked_regions),
            "unlocked_waypoints": list(self.unlocked_waypoints),
            "activated_statues": list(self.activated_statues),
            "location": self.location.to_dict(),
            "active_quest": self.active_quest.to_dict(),
            "resources": self.resources.to_dict(),
            "daily": self.daily.to_dict(),
            "weekly": self.weekly.to_dict(),
            "active_team": [s.to_dict() for s in self.active_team],
            "archon_quest_progress": dict(self.archon_quest_progress),
            "last_saved_at": self.last_saved_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], store_dir: Path | None = None) -> AccountState:
        characters = [
            CharacterInfo(
                character_id=c["character_id"],
                constellation=c.get("constellation", 0),
                level=c.get("level", 1),
                ascension_phase=c.get("ascension_phase", 0),
                friendship_level=c.get("friendship_level", 1),
                equipped_weapon_id=c.get("equipped_weapon_id", ""),
                talents=_parse_talents(c.get("talents", {})),
            )
            for c in data.get("characters", [])
        ]
        weapons = [
            WeaponInfo(
                weapon_id=w["weapon_id"],
                level=w.get("level", 1),
                ascension_phase=w.get("ascension_phase", 0),
                refinement_rank=w.get("refinement_rank", 1),
                equipped_to_character=w.get("equipped_to_character", ""),
            )
            for w in data.get("weapons", [])
        ]
        loc_data = data.get("location", {})
        location = LocationState(
            region=loc_data.get("region", ""),
            subregion=loc_data.get("subregion", ""),
            waypoint_near=loc_data.get("waypoint_near", ""),
        )
        quest_data = data.get("active_quest", {})
        active_quest = QuestProgress(
            quest_id=quest_data.get("quest_id", ""),
            current_step_index=quest_data.get("current_step_index", 0),
            current_step_objective=quest_data.get("current_step_objective", ""),
            status=quest_data.get("status", "not_started"),
        )
        res_data = data.get("resources", {})
        resources = ResourceState(
            original_resin=res_data.get("original_resin", 160),
            resin_updated_at=res_data.get("resin_updated_at", 0.0),
            condensed_resin=res_data.get("condensed_resin", 0),
            fragile_resin=res_data.get("fragile_resin", 0),
            mora=res_data.get("mora", 0),
            primogems=res_data.get("primogems", 0),
            stardust=res_data.get("stardust", 0),
            starglitter=res_data.get("starglitter", 0),
        )
        daily_data = data.get("daily", {})
        daily = DailyCompletion(
            date=daily_data.get("date", ""),
            commissions_completed=daily_data.get("commissions_completed", 0),
            commission_rewards_claimed=daily_data.get("commission_rewards_claimed", False),
            ley_lines_blue=daily_data.get("ley_lines_blue", 0),
            ley_lines_gold=daily_data.get("ley_lines_gold", 0),
        )
        weekly_data = data.get("weekly", {})
        weekly = WeeklyCompletion(
            week_start=weekly_data.get("week_start", ""),
            trounce_discounts_used=weekly_data.get("trounce_discounts_used", 0),
            trounce_discounts_remaining=weekly_data.get("trounce_discounts_remaining", 3),
        )
        active_team = tuple(
            TeamSlot(character_id=s["character_id"], role=s.get("role", ""))
            for s in data.get("active_team", [])
        )
        return cls(
            uid=data.get("uid", ""),
            server=data.get("server", ""),
            ar=data.get("ar", 0),
            world_level=data.get("world_level", 0),
            characters=characters,
            weapons=weapons,
            unlocked_regions=data.get("unlocked_regions", []),
            unlocked_waypoints=data.get("unlocked_waypoints", []),
            activated_statues=data.get("activated_statues", []),
            location=location,
            active_quest=active_quest,
            resources=resources,
            daily=daily,
            weekly=weekly,
            active_team=active_team,
            archon_quest_progress=data.get("archon_quest_progress", {}),
            store_dir=store_dir or Path("accounts/default"),
            last_saved_at=data.get("last_saved_at", 0.0),
        )

    # ------------------------------------------------------------------
    # Update helpers
    # ------------------------------------------------------------------

    def update_resources(self, **kwargs: Any) -> None:
        """Update resource fields by name."""
        new_vals = {}
        for k, v in kwargs.items():
            if hasattr(self.resources, k):
                new_vals[k] = v
        if new_vals:
            current = self.resources.to_dict()
            current.update(new_vals)
            self.resources = ResourceState(**current)

    def update_location(self, region: str = "", subregion: str = "", waypoint_near: str = "") -> None:
        self.location = LocationState(
            region=region or self.location.region,
            subregion=subregion or self.location.subregion,
            waypoint_near=waypoint_near or self.location.waypoint_near,
        )

    def update_quest(self, quest_id: str = "", step_index: int | None = None,
                     objective: str = "", status: str = "") -> None:
        self.active_quest = QuestProgress(
            quest_id=quest_id or self.active_quest.quest_id,
            current_step_index=step_index if step_index is not None else self.active_quest.current_step_index,
            current_step_objective=objective or self.active_quest.current_step_objective,
            status=status or self.active_quest.status,
        )


def _parse_talents(talent_data: dict[str, Any]) -> tuple[int, int, int]:
    return (
        talent_data.get("normal_attack", 1),
        talent_data.get("elemental_skill", 1),
        talent_data.get("elemental_burst", 1),
    )
