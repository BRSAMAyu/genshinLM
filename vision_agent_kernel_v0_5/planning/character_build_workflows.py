"""Character build workflows and advanced resource management.

Covers:
- R-15: Weapon refinement (consume duplicate weapons)
- R-20: Artifact substat evaluation (crit/ER/ATK scoring)
- R-23: Artifact salvage (feed trash artifacts as enhancement material)
- R-24: Artifact transmutation (Mystic Offering: 3→1 targeted 5-star)
- R-27: Party configuration execution
- R-28: Party save/switch (multiple presets)
- R-29: Elemental resonance utilization
- R-30: Enemy-specific team adaptation
- M-05: Condensed resin crafting
- M-06: Backpack inventory check
- M-07: Material synthesis (3:1 upgrade)
- M-08: Elemental gem conversion (Dust of Azoth)
- M-14: Expedition dispatch (integrated with daily_loop_executor)
- M-15: Parametric Transformer usage
- M-16: Serenitea Pot (Realm) currency collection

Integrates with:
- knowledge/genshin_character_progression.py for material data
- planning/resource_manager.py for resource tracking
- planning/character_build_planner.py for build planning
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Artifact evaluation (R-20)
# ---------------------------------------------------------------------------

class SubstatType(str, Enum):
    CRIT_RATE = "crit_rate"
    CRIT_DMG = "crit_dmg"
    ENERGY_RECHARGE = "energy_recharge"
    ATK_PERCENT = "atk_percent"
    HP_PERCENT = "hp_percent"
    DEF_PERCENT = "def_percent"
    ELEMENTAL_MASTERY = "elemental_mastery"
    FLAT_ATK = "flat_atk"
    FLAT_HP = "flat_hp"
    FLAT_DEF = "flat_def"


# Weight based on KQM/Akasha methodology — higher = more valuable
SUBSTAT_WEIGHTS: dict[SubstatType, float] = {
    SubstatType.CRIT_RATE: 1.0,
    SubstatType.CRIT_DMG: 1.0,
    SubstatType.ENERGY_RECHARGE: 0.8,
    SubstatType.ATK_PERCENT: 0.6,
    SubstatType.HP_PERCENT: 0.4,
    SubstatType.DEF_PERCENT: 0.3,
    SubstatType.ELEMENTAL_MASTERY: 0.5,
    SubstatType.FLAT_ATK: 0.1,
    SubstatType.FLAT_HP: 0.05,
    SubstatType.FLAT_DEF: 0.05,
}


@dataclass(slots=True)
class ArtifactSubstat:
    """A single artifact substat."""
    stat_type: SubstatType
    value: float
    max_value: float = 0.0

    @property
    def roll_quality(self) -> float:
        """How close this roll is to max (0.0-1.0)."""
        if self.max_value <= 0:
            return 0.5
        return min(self.value / self.max_value, 1.0)


@dataclass(slots=True)
class ArtifactEval:
    """Evaluation result for an artifact."""
    score: float               # 0.0-1.0 weighted quality
    is_good: bool = False      # score >= 0.6
    is_great: bool = False     # score >= 0.8
    should_keep: bool = True
    recommended_fodder: bool = False  # Good for feeding to other artifacts


class ArtifactEvaluator:
    """Evaluates artifact substat quality (R-20).

    Uses weighted scoring based on community standards (KQM/Akasha).
    Artifacts scoring below 0.4 are recommended as fodder.
    """

    KEEP_THRESHOLD = 0.4
    GOOD_THRESHOLD = 0.6
    GREAT_THRESHOLD = 0.8

    def evaluate(self, substats: list[ArtifactSubstat],
                 main_stat_relevant: bool = True,
                 priority_stats: list[SubstatType] | None = None,
                 ) -> ArtifactEval:
        """Evaluate artifact quality from its substats."""
        if not substats:
            return ArtifactEval(score=0.0, should_keep=False, recommended_fodder=True)

        total_weight = 0.0
        max_possible = 0.0

        for sub in substats:
            weight = SUBSTAT_WEIGHTS.get(sub.stat_type, 0.1)
            # Boost weight for priority stats
            if priority_stats and sub.stat_type in priority_stats:
                weight *= 1.5
            total_weight += weight * sub.roll_quality
            max_possible += weight

        score = total_weight / max_possible if max_possible > 0 else 0.0
        score = min(score, 1.0)

        return ArtifactEval(
            score=score,
            is_good=score >= self.GOOD_THRESHOLD,
            is_great=score >= self.GREAT_THRESHOLD,
            should_keep=score >= self.KEEP_THRESHOLD,
            recommended_fodder=score < self.KEEP_THRESHOLD,
        )

    def find_fodder(self, artifacts: list[list[ArtifactSubstat]]) -> list[int]:
        """Find indices of artifacts recommended as fodder."""
        fodder: list[int] = []
        for i, subs in enumerate(artifacts):
            eval_result = self.evaluate(subs)
            if eval_result.recommended_fodder:
                fodder.append(i)
        return fodder


# ---------------------------------------------------------------------------
# Weapon refinement (R-15)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RefinementResult:
    """Result of weapon refinement."""
    weapon_name: str
    new_refinement: int        # R1-R5
    duplicates_consumed: int
    mora_cost: int = 0


class WeaponRefinery:
    """Manages weapon refinement operations (R-15).

    Consumes duplicate weapons to increase refinement rank (R1→R5).
    """

    MORA_COST_PER_REFINE = 1000  # Approximate

    def can_refine(self, weapon_name: str, current_refinement: int,
                   duplicates_available: int) -> bool:
        """Check if refinement is possible."""
        if current_refinement < 1 or current_refinement > 5:
            return False
        return current_refinement < 5 and duplicates_available >= 1

    def refine(self, weapon_name: str, current_refinement: int,
               duplicates_available: int) -> RefinementResult | None:
        """Execute refinement if possible."""
        if not self.can_refine(weapon_name, current_refinement, duplicates_available):
            return None

        return RefinementResult(
            weapon_name=weapon_name,
            new_refinement=current_refinement + 1,
            duplicates_consumed=1,
            mora_cost=self.MORA_COST_PER_REFINE * (current_refinement + 1),
        )


# ---------------------------------------------------------------------------
# Artifact salvage & transmutation (R-23, R-24)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SalvagePlan:
    """Plan for feeding artifacts as enhancement material."""
    target_artifact: str
    fodder_artifacts: list[str] = field(default_factory=list)
    estimated_xp: int = 0
    mora_cost: int = 0


class ArtifactSalvager:
    """Manages artifact enhancement via fodder feeding (R-23)."""

    XP_PER_5STAR = 2520
    XP_PER_4STAR = 1260
    XP_PER_3STAR = 630
    MORA_PER_XP = 1  # 1 mora per enhancement point

    def plan_salvage(self, target: str, fodder_rarity: int,
                     fodder_count: int) -> SalvagePlan:
        """Plan artifact salvage/enhancement."""
        if fodder_count <= 0:
            return SalvagePlan(target_artifact=target)
        xp_table = {5: self.XP_PER_5STAR, 4: self.XP_PER_4STAR, 3: self.XP_PER_3STAR}
        xp_per = xp_table.get(fodder_rarity, 630)
        total_xp = xp_per * fodder_count

        return SalvagePlan(
            target_artifact=target,
            fodder_artifacts=[f"fodder_{i}" for i in range(fodder_count)],
            estimated_xp=total_xp,
            mora_cost=total_xp * self.MORA_PER_XP,
        )


@dataclass(slots=True)
class TransmutePlan:
    """Plan for Mystic Offering artifact transmutation."""
    input_artifacts: list[str] = field(default_factory=list)  # 3 artifacts
    target_set: str = ""
    target_slot: str = ""    # "flower", "plume", "sands", "goblet", "circlet"


class ArtifactTransmuter:
    """Manages Mystic Offering (3 5-star → 1 targeted 5-star) (R-24)."""

    INPUT_COUNT = 3
    REQUIRED_RARITY = 5

    def plan_transmute(self, input_artifacts: list[str],
                       target_set: str, target_slot: str,
                       input_rarities: list[int] | None = None) -> TransmutePlan | None:
        """Plan artifact transmutation via Mystic Offering.

        Args:
            input_artifacts: List of artifact identifiers.
            target_set: Target artifact set name.
            target_slot: Target slot (flower/plume/sands/goblet/circlet).
            input_rarities: Optional list of rarities corresponding to input_artifacts.
                           Must all be 5-star for Mystic Offering.
        """
        if len(input_artifacts) < self.INPUT_COUNT:
            return None

        if input_rarities is not None:
            if len(input_rarities) < self.INPUT_COUNT:
                return None
            selected_rarities = input_rarities[:self.INPUT_COUNT]
            if any(r != self.REQUIRED_RARITY for r in selected_rarities):
                return None

        return TransmutePlan(
            input_artifacts=input_artifacts[:self.INPUT_COUNT],
            target_set=target_set,
            target_slot=target_slot,
        )


# ---------------------------------------------------------------------------
# Elemental resonance (R-29)
# ---------------------------------------------------------------------------

class ElementalResonance(str, Enum):
    FERVENT_FLAMES = "fervent_flames"      # 2 Pyro: ATK +25%
    SOOTHING_WATERS = "soothing_waters"     # 2 Hydro: Max HP +25%
    HIGH_VOLTAGE = "high_voltage"           # 2 Electro: Energy recharge
    SHATTERING_ICE = "shattering_ice"       # 2 Cryo: Crit rate vs frozen
    IMPETUOUS_WINDS = "impetuous_winds"     # 2 Anemo: Movement SPD +10%, CD -5%
    ENDURING_ROCK = "enduring_rock"         # 2 Geo: Shield strength +15%
    SPRAWLING_GREEN = "sprawling_green"     # 2 Dendro: EM +50


RESONANCE_CONDITIONS: dict[ElementalResonance, str] = {
    ElementalResonance.FERVENT_FLAMES: "pyro",
    ElementalResonance.SOOTHING_WATERS: "hydro",
    ElementalResonance.HIGH_VOLTAGE: "electro",
    ElementalResonance.SHATTERING_ICE: "cryo",
    ElementalResonance.IMPETUOUS_WINDS: "anemo",
    ElementalResonance.ENDURING_ROCK: "geo",
    ElementalResonance.SPRAWLING_GREEN: "dendro",
}


class ElementalResonanceCalculator:
    """Calculates active elemental resonances from team composition (R-29)."""

    def get_active_resonances(self, team_elements: list[str]) -> list[ElementalResonance]:
        """Get all active resonances for a team's element composition."""
        element_counts: dict[str, int] = {}
        for elem in team_elements:
            element_counts[elem] = element_counts.get(elem, 0) + 1

        active: list[ElementalResonance] = []
        for resonance, element in RESONANCE_CONDITIONS.items():
            if element_counts.get(element, 0) >= 2:
                active.append(resonance)
        return active


# ---------------------------------------------------------------------------
# Enemy-specific team adaptation (R-30)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EnemyProfile:
    """Enemy characteristics that influence team selection."""
    enemy_id: str
    element_shield: str = ""
    elemental_weaknesses: list[str] = field(default_factory=list)
    is_boss: bool = False
    is_abyss: bool = False
    has_flying_phase: bool = False
    has_healing: bool = False


class TeamAdapter:
    """Adapts team composition for specific enemies (R-30)."""

    def recommend_changes(self, current_elements: list[str],
                          enemy: EnemyProfile) -> list[str]:
        """Recommend element changes for the team based on enemy profile."""
        recommendations: list[str] = []

        if enemy.element_shield:
            from combat.genshin_element_reactions import GenshinReactionTable
            try:
                table = GenshinReactionTable()
                counter = table.get_shield_counter(enemy.element_shield)
                if counter not in ("none", "unknown") and counter not in current_elements:
                    recommendations.append(f"Add {counter} for {enemy.element_shield} shield")
            except (KeyError, ValueError):
                pass

        if enemy.elemental_weaknesses:
            for weak in enemy.elemental_weaknesses:
                if weak not in current_elements:
                    recommendations.append(f"Add {weak} for weakness exploit")

        if enemy.has_flying_phase:
            recommendations.append("Consider bow user for flying phase")

        return recommendations


# ---------------------------------------------------------------------------
# Resource crafting (M-05, M-07, M-08)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CraftingRecipe:
    """A crafting/synthesis recipe."""
    recipe_id: str
    input_materials: dict[str, int] = field(default_factory=dict)
    output_material: str = ""
    output_count: int = 1
    mora_cost: int = 0
    crafting_time_sec: int = 0


class CondensedResinCrafter:
    """Manages condensed resin crafting (M-05).

    Condensed resin costs 40 original resin + 1 crystal core.
    """

    RESIN_COST = 40
    CRYSTAL_CORE_COST = 1

    def can_craft(self, original_resin: int, crystal_cores: int) -> bool:
        return original_resin >= self.RESIN_COST and crystal_cores >= self.CRYSTAL_CORE_COST

    def craft(self, original_resin: int, crystal_cores: int) -> bool:
        if not self.can_craft(original_resin, crystal_cores):
            return False
        return True  # Caller updates resource state


class MaterialSynthesizer:
    """Manages material synthesis (3:1 upgrade, M-07)."""

    RATIO = 3  # 3 lower → 1 higher

    def can_synthesize(self, material_count: int) -> bool:
        return material_count >= self.RATIO

    def plan_synthesis(self, material_name: str, available: int,
                       mora: int = 1000) -> dict[str, int]:
        """Plan synthesis operations. Returns {operations, total_mora}."""
        operations = available // self.RATIO
        return {
            "operations": operations,
            "output": operations,
            "mora_cost": operations * mora,
        }


class ElementGemConverter:
    """Manages elemental gem conversion via Dust of Azoth (M-08).

    Converts gems of one element to another element.
    """

    DUST_COST_PER_GEM = 1  # Dust of Azoth per gem

    def plan_conversion(self, source_element: str, target_element: str,
                        gem_tier: int, available: int) -> dict[str, int | str]:
        """Plan gem conversion."""
        return {
            "source_element": source_element,
            "target_element": target_element,
            "gem_count": available,
            "dust_cost": available * self.DUST_COST_PER_GEM,
        }


# ---------------------------------------------------------------------------
# Party management (R-27, R-28)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PartyPreset:
    """A saved party configuration."""
    preset_id: str
    name: str
    character_names: list[str] = field(default_factory=list)
    is_active: bool = False


class PartyManager:
    """Manages party presets and switching (R-27, R-28)."""

    MAX_PRESETS = 10
    PARTY_SIZE = 4

    def __init__(self) -> None:
        self._presets: dict[str, PartyPreset] = {}
        self._active_preset_id: str = ""

    @property
    def active_preset(self) -> PartyPreset | None:
        return self._presets.get(self._active_preset_id)

    @property
    def presets(self) -> list[PartyPreset]:
        return list(self._presets.values())

    def save_preset(self, preset_id: str, name: str,
                    characters: list[str]) -> PartyPreset | None:
        """Save a party preset."""
        if len(self._presets) >= self.MAX_PRESETS and preset_id not in self._presets:
            return None
        if len(characters) != self.PARTY_SIZE:
            return None

        preset = PartyPreset(
            preset_id=preset_id,
            name=name,
            character_names=characters,
        )
        self._presets[preset_id] = preset
        return preset

    def load_preset(self, preset_id: str) -> PartyPreset | None:
        """Load/switch to a saved party preset."""
        preset = self._presets.get(preset_id)
        if preset is None:
            return None
        # Deactivate old
        if self._active_preset_id in self._presets:
            self._presets[self._active_preset_id].is_active = False
        # Activate new
        preset.is_active = True
        self._active_preset_id = preset_id
        return preset

    def delete_preset(self, preset_id: str) -> bool:
        """Delete a saved preset."""
        if preset_id not in self._presets:
            return False
        del self._presets[preset_id]
        if self._active_preset_id == preset_id:
            self._active_preset_id = ""
        return True


# ---------------------------------------------------------------------------
# Inventory check (M-06)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class InventoryItem:
    """An item in the player's inventory."""
    item_id: str
    name: str
    quantity: int = 0
    category: str = ""  # "material", "weapon", "artifact", "food", "gadget"


class InventoryChecker:
    """Manages inventory checking (M-06)."""

    def __init__(self) -> None:
        self._items: dict[str, InventoryItem] = {}

    def update_item(self, item_id: str, name: str, quantity: int,
                    category: str = "") -> None:
        self._items[item_id] = InventoryItem(item_id, name, quantity, category)

    def get_quantity(self, item_id: str) -> int:
        return self._items.get(item_id, InventoryItem("", "", 0)).quantity

    def check_materials(self, required: dict[str, int]) -> dict[str, int]:
        """Check which materials are missing. Returns {item_id: shortfall}."""
        missing: dict[str, int] = {}
        for item_id, needed in required.items():
            have = self.get_quantity(item_id)
            if have < needed:
                missing[item_id] = needed - have
        return missing

    def items_by_category(self, category: str) -> list[InventoryItem]:
        return [i for i in self._items.values() if i.category == category]


# ---------------------------------------------------------------------------
# Parametric Transformer (M-15)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ParametricUsage:
    """Tracks parametric transformer usage."""
    last_used_day: str = ""     # ISO date
    is_available: bool = True
    materials_submitted: dict[str, int] = field(default_factory=dict)


class ParametricTransformer:
    """Manages parametric transformer usage (M-15).

    Weekly usage: submit 150 material points, get random rewards.
    """

    WEEKLY_COOLDOWN_DAYS = 7
    MATERIAL_POINT_TARGET = 150

    def can_use(self, days_since_last: int) -> bool:
        return days_since_last >= self.WEEKLY_COOLDOWN_DAYS

    def calculate_points(self, materials: dict[str, int],
                         point_values: dict[str, int]) -> int:
        """Calculate total material points for submission."""
        total = 0
        for mat_id, count in materials.items():
            value = point_values.get(mat_id, 1)
            total += value * count
        return total

    def plan_submission(self, available_materials: dict[str, int],
                        point_values: dict[str, int]) -> dict[str, int]:
        """Plan which materials to submit to reach target points."""
        target = self.MATERIAL_POINT_TARGET
        plan: dict[str, int] = {}
        current_points = 0

        # Sort by point value (use cheapest first)
        sorted_mats = sorted(point_values.items(), key=lambda x: x[1])

        for mat_id, point_val in sorted_mats:
            if current_points >= target:
                break
            available = available_materials.get(mat_id, 0)
            if available <= 0:
                continue
            needed = (target - current_points + point_val - 1) // point_val
            use = min(available, needed)
            plan[mat_id] = use
            current_points += use * point_val

        return plan


# ---------------------------------------------------------------------------
# Serenitea Pot / Realm (M-16)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RealmCurrency:
    """Tracks realm currency state."""
    current: int = 0
    max: int = 2400
    hours_to_full: float = 72.0

    @property
    def should_collect(self) -> bool:
        return self.current >= self.max * 0.8


class RealmManager:
    """Manages Serenitea Pot realm currency collection (M-16)."""

    def __init__(self) -> None:
        self._currency = RealmCurrency()

    @property
    def currency(self) -> RealmCurrency:
        return self._currency

    def update_currency(self, current: int) -> None:
        self._currency.current = current

    def collect(self) -> int:
        """Collect realm currency. Returns amount collected."""
        amount = self._currency.current
        self._currency.current = 0
        return amount


# ---------------------------------------------------------------------------
# Artifact main stat validator (R-34)
# ---------------------------------------------------------------------------

# Main stat requirements by slot and character role
VALID_MAIN_STATS: dict[str, dict[str, tuple[str, ...]]] = {
    "sands": {
        "dps": ("atk_percent", "elemental_mastery", "energy_recharge"),
        "support": ("energy_recharge", "hp_percent", "atk_percent"),
        "healer": ("hp_percent", "energy_recharge"),
    },
    "goblet": {
        "dps": ("physical_dmg_bonus", "pyro_dmg_bonus", "hydro_dmg_bonus", "electro_dmg_bonus",
                "cryo_dmg_bonus", "anemo_dmg_bonus", "geo_dmg_bonus", "dendro_dmg_bonus"),
        "support": ("elemental_mastery", "hp_percent", "atk_percent"),
        "healer": ("hp_percent", "healing_bonus"),
    },
    "circlet": {
        "dps": ("crit_rate", "crit_dmg", "atk_percent"),
        "support": ("crit_rate", "healing_bonus", "hp_percent"),
        "healer": ("healing_bonus", "hp_percent", "crit_rate"),
    },
}


@dataclass(slots=True)
class MainStatValidation:
    """Result of main stat validation."""
    is_valid: bool
    expected_stats: tuple[str, ...]
    actual_stat: str
    slot: str
    severity: str = "none"  # "none", "warning", "error"


class MainStatValidator:
    """Validates artifact main stat correctness (R-34).

    Detects wrong main stat on Sands/Goblet/Circlet based on character role.
    """

    def validate(
        self,
        slot: str,
        main_stat: str,
        character_role: str,
    ) -> MainStatValidation:
        """Check if main stat is appropriate for slot and role."""
        slot_key = slot.lower()
        role_key = character_role.lower()

        # Normalize role to known categories
        if role_key in ("main_dps", "off_field_dps", "sub_dps", "dps"):
            role_key = "dps"
        elif role_key in ("support", "off_field_support"):
            role_key = "support"
        elif role_key in ("healer", "healer_support"):
            role_key = "healer"

        valid_stats = VALID_MAIN_STATS.get(slot_key, {}).get(role_key, ())
        stat_lower = main_stat.lower().replace(" ", "_")

        is_valid = stat_lower in valid_stats

        return MainStatValidation(
            is_valid=is_valid,
            expected_stats=valid_stats,
            actual_stat=stat_lower,
            slot=slot_key,
            severity="error" if not is_valid else "none",
        )

    def validate_batch(
        self,
        artifacts: list[tuple[str, str]],  # (slot, main_stat) pairs
        character_role: str,
    ) -> list[MainStatValidation]:
        """Validate multiple artifacts at once."""
        return [
            self.validate(slot, main_stat, character_role)
            for slot, main_stat in artifacts
        ]


# ---------------------------------------------------------------------------
# AR-phase artifact evaluator (R-35)
# ---------------------------------------------------------------------------

class ARPhaseAwareEvaluator:
    """Artifact evaluator that adjusts thresholds based on AR phase (R-35).

    Before AR45, don't chase 5-star artifacts or high rolls.
    """

    # Thresholds by AR phase
    PHASE_THRESHOLDS: dict[str, tuple[float, float, float]] = {
        "early": (0.2, 0.3, 0.4),    # AR < 30: very lenient
        "mid": (0.3, 0.4, 0.5),     # AR 30-44: moderate
        "late": (0.4, 0.6, 0.8),    # AR 45+: full standards
    }

    # Prioritize 4-star artifacts before AR45
    STAR_PREFERENCE: dict[str, int] = {
        "early": 4,
        "mid": 4,
        "late": 5,
    }

    def __init__(self, base_evaluator: ArtifactEvaluator) -> None:
        self._base = base_evaluator

    def _get_phase(self, ar: int) -> str:
        if ar < 30:
            return "early"
        if ar < 45:
            return "mid"
        return "late"

    def evaluate(
        self,
        substats: list[ArtifactSubstat],
        ar: int,
        main_stat_relevant: bool = True,
        priority_stats: list[SubstatType] | None = None,
    ) -> ArtifactEval:
        """Evaluate artifact with AR-adapted thresholds."""
        phase = self._get_phase(ar)
        thresholds = self.PHASE_THRESHOLDS[phase]
        keep_thresh, good_thresh, great_thresh = thresholds

        total_weight = 0.0
        max_possible = 0.0

        for sub in substats:
            weight = SUBSTAT_WEIGHTS.get(sub.stat_type, 0.1)
            if priority_stats and sub.stat_type in priority_stats:
                weight *= 1.5
            total_weight += weight * sub.roll_quality
            max_possible += weight

        score = total_weight / max_possible if max_possible > 0 else 0.0
        score = min(score, 1.0)

        return ArtifactEval(
            score=score,
            is_good=score >= good_thresh,
            is_great=score >= great_thresh,
            should_keep=score >= keep_thresh,
            recommended_fodder=score < keep_thresh,
        )

    def preferred_rarity(self, ar: int) -> int:
        """Return preferred artifact rarity for the given AR."""
        phase = self._get_phase(ar)
        return self.STAR_PREFERENCE.get(phase, 5)


# ---------------------------------------------------------------------------
# R-44: Breakthrough material overflow conversion (Artifact → ascension)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OverflowConversionPlan:
    """Plan for converting excess materials to useful forms."""
    source_material: str
    target_material: str
    conversion_ratio: int  # e.g., 3:1
    available_count: int
    converted_count: int = 0
    is_efficient: bool = True


class MaterialOverflowConverter:
    """Converts excess ascension/breakthrough materials to other forms (R-44).

    E.g., excess boss materials → synthesize into talent books,
    or use excess for weapon ascension.
    """

    # Materials that can be converted
    CONVERSION_PAIRS: dict[str, tuple[str, int]] = {
        # Boss material -> Talent book material
        "pyro_everlasting_essence": ("teachings_of_gold", 1),
        "electro_everlasting_essence": ("teachings_of_freedom", 1),
        # Weekly boss drops (1:1 conversion to weapon ascension)
        "dream_solvent": ("spirit_bound_essence", 1),
    }

    def plan_conversion(
        self,
        excess_materials: dict[str, int],
        target_material: str | None = None,
    ) -> list[OverflowConversionPlan]:
        """Plan conversions for excess materials."""
        plans: list[OverflowConversionPlan] = []

        for mat_id, count in excess_materials.items():
            if count < 3:  # Minimum for conversion
                continue

            conversion = self.CONVERSION_PAIRS.get(mat_id)
            if conversion:
                target, ratio = conversion
                plans.append(OverflowConversionPlan(
                    source_material=mat_id,
                    target_material=target,
                    conversion_ratio=ratio,
                    available_count=count,
                    converted_count=count // 3,
                    is_efficient=count >= 6,
                ))

        return plans


# ---------------------------------------------------------------------------
# R-45: Triple elemental resonance analyzer
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TripleResonanceResult:
    """Result of checking triple elemental team composition."""
    active_resonances: list[str]
    bonus_effect: str
    is_synergistic: bool
    recommendation: str


class TripleResonanceAnalyzer:
    """Analyzes team elemental composition for 3+ element resonance effects (R-45).

    Genshin has double resonance, but certain team compositions benefit from
    having specific element distributions for different content.
    """

    # Resonance effects
    RESONANCE_EFFECTS: dict[str, str] = {
        "fervent_flames": "ATK +25%",
        "soothing_waters": "Max HP +25%",
        "high_voltage": "Energy Recharge +10% for 8s after Electro reaction",
        "shattering_ice": "CRIT Rate +15% vs frozen enemies",
        "impetuous_winds": "Movement SPD +10%, CD -5%",
        "enduring_rock": "Shield strength +15%",
        "sprawling_green": "EM +50",
    }

    # Optimal element distributions
    OPTIMAL_DISTRIBUTIONS: dict[str, tuple[str, int]] = {
        "vaporize_team": ("pyro", 2),   # 2 pyro + hydro
        "melt_team": ("pyro", 2),      # 2 pyro + cryo
        "freeze_team": ("cryo", 2),    # 2 cryo + hydro
        "hyperbloom": ("dendro", 2),   # 2 dendro + hydro + electro
    }

    def analyze_team(
        self,
        elements: list[str],
        team_type: str | None = None,
    ) -> TripleResonanceResult:
        """Analyze elemental composition for resonance effects."""
        active_resonances: list[str] = []

        # Count elements
        element_counts: dict[str, int] = {}
        for elem in elements:
            element_counts[elem] = element_counts.get(elem, 0) + 1

        # Check resonances
        for elem, count in element_counts.items():
            if count >= 2:
                resonance = self._get_resonance_for_element(elem)
                if resonance:
                    active_resonances.append(resonance)

        # Determine if team is synergistic
        is_synergistic = len(active_resonances) >= 2

        # Generate recommendation
        recommendation = ""
        if not active_resonances:
            recommendation = "Add 2 characters of same element for resonance"
        elif len(active_resonances) == 1:
            recommendation = "Good resonance active, consider adding more"

        return TripleResonanceResult(
            active_resonances=active_resonances,
            bonus_effect=", ".join(active_resonances),
            is_synergistic=is_synergistic,
            recommendation=recommendation,
        )

    def _get_resonance_for_element(self, element: str) -> str:
        """Get resonance name for element."""
        mapping = {
            "pyro": "fervent_flames",
            "hydro": "soothing_waters",
            "electro": "high_voltage",
            "cryo": "shattering_ice",
            "anemo": "impetuous_winds",
            "geo": "enduring_rock",
            "dendro": "sprawling_green",
        }
        return mapping.get(element, "")


# ---------------------------------------------------------------------------
# R-46: Energy recharge calculator
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EnergyRechargeNeed:
    """Energy recharge requirement for a character."""
    character_id: str
    base_cost: int                # Base burst energy cost
    optimal_er: float             # Optimal ER%
    current_er: float = 100.0     # Current ER from artifacts
    needs_battery: bool = False
    battery_character: str = ""


class EnergyRechargeCalculator:
    """Calculates optimal energy recharge requirements for team battery (R-46).

    Determines how much ER is needed for consistent burst uptime and
    recommends battery characters.
    """

    # Base energy costs by character
    BASE_ENERGY_COST: dict[str, int] = {
        "xiangling": 80,
        "xingqiu": 80,
        "bennett": 60,
        "kaeya": 60,
        "fischl": 60,
        "barbara": 80,
        "noelle": 80,
        "collei": 60,
    }

    # Battery efficiency (ER needed per energy generated)
    BATTERY_EFFICIENCY = 0.5  # For Favonius weapons

    def calculate_er_need(
        self,
        character_id: str,
        team_elements: list[str],
        has_favonius: bool = False,
    ) -> EnergyRechargeNeed:
        """Calculate optimal ER requirement for a character."""
        base_cost = self.BASE_ENERGY_COST.get(character_id, 60)

        # Adjust for team composition
        has_pyro = "pyro" in team_elements  # Benny buff
        has_electro = "electro" in team_elements  # Particle generation

        optimal_er = 100.0
        needs_battery = False
        battery_char = ""

        # If no Favonius and no battery
        if not has_favonius:
            if base_cost >= 80:
                optimal_er = 180.0 if not has_pyro else 150.0
                needs_battery = True
            elif base_cost >= 60:
                optimal_er = 140.0 if not has_pyro else 120.0

            if needs_battery:
                battery_char = self._find_battery(team_elements)

        # With Favonius, can reduce ER requirement
        if has_favonius:
            optimal_er *= 0.8

        return EnergyRechargeNeed(
            character_id=character_id,
            base_cost=base_cost,
            optimal_er=optimal_er,
            needs_battery=needs_battery,
            battery_character=battery_char,
        )

    def _find_battery(self, elements: list[str]) -> str:
        """Find best battery character for the team."""
        if "anemo" in elements:
            return "traveler"
        if "electro" in elements:
            return "fischl"
        if "pyro" in elements:
            return "bennett"
        return "xingqiu"


# ---------------------------------------------------------------------------
# R-47: Four-star artifact alternatives
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FourStarAlternative:
    """Four-star artifact as alternative to five-star."""
    set_name: str
    slot: str
    main_stat: str
    substat_priority: tuple[str, ...]
    replacement_for_5star: str
    efficiency_pct: float


FOUR_STAR_ALTERNATIVES: list[FourStarAlternative] = [
    FourStarAlternative(
        set_name="Martial Hero",
        slot="circlet",
        main_stat="crit_rate",
        substat_priority=("crit_dmg", "atk_percent", "energy_recharge"),
        replacement_for_5star="Gladiator's Finale",
        efficiency_pct=75.0,
    ),
    FourStarAlternative(
        set_name="Exile",
        slot="sands",
        main_stat="energy_recharge",
        substat_priority=("atk_percent", "hp_percent"),
        replacement_for_5star="Emblem of Severed Fate",
        efficiency_pct=60.0,
    ),
    FourStarAlternative(
        set_name="Scholar",
        slot="goblet",
        main_stat="atk_percent",
        substat_priority=("crit_rate", "crit_dmg"),
        replacement_for_5star="Noblesse Oblige",
        efficiency_pct=70.0,
    ),
]


class FourStarAlternativeRecommender:
    """Recommends four-star artifacts as alternatives to five-star (R-47).

    Used when player hasn't reached AR45 for reliable 5-star drops.
    """

    def recommend_for_role(
        self,
        role: str,
        ar: int,
    ) -> list[FourStarAlternative]:
        """Recommend 4-star alternatives for a character role."""
        if ar >= 45:
            return []  # No need, can farm 5-star

        # Pre-AR45: recommend 4-star alternatives
        if role in ("main_dps", "off_field_dps"):
            return [alt for alt in FOUR_STAR_ALTERNATIVES if alt.efficiency_pct >= 70]
        return FOUR_STAR_ALTERNATIVES


# ---------------------------------------------------------------------------
# R-49: Enhancement stop-loss decision (+12 vs +16 vs +20)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EnhancementDecision:
    """Decision on artifact enhancement level."""
    recommended_level: int        # +12, +16, or +20
    reasoning: str
    is_cost_effective: bool
    risk_score: float = 0.0       # 0.0-1.0


class EnhancementStopLoss:
    """Determines optimal artifact enhancement levels (R-49).

    Implements stop-loss logic for +12 vs +16 vs +20 decisions.
    """

    # Enhancement costs (mora) and risk levels
    ENHANCEMENT_COSTS: dict[int, int] = {
        4: 2000,
        8: 4000,
        12: 8000,
        16: 16000,
        20: 40000,
    }

    # Risk thresholds
    STOP_AT_12_RISK = 0.7        # Stop if risk > 70%
    STOP_AT_16_RISK = 0.4        # Stop at 16 if risk > 40%

    def decide(
        self,
        artifact_score: float,
        main_stat_relevant: bool,
        substat_roll_quality: float,
        current_level: int,
        mora_available: int,
    ) -> EnhancementDecision:
        """Decide optimal enhancement level.

        Args:
            artifact_score: Overall artifact quality (0.0-1.0)
            main_stat_relevant: Whether main stat is correct
            substat_roll_quality: Average substat roll quality (0.0-1.0)
            current_level: Current enhancement level
            mora_available: Available mora for enhancement

        Returns:
            EnhancementDecision with recommendation
        """
        # Calculate risk score
        risk_score = 1.0 - artifact_score
        if not main_stat_relevant:
            risk_score += 0.2
        risk_score = min(1.0, risk_score)

        # Determine recommended level
        if risk_score >= self.STOP_AT_12_RISK:
            # High risk: stop at +12
            target_level = 12
            reasoning = "High risk artifact - stop at +12"
        elif risk_score >= self.STOP_AT_16_RISK:
            # Medium risk: stop at +16
            target_level = 16
            reasoning = "Medium risk - stop at +16 to limit investment"
        else:
            # Low risk: continue to +20 if good quality
            if artifact_score >= 0.7 and substat_roll_quality >= 0.6:
                target_level = 20
                reasoning = "High quality artifact - fully enhance to +20"
            else:
                target_level = 16
                reasoning = "Good artifact - enhance to +16"

        # Check if we have enough mora
        cost_remaining = sum(
            self.ENHANCEMENT_COSTS.get(l, 0)
            for l in range(current_level + 1, target_level + 1)
        )

        is_cost_effective = cost_remaining <= mora_available

        if not is_cost_effective:
            target_level = current_level + 4  # Limit to affordable
            reasoning = f"Limited by mora budget - enhance to +{target_level}"

        return EnhancementDecision(
            recommended_level=target_level,
            reasoning=reasoning,
            is_cost_effective=is_cost_effective,
            risk_score=risk_score,
        )


# ---------------------------------------------------------------------------
# Inventory capacity manager (R-36)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class InventoryCapacityWarning:
    """Warning about inventory capacity."""
    current: int
    max_capacity: int
    usage_percent: float
    severity: str = "none"  # "none", "caution", "warning", "critical"
    recommended_actions: list[str] = field(default_factory=list)


class InventoryCapacityManager:
    """Manages inventory capacity warnings and batch filtering (R-36)."""

    DEFAULT_CAPACITY = 1500
    CAUTION_THRESHOLD = 0.80   # 80%
    WARNING_THRESHOLD = 0.90   # 90%
    CRITICAL_THRESHOLD = 0.95  # 95%

    def __init__(self, max_capacity: int = DEFAULT_CAPACITY) -> None:
        self._max_capacity = max_capacity
        self._categories: dict[str, int] = {
            "material": 999,
            "weapon": 999,
            "artifact": 999,
            "food": 999,
            "gadget": 999,
        }

    def check_capacity(
        self,
        total_items: int,
        artifact_count: int = 0,
        material_count: int = 0,
    ) -> InventoryCapacityWarning:
        """Check current inventory capacity and return warnings."""
        usage = total_items / self._max_capacity
        severity = "none"

        if usage >= self.CRITICAL_THRESHOLD:
            severity = "critical"
        elif usage >= self.WARNING_THRESHOLD:
            severity = "warning"
        elif usage >= self.CAUTION_THRESHOLD:
            severity = "caution"

        actions: list[str] = []
        if severity in ("warning", "critical"):
            actions.append("Feed trash artifacts as enhancement material")
        if severity == "critical":
            actions.append("Use Mystic Offering to convert 3 artifacts into 1 targeted 5-star")
            actions.append("Batch lock good artifacts, mass-feed the rest")
        if artifact_count > 200:
            actions.append(f"Consider filtering: {artifact_count} artifacts detected")

        return InventoryCapacityWarning(
            current=total_items,
            max_capacity=self._max_capacity,
            usage_percent=usage,
            severity=severity,
            recommended_actions=actions,
        )

    def batch_filter_recommendation(
        self,
        artifact_scores: list[tuple[str, float]],  # (artifact_id, score)
        keep_threshold: float = 0.4,
    ) -> list[str]:
        """Suggest batch filtering based on artifact scores."""
        keep: list[str] = []
        feed: list[str] = []

        for artifact_id, score in artifact_scores:
            if score >= keep_threshold:
                keep.append(artifact_id)
            else:
                feed.append(artifact_id)

        return [
            f"Keep {len(keep)} artifacts (score >= {keep_threshold})",
            f"Feed {len(feed)} artifacts as fodder",
        ]
