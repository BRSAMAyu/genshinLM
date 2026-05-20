from __future__ import annotations

from dataclasses import dataclass

from combat.genshin_element_reactions import GenshinReactionTable


@dataclass(frozen=True, slots=True)
class CombatAction:
    action: str
    character: int
    repeat: int = 1
    condition: str = ""
    priority: int = 50


@dataclass(frozen=True, slots=True)
class PriorityTrigger:
    condition: str
    action: str
    priority: int
    interrupt: bool = False


@dataclass(frozen=True, slots=True)
class FallbackStrategy:
    on_target_lost: str
    on_combo_break: str
    on_all_dead: str
    on_timeout: str


@dataclass(frozen=True, slots=True)
class CombatPlaybook:
    playbook_id: str
    team: list[str]
    enemy: str
    default_rotation: list[CombatAction]
    priority_triggers: list[PriorityTrigger]
    fallback: FallbackStrategy
    elemental_chain: list[str]


_ELEMENT_TO_SLOT: dict[str, int] = {
    "pyro": 1, "hydro": 2, "cryo": 3, "electro": 4,
    "anemo": 1, "geo": 2, "dendro": 3,
}


class GenshinCombatPlanner:
    """Generate combat playbooks for Genshin Impact encounters."""

    def __init__(self) -> None:
        self._reactions = GenshinReactionTable()

    def generate_playbook(
        self,
        team_elements: list[str],
        team_characters: list[str],
        enemy_id: str,
        enemy_weaknesses: list[str] | None = None,
    ) -> CombatPlaybook:
        weaknesses = enemy_weaknesses or self._get_weaknesses_from_kb(enemy_id)
        reaction_chain = self._plan_reaction_chain(team_elements, weaknesses)
        rotation = self._build_rotation(team_elements, reaction_chain)
        triggers = self._build_priority_triggers()
        fallback = FallbackStrategy(
            on_target_lost="re_acquire_target",
            on_combo_break="reset_rotation",
            on_all_dead="respawn_nearest_statue",
            on_timeout="fallback_basic_loop",
        )
        return CombatPlaybook(
            playbook_id=f"pb_{enemy_id}_{'_'.join(team_elements)}",
            team=list(team_characters) if team_characters else list(team_elements),
            enemy=enemy_id,
            default_rotation=rotation,
            priority_triggers=triggers,
            fallback=fallback,
            elemental_chain=reaction_chain,
        )

    def _plan_reaction_chain(
        self, team_elements: list[str], weaknesses: list[str]
    ) -> list[str]:
        available = self._reactions.get_team_reactions(team_elements)
        if not available:
            return []

        scored: list[tuple[float, str]] = []
        for rxn in available:
            score = rxn.damage_multiplier
            targets_weakness = (
                rxn.trigger_element in weaknesses or rxn.base_element in weaknesses
            )
            if targets_weakness:
                score += 5.0
            if rxn.tactical_value == "High":
                score += 2.0
            elif rxn.tactical_value == "Medium":
                score += 1.0
            scored.append((score, rxn.name))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [name for _, name in scored]

    def _build_rotation(
        self, team_elements: list[str], reaction_chain: list[str]
    ) -> list[CombatAction]:
        actions: list[CombatAction] = []

        if not reaction_chain:
            slot = _ELEMENT_TO_SLOT.get(team_elements[0], 1) if team_elements else 1
            actions.append(CombatAction(
                action="normal_attack", character=slot, repeat=5, priority=50,
            ))
            actions.append(CombatAction(
                action="e_skill", character=slot, condition="skill_e_ready", priority=40,
            ))
            actions.append(CombatAction(
                action="q_burst", character=slot, condition="energy_full", priority=30,
            ))
            return actions

        seen_elements: set[str] = set()
        for idx, rxn_name in enumerate(reaction_chain[:4]):
            rxn = self._find_reaction_by_name(rxn_name)
            if rxn is None:
                continue

            base_slot = self._slot_for_element(rxn.base_element, team_elements)
            trigger_slot = self._slot_for_element(rxn.trigger_element, team_elements)

            if rxn.base_element not in seen_elements:
                actions.append(CombatAction(
                    action="e_skill", character=base_slot,
                    condition="skill_e_ready", priority=40 - idx * 2,
                ))
                actions.append(CombatAction(
                    action="normal_attack", character=base_slot, repeat=3,
                    priority=50 - idx,
                ))
                seen_elements.add(rxn.base_element)

            actions.append(CombatAction(
                action="switch", character=trigger_slot, priority=35 - idx * 2,
            ))
            actions.append(CombatAction(
                action="e_skill", character=trigger_slot,
                condition="skill_e_ready", priority=38 - idx * 2,
            ))
            seen_elements.add(rxn.trigger_element)

        for elem in team_elements:
            slot = _ELEMENT_TO_SLOT.get(elem, 1)
            actions.append(CombatAction(
                action="q_burst", character=slot,
                condition="energy_full", priority=30,
            ))

        return actions

    def _build_priority_triggers(self) -> list[PriorityTrigger]:
        return [
            PriorityTrigger(
                condition="danger > 0.7", action="dodge", priority=0, interrupt=True,
            ),
            PriorityTrigger(
                condition="hp < 0.3", action="switch", priority=0, interrupt=True,
            ),
            PriorityTrigger(
                condition="energy_full", action="q_burst", priority=10,
            ),
            PriorityTrigger(
                condition="skill_e_ready", action="e_skill", priority=10,
            ),
            PriorityTrigger(
                condition="stamina < 0.2", action="stop_sprint", priority=20,
            ),
        ]

    def _get_enemy_info(self, enemy_id: str) -> dict:
        try:
            from knowledge.genshin_knowledge_loader import GenshinKnowledgeBase
            from pathlib import Path
            kb = GenshinKnowledgeBase(Path("knowledge"))
            monster = kb.get_monster(enemy_id)
            if monster is not None:
                return {
                    "monster_id": monster.monster_id,
                    "name": monster.name,
                    "element": monster.element,
                    "weaknesses": monster.weaknesses,
                    "danger_signals": monster.danger_signals,
                }
        except Exception:
            pass
        return {}

    def _get_weaknesses_from_kb(self, enemy_id: str) -> list[str]:
        info = self._get_enemy_info(enemy_id)
        return info.get("weaknesses", [])

    def generate_llm_prompt(
        self, team: list[str], enemy: str, playbook: CombatPlaybook
    ) -> str:
        chain_desc = ", ".join(playbook.elemental_chain) if playbook.elemental_chain else "none"
        rotation_lines: list[str] = []
        for act in playbook.default_rotation:
            parts = [f"  - {act.action}(char={act.character}"]
            if act.repeat > 1:
                parts.append(f"repeat={act.repeat}")
            if act.condition:
                parts.append(f"if={act.condition}")
            parts.append(f"priority={act.priority})")
            rotation_lines.append(" ".join(parts))
        rotation_text = "\n".join(rotation_lines)

        trigger_lines: list[str] = []
        for trig in playbook.priority_triggers:
            trigger_lines.append(
                f"  - [{trig.priority:02d}] {trig.condition} -> {trig.action}"
                f"{' (interrupt)' if trig.interrupt else ''}"
            )
        trigger_text = "\n".join(trigger_lines)

        return (
            f"You are a Genshin Impact combat strategist.\n"
            f"Team: {', '.join(team)}\n"
            f"Enemy: {enemy}\n"
            f"Planned reaction chain: {chain_desc}\n"
            f"Default rotation:\n{rotation_text}\n"
            f"Priority triggers:\n{trigger_text}\n"
            f"Fallback: target_lost={playbook.fallback.on_target_lost}, "
            f"combo_break={playbook.fallback.on_combo_break}, "
            f"timeout={playbook.fallback.on_timeout}\n"
            f"Optimize the rotation for maximum reaction uptime and damage."
        )

    def _find_reaction_by_name(self, name: str):
        for rxn in self._reactions.REACTIONS:
            if rxn.name == name:
                return rxn
        return None

    @staticmethod
    def _slot_for_element(element: str, team_elements: list[str]) -> int:
        if element in team_elements:
            return _ELEMENT_TO_SLOT.get(element, team_elements.index(element) + 1)
        return _ELEMENT_TO_SLOT.get(element, 1)
