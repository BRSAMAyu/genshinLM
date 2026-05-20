from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DomainType(Enum):
    ARTIFACT_DOMAIN = "artifact"
    TALENT_DOMAIN = "talent"
    WEAPON_DOMAIN = "weapon"
    BOSS_DOMAIN = "boss"
    LEYLINE = "leyline"


@dataclass(frozen=True, slots=True)
class DomainInfo:
    domain_id: str
    name: str
    name_en: str
    domain_type: DomainType
    waypoint_id: str
    resin_cost: int
    recommended_elements: list[str]
    region: str


@dataclass(frozen=True, slots=True)
class ResinRunState:
    active: bool
    domain_id: str
    runs_done: int
    runs_planned: int
    resin_used: int
    resin_remaining: int


# Key domains database
DOMAINS: dict[str, DomainInfo] = {
    # Artifact domains
    "midsummer_courtyard": DomainInfo(
        "midsummer_courtyard", "仲夏庭园", "Midsummer Courtyard",
        DomainType.ARTIFACT_DOMAIN, "tp_mondstadt_city", 20, ["electro", "pyro"], "mondstadt",
    ),
    "valley_of_remembrance": DomainInfo(
        "valley_of_remembrance", "铭记之谷", "Valley of Remembrance",
        DomainType.ARTIFACT_DOMAIN, "tp_wolvendom", 20, ["anemo", "cryo"], "mondstadt",
    ),
    "domain_of_blessing_clear_pool": DomainInfo(
        "domain_of_blessing_clear_pool", "芬德尼尔之顶", "Peak of Vindagnyr",
        DomainType.ARTIFACT_DOMAIN, "tp_dragonspine", 20, ["pyro", "hydro"], "mondstadt",
    ),
    # Talent domains
    "forsaken_rift": DomainInfo(
        "forsaken_rift", "忘却之峡", "Forsaken Rift",
        DomainType.TALENT_DOMAIN, "tp_mondstadt_city", 20, ["cryo", "pyro"], "mondstadt",
    ),
    "taishan_mansion": DomainInfo(
        "taishan_mansion", "太山府", "Taishan Mansion",
        DomainType.TALENT_DOMAIN, "tp_liyue_harbor", 20, ["hydro", "pyro"], "liyue",
    ),
    # Boss domains
    "pyro_regisvine_domain": DomainInfo(
        "pyro_regisvine_domain", "爆炎树", "Pyro Regisvine",
        DomainType.BOSS_DOMAIN, "tp_pyro_regisvine", 40, ["hydro", "cryo"], "liyue",
    ),
    "cryo_regisvine_domain": DomainInfo(
        "cryo_regisvine_domain", "急冻树", "Cryo Regisvine",
        DomainType.BOSS_DOMAIN, "tp_cryo_regisvine", 40, ["pyro", "electro"], "mondstadt",
    ),
    # Leyline (blossoms)
    "leyline_mora_mondstadt": DomainInfo(
        "leyline_mora_mondstadt", "藏金之花(蒙德)",
        "Blossom of Wealth (Mondstadt)",
        DomainType.LEYLINE, "tp_mondstadt_city", 20, [], "mondstadt",
    ),
    "leyline_exp_mondstadt": DomainInfo(
        "leyline_exp_mondstadt", "启示之花(蒙德)",
        "Blossom of Revelation (Mondstadt)",
        DomainType.LEYLINE, "tp_mondstadt_city", 20, [], "mondstadt",
    ),
}

_REGEN_MINUTES_PER_RESIN = 8.0


class ResinManager:
    """Manage resin consumption through domain runs."""

    def __init__(self, current_resin: int = 160) -> None:
        self._current_resin = current_resin
        self._max_resin = 160
        self._runs_done = 0

    def plan_resin_usage(self, target_type: str = "auto") -> list[DomainInfo]:
        """Plan which domains to run based on available resin.

        Args:
            target_type: "auto", "artifact", "talent", "boss", "leyline"

        Auto strategy:
        - < 40 resin: Leyline runs (20 each)
        - 40-80 resin: Boss runs (40 each)
        - 80-160 resin: Artifact domain runs (20 each)
        """
        if target_type == "auto":
            return self._auto_plan()

        type_filter = {
            "artifact": DomainType.ARTIFACT_DOMAIN,
            "talent": DomainType.TALENT_DOMAIN,
            "boss": DomainType.BOSS_DOMAIN,
            "leyline": DomainType.LEYLINE,
        }.get(target_type)

        if type_filter is None:
            return []

        return self._plan_by_type(type_filter)

    def _auto_plan(self) -> list[DomainInfo]:
        if self._current_resin < 40:
            return self._plan_by_type(DomainType.LEYLINE)
        if self._current_resin <= 80:
            return self._plan_by_type(DomainType.BOSS_DOMAIN)
        return self._plan_by_type(DomainType.ARTIFACT_DOMAIN)

    def _plan_by_type(self, domain_type: DomainType) -> list[DomainInfo]:
        matching = [d for d in DOMAINS.values() if d.domain_type == domain_type]
        if not matching:
            return []

        cost = matching[0].resin_cost
        runs = self._current_resin // cost
        if runs <= 0:
            return []

        selected = matching[0]
        return [selected] * runs

    def create_run_plan(self, domain: DomainInfo, runs: int = 0) -> list[dict]:
        """Create a detailed run plan for a domain.

        Each run involves:
        1. Navigate to domain
        2. Enter domain
        3. Complete domain (combat)
        4. Claim rewards (use resin)
        5. Check if more runs needed
        """
        if runs <= 0:
            runs = self._current_resin // domain.resin_cost

        plan: list[dict] = []
        for i in range(runs):
            plan.append({
                "step": "navigate",
                "target_waypoint": domain.waypoint_id,
                "domain_id": domain.domain_id,
                "run": i + 1,
            })
            plan.append({
                "step": "enter_domain",
                "domain_id": domain.domain_id,
                "run": i + 1,
            })
            plan.append({
                "step": "complete_domain",
                "domain_type": domain.domain_type.value,
                "run": i + 1,
            })
            plan.append({
                "step": "claim_rewards",
                "resin_cost": domain.resin_cost,
                "run": i + 1,
            })
            plan.append({
                "step": "check_continue",
                "remaining_runs": runs - i - 1,
                "run": i + 1,
            })
        return plan

    def record_run(self, resin_used: int) -> None:
        """Record a completed domain run."""
        self._current_resin = max(0, self._current_resin - resin_used)
        self._runs_done += 1

    @property
    def current_resin(self) -> int:
        return self._current_resin

    @property
    def runs_done(self) -> int:
        return self._runs_done

    def estimate_resin_regen_time(self, target_resin: int) -> float:
        """Estimate hours until resin reaches target.

        Resin regenerates at 8 minutes per 1 resin.
        """
        if self._current_resin >= target_resin:
            return 0.0
        deficit = target_resin - self._current_resin
        return deficit * _REGEN_MINUTES_PER_RESIN / 60.0
