from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ElementReaction:
    name: str
    trigger_element: str
    base_element: str
    damage_multiplier: float
    effect: str
    visual_signature: str
    tactical_value: str


class GenshinReactionTable:
    """Lookup table for elemental reactions."""

    REACTIONS: list[ElementReaction] = [
        ElementReaction("Vaporize", "pyro", "hydro", 2.0, "Steam AoE", "White steam cloud", "High"),
        ElementReaction("Vaporize_Reverse", "hydro", "pyro", 1.5, "Steam", "White steam", "Medium"),
        ElementReaction("Melt", "pyro", "cryo", 2.0, "Ice melt", "Water vapor", "High"),
        ElementReaction("Melt_Reverse", "cryo", "pyro", 1.5, "Freeze burst", "Ice particles", "Medium"),
        ElementReaction("Overloaded", "pyro", "electro", 1.2, "AoE explosion", "Orange explosion + screen shake", "High"),
        ElementReaction("Electro-Charged", "electro", "hydro", 0.6, "Chain lightning", "Electric arcs between targets", "Medium"),
        ElementReaction("Superconduct", "cryo", "electro", 0.5, "Physical DEF down", "Blue-purple ice burst", "Medium"),
        ElementReaction("Frozen", "hydro", "cryo", 0.0, "Freeze target", "Ice blue coating", "High"),
        ElementReaction("Swirl", "anemo", "any", 0.6, "Spread element", "Green tornado changes color", "Medium"),
        ElementReaction("Crystallize", "geo", "any", 0.0, "Generate shield", "Element-colored shard", "Low"),
        ElementReaction("Bloom", "hydro", "dendro", 0.0, "Produce seed", "Green seed object", "Medium"),
        ElementReaction("Hyperbloom", "electro", "dendro_seed", 1.5, "Homing missile", "Green-purple tracking shot", "High"),
        ElementReaction("Burgeon", "pyro", "dendro_seed", 1.5, "Seed explosion", "Green-orange AoE", "High"),
        ElementReaction("Quicken", "electro", "dendro", 0.0, "Mark target", "Purple-green flash", "Medium"),
        ElementReaction("Aggravate", "electro", "quicken", 1.15, "Damage boost", "Enhanced purple bolt", "High"),
        ElementReaction("Spread", "dendro", "quicken", 1.25, "Damage boost", "Enhanced green shot", "High"),
    ]

    def get_reaction(self, trigger: str, base: str) -> ElementReaction | None:
        """Look up reaction by trigger + base element pair."""
        for reaction in self.REACTIONS:
            if reaction.trigger_element == trigger and reaction.base_element == base:
                return reaction
        if trigger == base:
            return None
        for reaction in self.REACTIONS:
            if reaction.trigger_element == trigger and reaction.base_element == "any":
                return reaction
        return None

    def get_shield_counter(self, shield_element: str) -> str:
        """Get the element that counters a given shield type.

        Counter rules based on in-game elemental shield mechanics:
        - Pyro shield    -> Hydro (water puts out fire)
        - Hydro shield   -> Cryo (freeze)
        - Cryo shield    -> Pyro (melt)
        - Electro shield -> Pyro (overloaded) or Cryo (superconduct)
        - Dendro shield  -> Pyro (burning)
        - Anemo shield   -> none  (cannot swirl shields)
        - Geo shield     -> none  (use claymore / blunt instead)
        """
        counters: dict[str, str] = {
            "pyro": "hydro",
            "hydro": "cryo",
            "cryo": "pyro",
            "electro": "pyro",
            "dendro": "pyro",
            "geo": "none",
            "anemo": "none",
        }
        return counters.get(shield_element, "pyro")

    def get_team_reactions(self, team_elements: list[str]) -> list[ElementReaction]:
        """Get all possible reactions for a team's element composition."""
        results: list[ElementReaction] = []
        seen: set[str] = set()
        for trigger in team_elements:
            for base in team_elements:
                if trigger == base:
                    continue
                reaction = self.get_reaction(trigger, base)
                if reaction is not None and reaction.name not in seen:
                    seen.add(reaction.name)
                    results.append(reaction)
        return results
