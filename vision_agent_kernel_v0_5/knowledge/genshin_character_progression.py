"""Character progression knowledge: EXP costs, ascension materials, talent schedules.

Data sourced from Genshin Impact Wiki, HoneyHunterWorld, and official game data.
Covers R-01 through R-11 capability requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# EXP book definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExpBook:
    item_id: str
    name: str
    exp_value: int
    rarity: int


EXP_BOOKS: dict[str, ExpBook] = {
    "wanderers_advice": ExpBook("wanderers_advice", "Wanderer's Advice", 1000, 2),
    "adventurers_experience": ExpBook("adventurers_experience", "Adventurer's Experience", 5000, 3),
    "heros_wit": ExpBook("heros_wit", "Hero's Wit", 20000, 4),
}


# ---------------------------------------------------------------------------
# Level-up cost tables
# ---------------------------------------------------------------------------

# Mora cost per EXP book used
MORA_PER_EXP: dict[str, int] = {
    "wanderers_advice": 200,
    "adventurers_experience": 1000,
    "heros_wit": 4000,
}

# Total EXP needed from level 1 to each target level (cumulative)
# These are the standard values for all characters.
_LEVEL_EXP_TABLE: dict[int, int] = {
    20: 13_395,
    40: 68_435,
    50: 144_825,
    60: 363_220,
    70: 580_635,
    80: 1_225_715,
    90: 1_677_405,
}


def exp_to_level(target_level: int) -> int:
    """Return total EXP needed from level 1 to *target_level*."""
    if target_level <= 1:
        return 0
    # Find the closest lower milestone
    for lv in sorted(_LEVEL_EXP_TABLE, reverse=True):
        if lv <= target_level:
            return _LEVEL_EXP_TABLE[lv]
    return 0


# ---------------------------------------------------------------------------
# Ascension material tables
# ---------------------------------------------------------------------------

class Element(Enum):
    PYRO = "Pyro"
    HYDRO = "Hydro"
    ELECTRO = "Electro"
    CRYO = "Cryo"
    ANEMO = "Anemo"
    GEO = "Geo"
    DENDRO = "Dendro"


@dataclass(frozen=True, slots=True)
class AscensionMats:
    """Materials needed for a single ascension."""
    ascension_level: int        # character level cap after ascension (20/40/50/60/70/80)
    mora: int
    gem_sliver: int             # tier 1 gem
    gem_fragment: int           # tier 2 gem
    gem_chunk: int              # tier 3 gem
    gem_gemstone: int           # tier 4 gem
    local_specialty: int        # regional specialty count
    common_damaged: int         # tier 1 common drop (e.g., Damaged Mask)
    common_intact: int          # tier 2 common drop
    common_phosphorescent: int  # tier 3 common drop
    boss_material: int          # world boss drop (e.g., Everflame Seed)


# Gem names by element (tier: sliver, fragment, chunk, gemstone)
GEM_NAMES: dict[str, tuple[str, str, str, str]] = {
    "Pyro":    ("Agnidus Agate Sliver",    "Agnidus Agate Fragment",    "Agnidus Agate Chunk",    "Agnidus Agate Gemstone"),
    "Hydro":   ("Varunada Lazurite Sliver", "Varunada Lazurite Fragment", "Varunada Lazurite Chunk", "Varunada Lazurite Gemstone"),
    "Electro": ("Vajrada Amethyst Sliver",  "Vajrada Amethyst Fragment",  "Vajrada Amethyst Chunk",  "Vajrada Amethyst Gemstone"),
    "Cryo":    ("Shivada Jade Sliver",      "Shivada Jade Fragment",      "Shivada Jade Chunk",      "Shivada Jade Gemstone"),
    "Anemo":   ("Vayuda Turquoise Sliver",  "Vayuda Turquoise Fragment",  "Vayuda Turquoise Chunk",  "Vayuda Turquoise Gemstone"),
    "Geo":     ("Prithiva Topaz Sliver",    "Prithiva Topaz Fragment",    "Prithiva Topaz Chunk",    "Prithiva Topaz Gemstone"),
    "Dendro":  ("Nagadus Emerald Sliver",   "Nagadus Emerald Fragment",   "Nagadus Emerald Chunk",   "Nagadus Emerald Gemstone"),
}

# Boss material names by element
BOSS_MATERIALS: dict[str, str] = {
    "Pyro":    "Everflame Seed",
    "Hydro":   "Cleansing Heart",
    "Electro": "Lightning Prism",
    "Cryo":    "Hoarfrost Core",
    "Anemo":   "Hurricane Seed",
    "Geo":     "Basalt Pillar",
    "Dendro":  "Majestic Hooked Beak",
}

# Common enemy drop names by drop family
COMMON_DROP_FAMILIES: dict[str, tuple[str, str, str]] = {
    "hilichurl_mask":  ("Damaged Mask",    "Stained Mask",      "Ominous Mask"),
    "slime_condensate": ("Slime Condensate", "Slime Secretions", "Slime Concentrate"),
    "arrowhead":       ("Firm Arrowhead",  "Sharp Arrowhead",   "Weathered Arrowhead"),
    "scroll":          ("Divining Scroll", "Sealed Scroll",     "Forbidden Curse Scroll"),
    "insignia":        ("Treasure Hoarder Insignia", "Silver Raven Insignia", "Golden Raven Insignia"),
    "whopperflower":   ("Nectar",          "Shimmering Nectar", "Energy Nectar"),
    "fleece":          ("Grey Hair",       "Smooth Hair",       "Glowing Hair"),
}

# Default common drop family (hilichurl masks - most characters use these)
DEFAULT_DROP_FAMILY = "hilichurl_mask"

# Ascension costs: keyed by ascension_level (the level cap after ascending)
# These are the same for ALL characters regardless of element.
_ASCENSION_COSTS: dict[int, AscensionMats] = {
    20: AscensionMats(20, 2000,
                      gem_sliver=1, gem_fragment=0, gem_chunk=0, gem_gemstone=0,
                      local_specialty=3, common_damaged=3, common_intact=0, common_phosphorescent=0,
                      boss_material=0),
    40: AscensionMats(40, 20000,
                      gem_sliver=0, gem_fragment=3, gem_chunk=0, gem_gemstone=0,
                      local_specialty=10, common_damaged=0, common_intact=15, common_phosphorescent=0,
                      boss_material=2),
    50: AscensionMats(50, 20000,
                      gem_sliver=0, gem_fragment=0, gem_chunk=6, gem_gemstone=0,
                      local_specialty=20, common_damaged=0, common_intact=0, common_phosphorescent=12,
                      boss_material=4),
    60: AscensionMats(60, 30000,
                      gem_sliver=0, gem_fragment=0, gem_chunk=3, gem_gemstone=0,
                      local_specialty=30, common_damaged=0, common_intact=0, common_phosphorescent=18,
                      boss_material=8),
    70: AscensionMats(70, 40000,
                      gem_sliver=0, gem_fragment=0, gem_chunk=0, gem_gemstone=3,
                      local_specialty=45, common_damaged=0, common_intact=0, common_phosphorescent=12,
                      boss_material=12),
    80: AscensionMats(80, 60000,
                      gem_sliver=0, gem_fragment=0, gem_chunk=0, gem_gemstone=6,
                      local_specialty=60, common_damaged=0, common_intact=0, common_phosphorescent=24,
                      boss_material=20),
}


def get_ascension_cost(ascension_level: int) -> AscensionMats | None:
    """Return ascension material costs for a given level cap."""
    return _ASCENSION_COSTS.get(ascension_level)


def total_ascension_mats_to_level(target_level: int, element: str) -> dict[str, int]:
    """Calculate total materials needed to ascend from level 1 to *target_level*.

    Returns a dict of material_name -> count.
    """
    result: dict[str, int] = {"mora": 0}
    gems = GEM_NAMES.get(element, GEM_NAMES["Pyro"])
    boss_mat = BOSS_MATERIALS.get(element, "Unknown Boss Material")

    for asc_lv in sorted(_ASCENSION_COSTS):
        if asc_lv >= target_level:
            break
        cost = _ASCENSION_COSTS[asc_lv]
        result["mora"] = result.get("mora", 0) + cost.mora
        if cost.gem_sliver:
            result[gems[0]] = result.get(gems[0], 0) + cost.gem_sliver
        if cost.gem_fragment:
            result[gems[1]] = result.get(gems[1], 0) + cost.gem_fragment
        if cost.gem_chunk:
            result[gems[2]] = result.get(gems[2], 0) + cost.gem_chunk
        if cost.gem_gemstone:
            result[gems[3]] = result.get(gems[3], 0) + cost.gem_gemstone
        if cost.boss_material:
            result[boss_mat] = result.get(boss_mat, 0) + cost.boss_material
        if cost.local_specialty:
            result["local_specialty"] = result.get("local_specialty", 0) + cost.local_specialty
        if cost.common_damaged:
            result["common_drop_t1"] = result.get("common_drop_t1", 0) + cost.common_damaged
        if cost.common_intact:
            result["common_drop_t2"] = result.get("common_drop_t2", 0) + cost.common_intact
        if cost.common_phosphorescent:
            result["common_drop_t3"] = result.get("common_drop_t3", 0) + cost.common_phosphorescent

    return result


# ---------------------------------------------------------------------------
# Talent upgrade costs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TalentCost:
    """Materials needed to upgrade one talent from *from_level* to *from_level+1*."""
    from_level: int          # current talent level (1-9)
    mora: int
    book_teachings: int      # tier 1 talent book
    book_guide: int          # tier 2 talent book
    book_philosophies: int   # tier 3 talent book
    common_t1: int           # common drop tier 1
    common_t2: int           # common drop tier 2
    common_t3: int           # common drop tier 3
    boss_material: int       # weekly boss drop (from level 7+)
    crown: bool = False      # Crown of Insight (level 10 only)


_TALENT_COSTS: dict[int, TalentCost] = {
    1:  TalentCost(1,  12500,   book_teachings=3, book_guide=0, book_philosophies=0,
                   common_t1=6, common_t2=0, common_t3=0, boss_material=0),
    2:  TalentCost(2,  17500,   book_teachings=2, book_guide=0, book_philosophies=0,
                   common_t1=3, common_t2=0, common_t3=0, boss_material=0),
    3:  TalentCost(3,  25000,   book_teachings=0, book_guide=2, book_philosophies=0,
                   common_t1=0, common_t2=3, common_t3=0, boss_material=0),
    4:  TalentCost(4,  30000,   book_teachings=0, book_guide=4, book_philosophies=0,
                   common_t1=0, common_t2=4, common_t3=0, boss_material=0),
    5:  TalentCost(5,  37500,   book_teachings=0, book_guide=6, book_philosophies=0,
                   common_t1=0, common_t2=6, common_t3=0, boss_material=0),
    6:  TalentCost(6,  120000,  book_teachings=0, book_guide=0, book_philosophies=3,
                   common_t1=0, common_t2=0, common_t3=3, boss_material=0),
    7:  TalentCost(7,  260000,  book_teachings=0, book_guide=0, book_philosophies=4,
                   common_t1=0, common_t2=0, common_t3=4, boss_material=1),
    8:  TalentCost(8,  450000,  book_teachings=0, book_guide=0, book_philosophies=6,
                   common_t1=0, common_t2=0, common_t3=6, boss_material=1),
    9:  TalentCost(9,  700000,  book_teachings=0, book_guide=0, book_philosophies=9,
                   common_t1=0, common_t2=0, common_t3=9, boss_material=2, crown=True),
}


def get_talent_cost(current_level: int) -> TalentCost | None:
    """Return cost to upgrade talent from *current_level* to *current_level + 1*."""
    return _TALENT_COSTS.get(current_level)


# ---------------------------------------------------------------------------
# Talent book schedule
# ---------------------------------------------------------------------------

class TalentBookDomain(Enum):
    """Genshin talent book domains and their daily rotation."""
    FORSAKEN_RIFT = "Forsaken Rift"           # Mondstadt: Freedom, Resistance, Ballad
    TAISHAN_MANSION = "Taishan Mansion"       # Liyue: Diligence, Gold, Prosperity
    VIOLET_COURT = "Violet Court"             # Inazuma: Transience, Elegance, Light
    STEEPLE_OF_SIGNIFICANCE = "Steeple of Significance"  # Sumeru: Admonition, Ingenuity, Praxis
    PALE_FORGOTTEN = "Pale Forgotten Flower"  # Fontaine: Equity, Justice, Order
    BLAZING_URSA = "Blazing Ursa Major"       # Natlan: kindling


# Talent book to domain mapping
TALENT_BOOK_DOMAINS: dict[str, TalentBookDomain] = {
    "Freedom":    TalentBookDomain.FORSAKEN_RIFT,
    "Resistance": TalentBookDomain.FORSAKEN_RIFT,
    "Ballad":     TalentBookDomain.FORSAKEN_RIFT,
    "Diligence":  TalentBookDomain.TAISHAN_MANSION,
    "Gold":       TalentBookDomain.TAISHAN_MANSION,
    "Prosperity": TalentBookDomain.TAISHAN_MANSION,
    "Transience": TalentBookDomain.VIOLET_COURT,
    "Elegance":   TalentBookDomain.VIOLET_COURT,
    "Light":      TalentBookDomain.VIOLET_COURT,
    "Admonition":  TalentBookDomain.STEEPLE_OF_SIGNIFICANCE,
    "Ingenuity":   TalentBookDomain.STEEPLE_OF_SIGNIFICANCE,
    "Praxis":      TalentBookDomain.STEEPLE_OF_SIGNIFICANCE,
    "Equity":     TalentBookDomain.PALE_FORGOTTEN,
    "Justice":    TalentBookDomain.PALE_FORGOTTEN,
    "Order":      TalentBookDomain.PALE_FORGOTTEN,
}

# Daily rotation: day_of_week (0=Mon, 6=Sun) -> set of available books
TALENT_BOOK_SCHEDULE: dict[int, tuple[str, ...]] = {
    0: ("Freedom", "Prosperity", "Transience", "Admonition", "Equity"),       # Monday
    1: ("Resistance", "Diligence", "Elegance", "Ingenuity", "Justice"),       # Tuesday
    2: ("Ballad", "Gold", "Light", "Praxis", "Order"),                        # Wednesday
    3: ("Freedom", "Prosperity", "Transience", "Admonition", "Equity"),       # Thursday
    4: ("Resistance", "Diligence", "Elegance", "Ingenuity", "Justice"),       # Friday
    5: ("Ballad", "Gold", "Light", "Praxis", "Order"),                        # Saturday
    6: (),  # Sunday: all books available
}

# Character -> talent book mapping (F2P characters + common ones)
CHARACTER_TALENT_BOOKS: dict[str, str] = {
    "amber":      "Freedom",
    "kaeya":      "Ballad",
    "lisa":       "Ballad",
    "barbara":    "Ballad",
    "xiangling":  "Diligence",
    "bennett":    "Resistance",
    "xingqiu":    "Gold",
    "noelle":     "Resistance",
    "fischl":     "Ballad",
    "collei":     "Praxis",
    "razor":      "Resistance",
    "sucrose":    "Freedom",
    "yanfei":     "Gold",
}


def books_available_today(day_of_week: int) -> tuple[str, ...]:
    """Return talent books available on *day_of_week* (0=Mon, 6=Sun)."""
    if day_of_week == 6:
        # Sunday: all books available
        return tuple(TALENT_BOOK_DOMAINS.keys())
    return TALENT_BOOK_SCHEDULE.get(day_of_week, ())


# ---------------------------------------------------------------------------
# Weapon enhancement costs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WeaponAscendCost:
    """Materials for one weapon ascension."""
    ascension_level: int    # weapon level cap after ascension
    mora: int
    domain_t1: int          # weapon ascension material tier 1
    domain_t2: int          # weapon ascension material tier 2
    domain_t3: int          # weapon ascension material tier 3
    domain_t4: int          # weapon ascension material tier 4 (elite)
    common_t1: int
    common_t2: int
    common_t3: int


# Weapon domain material schedules (same pattern as talent books)
WEAPON_DOMAIN_SCHEDULE: dict[int, tuple[str, ...]] = {
    0: ("Decarabian", "Liyue Monday/Wed", "Inazuma Mon/Wed"),   # Monday
    1: ("Boreal", "Liyue Tue/Thu", "Inazuma Tue/Thu"),           # Tuesday
    2: ("Dandelion", "Liyue Fri/Sun", "Inazuma Fri/Sun"),        # Wednesday
    3: ("Decarabian", "Liyue Monday/Wed", "Inazuma Mon/Wed"),   # Thursday
    4: ("Boreal", "Liyue Tue/Thu", "Inazuma Tue/Thu"),           # Friday
    5: ("Dandelion", "Liyue Fri/Sun", "Inazuma Fri/Sun"),        # Saturday
    6: (),  # Sunday: all available
}

# Weapon material domains by region
WEAPON_DOMAIN_NAMES: dict[str, str] = {
    "monstadt": "Cecilia Garden",
    "liyue": "Hidden Palace of Lianshan Formula",
    "inazuma": "Court of Flowing Sand",
    "sumeru": "Tower of Abject Pride",
    "fontaine": "Echoes of the Deep",
}


# ---------------------------------------------------------------------------
# Material synthesis (3:1 conversion)
# ---------------------------------------------------------------------------

SYNTHESIS_RATIO = 3  # 3 lower-tier -> 1 higher-tier

# Materials that can be crafted at the crafting bench (3:1 ratio)
SYNTHESIZABLE_FAMILIES: tuple[str, ...] = (
    "gem",          # elemental gems: Sliver -> Fragment -> Chunk -> Gemstone
    "talent_book",  # Teachings -> Guide -> Philosophies
    "weapon_mat",   # weapon domain materials: tile -> mosaic -> segment -> chunk
    "common_drop",  # common drops: Damaged -> Stained -> Ominous
)


# ---------------------------------------------------------------------------
# Weekly boss drop schedule
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WeeklyBossInfo:
    boss_id: str
    name: str
    region: str
    teleport_waypoint: str
    resin_discount: int       # first 3 bosses: 30 resin each
    full_cost: int            # after 3: 60 resin
    talent_materials: tuple[str, ...]  # possible weekly boss drops
    artifact_sets: tuple[str, ...]


WEEKLY_BOSSES: dict[str, WeeklyBossInfo] = {
    "dvalin": WeeklyBossInfo(
        "dvalin", "Confront Stormterror", "Mondstadt",
        "Stormterror's Lair", 30, 60,
        ("Dvalin's Sigh", "Dvalin's Claw", "Dvalin's Plume"),
        ("Gladiator's Finale", "Wanderer's Troupe"),
    ),
    "childe": WeeklyBossInfo(
        "childe", "Enter the Golden House", "Liyue",
        "Golden House", 30, 60,
        ("Tusk of Monoceros Caeli", "Masterless Starglass", "Shard of a Foul Legacy"),
        ("Gladiator's Finale", "Wanderer's Troupe"),
    ),
    "azhdaha": WeeklyBossInfo(
        "azhdaha", "Beneath the Dragon-Queller", "Liyue",
        "Nantianmen", 30, 60,
        ("Bloodjade Branch", "Dragon Lord's Crown", "Gilded Scale"),
        ("Gladiator's Finale", "Wanderer's Troupe"),
    ),
    "signora": WeeklyBossInfo(
        "signora", "Narukami Island: Tenshukaku", "Inazuma",
        "Tenshukaku", 30, 60,
        ("Molten Moment", "Ashen Heart", "Hellfire Butterfly"),
        ("Gladiator's Finale", "Wanderer's Troupe", "Crimson Witch"),
    ),
    "raiden_weekly": WeeklyBossInfo(
        "raiden_weekly", "End of the Oneiric Euthymia", "Inazuma",
        "Plane of Euthymia", 30, 60,
        ("The Meaning of Aeons", "Mudra of the Malefic General", "Tears of the Calamitous God"),
        ("Gladiator's Finale", "Wanderer's Troupe"),
    ),
}


# ---------------------------------------------------------------------------
# Build priority (R-06: progression priority ordering)
# ---------------------------------------------------------------------------

# Investment ROI ranking: higher ROI first
BUILD_INVESTMENT_PRIORITY: tuple[dict[str, Any], ...] = (
    {
        "category": "weapon_level",
        "roi": 10,
        "reason": "Weapon ATK directly multiplies all damage. Cheapest upgrade.",
        "max_level_priority": 70,  # level weapon to at least 70 first
    },
    {
        "category": "character_level",
        "roi": 9,
        "reason": "Base stats scale with level. Ascend at 20/40/50/60.",
        "target_levels": (20, 40, 50, 60, 70, 80),
    },
    {
        "category": "talent_burst",
        "roi": 8,
        "reason": "Elemental Burst is often the primary damage source.",
        "target_level": 6,
    },
    {
        "category": "talent_skill",
        "roi": 7,
        "reason": "Elemental Skill provides off-field damage or utility.",
        "target_level": 6,
    },
    {
        "category": "artifact_main_stats",
        "roi": 6,
        "reason": "Correct main stat > substats. Focus on Sands/Goblet/Circlet.",
        "target": "4pc correct set with correct main stats",
    },
    {
        "category": "talent_normal",
        "roi": 3,
        "reason": "Normal attacks only matter for on-field DPS.",
        "target_level": 6,
    },
    {
        "category": "artifact_substats",
        "roi": 2,
        "reason": "Substat optimization is resin-inefficient pre-AR45.",
        "target": "20+ CV substats",
    },
)


# ---------------------------------------------------------------------------
# AR breakthrough domains
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ARBreakthrough:
    ar_required: int
    domain_name: str
    domain_location: str
    recommended_team: tuple[str, ...]
    key_mechanics: tuple[str, ...]


AR_BREAKTHROUGHS: dict[int, ARBreakthrough] = {
    25: ARBreakthrough(
        25, "Ascend: Clear the Ruins", "Midsummer Courtyard (Mondstadt)",
        ("xiangling", "kaeya", "barbara", "amber"),
        ("Elemental reaction focused", "Timer challenge"),
    ),
    35: ARBreakthrough(
        35, "Clear the Abyssal Moon", "Clear Pool and Mountain Cavern (Liyue)",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Higher enemy levels", "Multiple waves"),
    ),
    45: ARBreakthrough(
        45, "Bloom and Grief", "Clear Pool and Mountain Cavern (Liyue)",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Full combat challenge", "5-star artifact unlock"),
    ),
    50: ARBreakthrough(
        50, "Realm of Slumber", "Clear Pool and Mountain Cavern (Liyue)",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Highest difficulty scaling", "Requires well-built team"),
    ),
}


# ---------------------------------------------------------------------------
# Resin costs reference
# ---------------------------------------------------------------------------

RESIN_COSTS: dict[str, int] = {
    "normal_boss": 40,
    "weekly_boss_discount": 30,
    "weekly_boss_full": 60,
    "domain_20_resin": 20,
    "domain_40_resin": 40,   # condensed resin = double rewards
    "ley_line_blossom": 20,
    "talent_domain": 20,
    "weapon_domain": 20,
    "artifact_domain": 20,
}

RESIN_MAX = 200  # Increased from 160 to 200 in v5.0
RESIN_RECOVERY_MINUTES = 8  # 1 resin per 8 minutes (unchanged in 5.0)
