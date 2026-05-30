"""F2P character builds, weapons, artifacts, and boss strategies for autonomous progression.

Covers the optimal free-to-play progression path from AR 1 through endgame.
Data sourced from KeqingMains, Game8, IGN, HoYoLAB community guides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Character build data
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class CharacterBuild:
    character_id: str
    element: str
    weapon_type: str
    role: str                    # off_field_dps, support, healer, main_dps, etc.
    tier: str                    # S, A, B
    source: str                  # how to obtain
    talent_priority: tuple[str, ...]
    best_weapon_f2p: str
    alt_weapons: tuple[str, ...]
    artifact_set: str
    artifact_alt: str
    artifact_main_stats: tuple[str, str, str]  # sands, goblet, circlet
    substat_priority: tuple[str, ...]


F2P_BUILDS: dict[str, CharacterBuild] = {
    "xiangling": CharacterBuild(
        character_id="xiangling", element="Pyro", weapon_type="Polearm",
        role="off_field_dps", tier="S", source="Spiral Abyss Floor 3",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="The Catch R5",
        alt_weapons=("Dragon's Bane", "Kitain Cross Spear", "Crescent Pike"),
        artifact_set="Emblem of Severed Fate 4pc",
        artifact_alt="Noblesse Oblige 2pc + Crimson Witch 2pc",
        artifact_main_stats=("ER% or ATK%", "Pyro DMG%", "CRIT Rate/DMG"),
        substat_priority=("CRIT DMG", "CRIT Rate", "Energy Recharge", "ATK%"),
    ),
    "xingqiu": CharacterBuild(
        character_id="xingqiu", element="Hydro", weapon_type="Sword",
        role="off_field_dps_support", tier="S", source="Paimon's Bargains / Gacha",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="Sacrificial Sword",
        alt_weapons=("Favonius Sword", "Amenoma Kageuchi"),
        artifact_set="Emblem of Severed Fate 4pc",
        artifact_alt="Noblesse Oblige 4pc",
        artifact_main_stats=("ATK% or ER%", "Hydro DMG%", "CRIT Rate/DMG"),
        substat_priority=("Energy Recharge", "CRIT Rate", "CRIT DMG", "ATK%"),
    ),
    "bennett": CharacterBuild(
        character_id="bennett", element="Pyro", weapon_type="Sword",
        role="support_healer_buffer", tier="S", source="Paimon's Bargains / Gacha",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="Sapwood Blade",
        alt_weapons=("Favonius Sword", "Prototype Rancour"),
        artifact_set="Noblesse Oblige 4pc",
        artifact_alt="Emblem of Severed Fate 4pc",
        artifact_main_stats=("HP% or ER%", "HP%", "HP% or Healing Bonus"),
        substat_priority=("Energy Recharge", "HP%", "HP flat", "CRIT Rate"),
    ),
    "fischl": CharacterBuild(
        character_id="fischl", element="Electro", weapon_type="Bow",
        role="off_field_dps", tier="A", source="Paimon's Bargains / Gacha / Events",
        talent_priority=("skill", "burst", "normal_attack"),
        best_weapon_f2p="The Stringless",
        alt_weapons=("Favonius Warbow", "Song of Stillness"),
        artifact_set="Golden Troupe 4pc",
        artifact_alt="Thundering Fury 2pc + Gladiator's Finale 2pc",
        artifact_main_stats=("ATK%", "Electro DMG%", "CRIT Rate/DMG"),
        substat_priority=("CRIT Rate", "CRIT DMG", "ATK%", "Energy Recharge"),
    ),
    "kaeya": CharacterBuild(
        character_id="kaeya", element="Cryo", weapon_type="Sword",
        role="off_field_dps_support", tier="A", source="Story (free at start)",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="Amenoma Kageuchi",
        alt_weapons=("Favonius Sword", "Harbinger of Dawn"),
        artifact_set="Blizzard Strayer 4pc (freeze) / Emblem of Severed Fate 4pc (sub-dps)",
        artifact_alt="Noblesse Oblige 4pc",
        artifact_main_stats=("ATK% or ER%", "Cryo DMG%", "CRIT Rate/DMG"),
        substat_priority=("Energy Recharge", "CRIT Rate", "CRIT DMG", "ATK%"),
    ),
    "barbara": CharacterBuild(
        character_id="barbara", element="Hydro", weapon_type="Catalyst",
        role="healer_support", tier="A", source="Story (free AR18)",
        talent_priority=("skill", "burst", "normal_attack"),
        best_weapon_f2p="Thrilling Tales of Dragon Slayers",
        alt_weapons=("Prototype Amber", "Magic Guide"),
        artifact_set="Ocean-Hued Clam 4pc",
        artifact_alt="Maiden Beloved 4pc",
        artifact_main_stats=("HP% or ER%", "HP%", "Healing Bonus or HP%"),
        substat_priority=("HP%", "Energy Recharge", "HP flat", "Healing Bonus"),
    ),
    "collei": CharacterBuild(
        character_id="collei", element="Dendro", weapon_type="Bow",
        role="dendro_support", tier="B", source="Sumeru Archon Quest completion",
        talent_priority=("skill", "burst", "normal_attack"),
        best_weapon_f2p="Favonius Warbow",
        alt_weapons=("The Stringless", "End of the Line"),
        artifact_set="Deepwood Memories 4pc",
        artifact_alt="Gilded Dreams 4pc",
        artifact_main_stats=("ER% or EM", "Dendro DMG%", "CRIT Rate/DMG or EM"),
        substat_priority=("Energy Recharge", "Elemental Mastery", "CRIT Rate", "ATK%"),
    ),
    "lisa": CharacterBuild(
        character_id="lisa", element="Electro", weapon_type="Catalyst",
        role="off_field_electro_support", tier="B", source="Story (free at start)",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="Thrilling Tales of Dragon Slayers",
        alt_weapons=("Mappa Mare", "Prototype Amber", "Magic Guide"),
        artifact_set="Thundering Fury 4pc / Noblesse Oblige 4pc",
        artifact_alt="Gilded Dreams 4pc (for hyperbloom)",
        artifact_main_stats=("EM or ER%", "Electro DMG% or EM", "EM or CRIT"),
        substat_priority=("Elemental Mastery", "Energy Recharge", "CRIT Rate", "ATK%"),
    ),
    "noelle": CharacterBuild(
        character_id="noelle", element="Geo", weapon_type="Claymore",
        role="shielder_healer_dps", tier="B", source="Beginner's Wish (guaranteed)",
        talent_priority=("normal_attack", "burst", "skill"),
        best_weapon_f2p="Whiteblind",
        alt_weapons=("Prototype Archaic", "Serpent Spine (BP)"),
        artifact_set="Husk of Opulent Dreams 4pc",
        artifact_alt="Gladiator's Finale 4pc",
        artifact_main_stats=("DEF%", "Geo DMG% or DEF%", "DEF% or CRIT Rate"),
        substat_priority=("DEF%", "CRIT Rate", "CRIT DMG", "Energy Recharge"),
    ),
    "amber": CharacterBuild(
        character_id="amber", element="Pyro", weapon_type="Bow",
        role="pyro_support_utility", tier="B", source="Story (free at start)",
        talent_priority=("burst", "skill", "normal_attack"),
        best_weapon_f2p="Favonius Warbow",
        alt_weapons=("Sharpshooter's Oath", "Recurve Bow"),
        artifact_set="Noblesse Oblige 4pc / Instructor 4pc",
        artifact_alt="Wanderer's Troupe 4pc",
        artifact_main_stats=("ER% or ATK%", "Pyro DMG%", "CRIT Rate/DMG"),
        substat_priority=("Energy Recharge", "CRIT Rate", "ATK%", "Elemental Mastery"),
    ),
}


# ---------------------------------------------------------------------------
# F2P weapons
# ---------------------------------------------------------------------------

F2P_WEAPONS: dict[str, dict[str, str]] = {
    "sword": {
        "best_general": "Finale of the Deep",
        "best_for_bennett": "Sapwood Blade",
        "best_for_energy": "Amenoma Kageuchi",
        "best_for_em": "Iron Sting",
        "best_3star": "Harbinger of Dawn",
    },
    "claymore": {
        "best_general": "Prototype Archaic",
        "best_for_def": "Whiteblind",
        "best_fontaine": "Tidal Shadow",
    },
    "polearm": {
        "best_overall_f2p": "The Catch R5 (free fishing)",
        "best_physical": "Crescent Pike",
        "best_fontaine": "Rightful Reward",
        "best_for_em": "Kitain Cross Spear",
    },
    "bow": {
        "best_general": "Song of Stillness",
        "best_for_fischl": "The Stringless",
        "best_charged_shot": "Prototype Crescent",
        "best_dps": "Hamayumi",
    },
    "catalyst": {
        "best_general": "Flowing Purity",
        "best_for_em": "Mappa Mare",
        "best_support": "Thrilling Tales of Dragon Slayers",
        "best_for_healer": "Prototype Amber",
    },
}


# ---------------------------------------------------------------------------
# Artifact set recommendations
# ---------------------------------------------------------------------------

ARTIFACT_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "national_team": {
        "xiangling": "Emblem of Severed Fate 4pc",
        "xingqiu": "Emblem of Severed Fate 4pc",
        "bennett": "Noblesse Oblige 4pc",
    },
    "hyperbloom": {
        "trigger": "Flower of Paradise Lost 4pc or Gilded Dreams 4pc",
        "dendro_support": "Deepwood Memories 4pc",
        "hydro_support": "Emblem of Severed Fate 4pc",
        "farm_domain": "Gilded Dreams + Deepwood Memories domain (resin efficient)",
    },
    "physical_dps": {
        "gold_standard": "2pc Pale Flame + 2pc Bloodstained Chivalry",
        "alternative": "4pc Gladiator's Finale",
    },
}


# ---------------------------------------------------------------------------
# Boss fight strategies for Archon Quests
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class BossStrategy:
    boss_id: str
    chapter: int
    act: int
    location: str
    f2p_team: tuple[str, ...]
    alt_team: tuple[str, ...]
    elements_needed: tuple[str, ...]
    key_mechanics: tuple[str, ...]
    difficulty: str
    tips: tuple[str, ...] = ()


ARCHON_BOSS_STRATEGIES: dict[str, BossStrategy] = {
    "dvalin": BossStrategy(
        boss_id="dvalin", chapter=0, act=3,
        location="Stormterror's Lair, Mondstadt",
        f2p_team=("amber", "kaeya", "lisa", "barbara"),
        alt_team=("xiangling", "xingqiu", "bennett", "kaeya"),
        elements_needed=("Ranged DPS", "Anemo"),
        key_mechanics=("Flying phase with aerial combat", "Platform phase with shields"),
        difficulty="moderate",
        tips=("Use ranged attacks during flying phase", "Break shields during platform phase"),
    ),
    "childe": BossStrategy(
        boss_id="childe", chapter=1, act=3,
        location="Golden House, Liyue",
        f2p_team=("xiangling", "bennett", "xingqiu", "kaeya"),
        alt_team=("xiangling", "bennett", "xingqiu", "noelle"),
        elements_needed=("Electro", "Cryo", "Ranged DPS"),
        key_mechanics=(
            "3-phase fight: Hydro -> Electro -> Dual element",
            "Phase transitions have attack windows",
            "Riptide marks on player enable extra attacks",
        ),
        difficulty="hard",
        tips=("Dodge whale attack in phase 3", "Use food buffs for DPS check"),
    ),
    "signora": BossStrategy(
        boss_id="signora", chapter=2, act=2,
        location="Tenshukaku, Inazuma City",
        f2p_team=("xiangling", "bennett", "kaeya", "barbara"),
        alt_team=("xiangling", "xingqiu", "kaeya", "bennett"),
        elements_needed=("Pyro for Phase 1", "Cryo/Hydro for Phase 2"),
        key_mechanics=(
            "Temperature gauge fills over time",
            "Phase 1 (Cryo): collect Hearts of Flame",
            "Phase 2 (Pyro): collect Frostflame seeds",
            "Must manage temperature to avoid HP drain",
        ),
        difficulty="hard",
        tips=("Always be near a temperature pickup", "Don't tunnel on DPS"),
    ),
    "raiden_shogun": BossStrategy(
        boss_id="raiden_shogun", chapter=2, act=3,
        location="Plane of Euthymia, Inazuma",
        f2p_team=("xiangling", "bennett", "xingqiu", "noelle"),
        alt_team=("xiangling", "bennett", "xingqiu", "kaeya"),
        elements_needed=("Pyro", "Hydro", "Cryo"),
        key_mechanics=(
            "Story fight: survive, not defeat",
            "Forced story mechanic during Musou no Hitotachi",
            "Dodge everything, especially wide slashes",
        ),
        difficulty="hard",
        tips=("National team core for damage", "Use Noelle for shield insurance"),
    ),
    "shouki_no_kami": BossStrategy(
        boss_id="shouki_no_kami", chapter=3, act=5,
        location="Joururi Workshop, Sumeru",
        f2p_team=("xiangling", "collei", "xingqiu", "noelle"),
        alt_team=("amber", "collei", "barbara", "noelle"),
        elements_needed=("Pyro", "Dendro", "Shielder"),
        key_mechanics=(
            "Giant boss with elemental cores",
            "Phase 2: collect energy blocks to charge device",
            "Must stun with device for damage window",
            "50-90% elemental resistance when not stunned",
        ),
        difficulty="very_hard",
        tips=("Shielder is critical (Noelle)", "Focus on collecting energy blocks in Phase 2"),
    ),
    "narwhal": BossStrategy(
        boss_id="narwhal", chapter=4, act=5,
        location="Fontaine",
        f2p_team=("xiangling", "bennett", "xingqiu", "kaeya"),
        alt_team=("xiangling", "xingqiu", "barbara", "noelle"),
        elements_needed=("Hydro counter", "General DPS"),
        key_mechanics=(
            "Giant whale boss",
            "Two phases with different attack patterns",
            "Avoid massive AoE attacks",
        ),
        difficulty="very_hard",
        tips=("Bring food buffs", "National team for sustained damage"),
    ),
}


# ---------------------------------------------------------------------------
# Build priority order for F2P progression
# ---------------------------------------------------------------------------

# Characters to build in this order (serves as the investment roadmap)
BUILD_PRIORITY: tuple[str, ...] = (
    "bennett",      # S-tier support, build first
    "xiangling",    # S-tier off-field DPS
    "xingqiu",      # S-tier off-field Hydro
    "kaeya",        # A-tier off-field Cryo
    "barbara",      # A-tier healer
    "fischl",       # A-tier off-field Electro (when obtained)
    "noelle",       # B-tier shielder/healer
    "collei",       # B-tier Dendro support (after Sumeru)
)

# Teams to build in order
TEAM_PROGRESSION: tuple[dict[str, Any], ...] = (
    {
        "name": "Early Survival Team",
        "ar_range": (1, 20),
        "members": ("amber", "kaeya", "lisa", "barbara"),
        "purpose": "Tutorial through Mondstadt",
    },
    {
        "name": "National Team Core",
        "ar_range": (20, 40),
        "members": ("xiangling", "xingqiu", "bennett", "kaeya"),
        "purpose": "Main team for Archon Quests through Inazuma",
    },
    {
        "name": "National Team + Flex",
        "ar_range": (40, 55),
        "members": ("xiangling", "xingqiu", "bennett", "fischl"),
        "purpose": "Optimized for Sumeru and beyond",
    },
    {
        "name": "Two-Team Abyss Ready",
        "ar_range": (55, 60),
        "members": (
            ("xiangling", "xingqiu", "bennett", "kaeya"),
            ("noelle", "collei", "barbara", "lisa"),
        ),
        "purpose": "Spiral Abyss two-team setup",
    },
)
