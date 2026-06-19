"""Game-asset adapters — load the real enhancement-pack data resources.

The project ships substantial curated game data (character/team combat profiles,
monster DB, world graph with 230+ waypoints, skill libraries) collected for
Genshin / HSR. These adapters load that real data into the shapes the Phase 0-6
controllers and sims consume, so the dogfood benchmarks run on real game balance
instead of synthetic stats — and so the curated assets are actually used.

Pure read access; safe to call from tests. Falls back gracefully if a file is
absent so environments without the data still work.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a core dep
    yaml = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent.parent
_COMBAT = _ROOT / "data" / "combat_profiles"
_KNOWLEDGE = _ROOT / "knowledge"


# Behaviour preference → our controller role vocabulary.
_ROLE_MAP = {
    "on_field_dps": "dps",
    "off_field_dps": "sub",
    "support": "sub",
    "healer": "healer",
    "shielder": "healer",  # defensive sustain role
    "battery": "sub",
    "hybrid": "dps",
}

# Monster class_id → combat tier.
_TIER_MAP = {
    "monster_normal": "mob",
    "monster_elite": "elite",
    "monster_boss": "boss",
}


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    character_id: str
    element: str
    role: str            # dps | sub | healer
    e_skill_cd_ms: int
    q_energy_cost: float
    style: str


@dataclass(frozen=True, slots=True)
class TeamProfile:
    team_id: str
    members: tuple[str, ...]
    rotation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonsterProfile:
    monster_id: str
    name: str
    element: str
    tier: str            # mob | elite | boss
    weaknesses: tuple[str, ...]


def _load_yaml(path: Path) -> Any:
    """Load a YAML file, returning None if absent or unparseable.

    Some curated data files contain stray unquoted colons in name fields (e.g.
    ``name_en: Ruin Drake: Earthguard``); rather than crash, we skip a broken
    file so the rest of the asset set still loads. The known offender is logged
    once.
    """
    if yaml is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError:
        import logging
        logging.getLogger("game_assets").warning("Skipping unparseable asset %s", path)
        return None


@lru_cache(maxsize=1)
def load_character_profiles() -> dict[str, CharacterProfile]:
    data = _load_yaml(_COMBAT / "character_profiles.yaml") or {}
    out: dict[str, CharacterProfile] = {}
    for c in data.get("characters", []):
        cid = str(c.get("character_id", ""))
        if not cid:
            continue
        out[cid] = CharacterProfile(
            character_id=cid,
            element=str(c.get("element", "none")),
            role=_ROLE_MAP.get(str(c.get("behavior_preference", "")), "dps"),
            e_skill_cd_ms=int(c.get("e_skill_cd_ms", 6000)),
            q_energy_cost=float(c.get("q_energy_cost", 60)),
            style=str(c.get("strategy_style", "sustained_dps")),
        )
    return out


@lru_cache(maxsize=1)
def load_team_profiles() -> list[TeamProfile]:
    data = _load_yaml(_COMBAT / "team_profiles.yaml") or {}
    teams: list[TeamProfile] = []
    for t in data.get("teams", []):
        teams.append(TeamProfile(
            team_id=str(t.get("team_id", "")),
            members=tuple(str(m) for m in t.get("members", [])),
            rotation=tuple(str(r) for r in t.get("recommended_rotation", [])),
        ))
    return teams


@lru_cache(maxsize=1)
def load_monsters() -> dict[str, MonsterProfile]:
    data = _load_yaml(_KNOWLEDGE / "genshin_monsters.yaml") or {}
    out: dict[str, MonsterProfile] = {}
    for m in data.get("monsters", []):
        mid = str(m.get("monster_id", ""))
        if not mid:
            continue
        out[mid] = MonsterProfile(
            monster_id=mid,
            name=str(m.get("name_en", m.get("name", mid))),
            element=str(m.get("element", "none")),
            tier=_TIER_MAP.get(str(m.get("class_id", "")), "mob"),
            weaknesses=tuple(str(w) for w in m.get("weaknesses", [])),
        )
    return out


def resolve_team_comp(team_id: str) -> list[CharacterProfile]:
    """Resolve a named team to its member character profiles (skips unknowns)."""
    chars = load_character_profiles()
    for team in load_team_profiles():
        if team.team_id == team_id:
            return [chars[m] for m in team.members if m in chars]
    return []


def team_comp_to_sim(team_id: str, *, atk: float = 60.0) -> list[dict[str, object]]:
    """Turn a real named team into combat-sim member dicts.

    Maps real character data (element, role, skill cd, burst energy) onto the
    sim's stat shape. ATK is a stand-in scalar since the curated profiles don't
    carry numeric attack; everything structural (elements, roles, cooldowns,
    energy economy, reactions) comes from the real data.
    """
    members = resolve_team_comp(team_id)
    out: list[dict[str, object]] = []
    for i, c in enumerate(members[:4]):  # parties of up to 4
        skill_cd = max(2, round(c.e_skill_cd_ms / 1000))
        burst_cost = c.q_energy_cost if c.q_energy_cost > 0 else 60.0
        # Promote the rotation lead (first member) to dps so the comp has an
        # on-field damage lead; the data's behaviour_preference rarely tags an
        # explicit on-field dps for off-field-heavy meta comps.
        role = "dps" if i == 0 else c.role
        member = {
            "name": c.character_id, "element": c.element, "role": role,
            "hp": 1000.0 if role != "healer" else 1100.0,
            "atk": atk * (1.0 if role == "dps" else 0.7),
            "skill_cd": skill_cd, "skill_mult": 3.0 if role != "healer" else 1.5,
            "burst_cost": burst_cost, "burst_mult": 6.0 if role == "dps" else 4.0,
        }
        if role == "healer":
            member["heal_amount"] = 380.0
        out.append(member)
    return out


def monster_to_sim(monster_id: str) -> dict[str, object]:
    """Turn a real monster entry into a combat-sim enemy dict (tier-scaled HP/atk)."""
    monsters = load_monsters()
    m = monsters.get(monster_id)
    if m is None:
        return {"hp": 800.0, "atk": 70.0, "aura": "", "attack_interval": 6, "telegraph_lead": 1}
    hp_atk = {"mob": (800.0, 70.0), "elite": (1800.0, 130.0), "boss": (2800.0, 200.0)}
    hp, atk = hp_atk.get(m.tier, hp_atk["mob"])
    return {
        "hp": hp, "atk": atk, "aura": "" if m.element == "none" else m.element,
        "attack_interval": 6 if m.tier == "mob" else (4 if m.tier == "elite" else 4),
        "telegraph_lead": 1, "aoe": m.tier == "boss", "monster_id": m.monster_id,
        "weaknesses": list(m.weaknesses),
    }
