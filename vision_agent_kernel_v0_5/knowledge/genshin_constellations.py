"""Character constellation system (R-31).

Provides constellation data and evaluation for F2P-accessible characters.
Constellations can significantly change a character power and playstyle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Constellation data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConstellationBenefit:
    level: int
    name: str
    description: str
    power_impact: float
    priority: int


@dataclass(frozen=True, slots=True)
class CharacterConstellation:
    character_id: str
    character_name: str
    constellation_level: int = 0
    benefits: tuple[ConstellationBenefit, ...] = field(default_factory=())
    recommended_saving: int = 0


# F2P character constellation data (Chinese names from game)
BENNETT_BENEFITS = (
    ConstellationBenefit(1, "热情不减", "攻击力加成从30%提升至40%", 0.15, 1),
    ConstellationBenefit(2, "燃烧的意志", "消弭冷却的体力要求降低", 0.10, 2),
    ConstellationBenefit(3, "引来炽火", "妙火炉灶的技能等级提高3级", 0.10, 3),
    ConstellationBenefit(4, "火锅达成", "命中火史莱姆时,额外产生3个火元素微粒", 0.05, 4),
    ConstellationBenefit(5, "你也可以", "热情注入的技能等级提高3级", 0.10, 5),
    ConstellationBenefit(6, "魔火炽心", "危险领域对范围内所有玩家生效", 0.25, 6),
)

XINGQIU_BENEFITS = (
    ConstellationBenefit(1, "生水要心", "雨裁的水元素抗性提升15%", 0.10, 1),
    ConstellationBenefit(2, "雨滞坎离", "雨裁持续期间,每2秒清除一次雨裁的冷却", 0.15, 2),
    ConstellationBenefit(3, "升到元满", "倾力一击的技能等级提高3级", 0.10, 3),
    ConstellationBenefit(4, "先发制人", "雨裁的持续时间延长3秒", 0.10, 4),
    ConstellationBenefit(5, "斩雨愈心", "倾力一击的技能等级提高3级", 0.10, 5),
    ConstellationBenefit(6, "虚亨真满", "雨裁对受到蒸发影响的敌人造成伤害时,额外产生元素能量", 0.20, 6),
)

XIANGLING_BENEFITS = (
    ConstellationBenefit(1, "外肉内骨", "锅巴的攻击范围扩大15%", 0.05, 1),
    ConstellationBenefit(2, "旺上流温", "锅巴的辣椒使敌人受到的燃烧伤害提升", 0.15, 2),
    ConstellationBenefit(3, "大波胜过", "旋火轮的技能等级提高3级", 0.15, 3),
    ConstellationBenefit(4, "火史莱姆的怒火", "旋火轮的持续时间延长40%", 0.10, 4),
    ConstellationBenefit(5, "油炸警告", "锅巴的技能等级提高3级", 0.15, 5),
    ConstellationBenefit(6, "吞地产火", "所有元素伤害提升15%", 0.20, 6),
)

FISCHL_BENEFITS = (
    ConstellationBenefit(1, "噬星之渊", "奥兹在场时,会额外攻击一名敌人", 0.10, 1),
    ConstellationBenefit(2, "堆坏捕者", "落雷的抗打断等级提升,并使敌人受到的雷电伤害降低15%", 0.10, 2),
    ConstellationBenefit(3, "夜蚀鲜辉", "夜行通的技能等级提高3级", 0.15, 3),
    ConstellationBenefit(4, "神圣的新月", "夜行通的雷鸣攻击范围扩大50%", 0.10, 4),
    ConstellationBenefit(5, "苏门之坚", "奥兹的技能等级提高3级", 0.15, 5),
    ConstellationBenefit(6, "莫管夜视", "在夜晚时,队伍中所有角色攻击力提升30%", 0.25, 6),
)

SUCROSE_BENEFITS = (
    ConstellationBenefit(1, "星定冶火", "扩散反应使敌人元素抗性降低的数值,会同时使队伍中所有角色获得20%", 0.10, 1),
    ConstellationBenefit(2, "容系勿怡", "扩散反应的范围扩大15%", 0.10, 2),
    ConstellationBenefit(3, "大鉴乎野", "飓风不住的技能等级提高3级", 0.10, 3),
    ConstellationBenefit(4, "零谐云和", "飓风不住的持续时间延长2秒", 0.10, 4),
    ConstellationBenefit(5, "念动幽预", "飓风不住的技能等级提高3级", 0.10, 5),
    ConstellationBenefit(6, "粗中又细", "扩散反应造成的伤害提升15%", 0.15, 6),
)

CHARACTER_CONSTELLATION_DATA = {
    "bennett": CharacterConstellation("bennett", "Bennett", benefits=BENNETT_BENEFITS, recommended_saving=1),
    "xingqiu": CharacterConstellation("xingqiu", "Xingqiu", benefits=XINGQIU_BENEFITS, recommended_saving=6),
    "xiangling": CharacterConstellation("xiangling", "Xiangling", benefits=XIANGLING_BENEFITS, recommended_saving=4),
    "fischl": CharacterConstellation("fischl", "Fischl", benefits=FISCHL_BENEFITS, recommended_saving=6),
    "sucrose": CharacterConstellation("sucrose", "Sucrose", benefits=SUCROSE_BENEFITS, recommended_saving=1),
}


class ConstellationEvaluator:
    def __init__(self) -> None:
        self._character_data = dict(CHARACTER_CONSTELLATION_DATA)

    def get_constellation(self, character_id: str) -> CharacterConstellation | None:
        return self._character_data.get(character_id.lower())

    def evaluate_constellation_value(self, character_id: str, from_level: int = 0, to_level: int | None = None) -> float:
        constellation = self.get_constellation(character_id)
        if constellation is None:
            return 0.0
        if to_level is None:
            to_level = constellation.recommended_saving
        to_level = min(to_level, 6)
        if from_level >= to_level:
            return 1.0
        total_impact = 0.0
        for benefit in constellation.benefits:
            if from_level < benefit.level <= to_level:
                total_impact += benefit.power_impact
        return min(total_impact, 1.0)

    def recommend_constellation_saving(self, character_id: str, current_level: int = 0) -> dict[str, Any]:
        constellation = self.get_constellation(character_id)
        if constellation is None:
            return {"error": "Character not found"}
        recommendations = []
        for benefit in constellation.benefits:
            if benefit.level > current_level:
                recommendations.append({"level": benefit.level, "name": benefit.name, "power": benefit.power_impact, "priority": benefit.priority})
        recommendations.sort(key=lambda x: x["priority"])
        return {"character_id": character_id, "current": current_level, "target": constellation.recommended_saving, "recs": recommendations}

    def should_save_for_constellation(self, character_id: str, current_c: int, pity: int, guarantee: bool) -> bool:
        constellation = self.get_constellation(character_id)
        if constellation is None or current_c >= constellation.recommended_saving:
            return False
        return self.evaluate_constellation_value(character_id, current_c) >= 0.2 and (pity >= 60 or (pity >= 50 and guarantee))

    def get_best_f2p_constellations(self, characters_with_c: dict[str, int]) -> list[tuple[str, int, float]]:
        results = []
        for char_id, current_c in characters_with_c.items():
            constellation = self.get_constellation(char_id)
            if constellation and current_c < constellation.recommended_saving:
                value = self.evaluate_constellation_value(char_id, current_c)
                results.append((char_id, constellation.recommended_saving, value))
        results.sort(key=lambda x: x[2], reverse=True)
        return results
