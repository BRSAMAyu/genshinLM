from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonaResponse:
    text: str
    emotion: str
    suggestion: str = ""
    priority: int = 50


@dataclass(frozen=True, slots=True)
class EventMapping:
    event: str
    text: str
    emotion: str
    suggestion: str
    priority: int
    cooldown_ms: int = 5000


class GenshinPersona:
    """Genshin Impact companion persona that converts system events into character dialogue."""

    EVENT_MAP: dict[str, list[EventMapping]] = {
        # === Target Tracking ===
        "TARGET_LOST": [
            EventMapping("TARGET_LOST", "咦？怪物跑哪去了？让我找找……", "worried", "正在重新搜索目标", 50),
            EventMapping("TARGET_LOST", "目标消失了！别急，我帮你找！", "surprised", "", 50),
        ],
        "TARGET_FOUND": [
            EventMapping("TARGET_FOUND", "找到了！就在那边！", "excited", "", 40),
            EventMapping("TARGET_FOUND", "看，目标出现了！准备战斗！", "happy", "", 40),
        ],
        "TARGET_DEFEATED": [
            EventMapping("TARGET_DEFEATED", "太棒了！轻松搞定！", "happy", "", 30),
            EventMapping("TARGET_DEFEATED", "漂亮！下一个是谁？", "excited", "", 30),
        ],

        # === Combat ===
        "COMBAT_START": [
            EventMapping("COMBAT_START", "发现敌人！准备好了吗？", "excited", "建议先上元素附着", 40),
            EventMapping("COMBAT_START", "战斗开始！注意走位哦～", "happy", "", 40),
        ],
        "COMBAT_VICTORY": [
            EventMapping("COMBAT_VICTORY", "胜利！今天的旅行者也很强呢！", "happy", "", 20),
            EventMapping("COMBAT_VICTORY", "全部解决！完美！", "excited", "", 20),
        ],
        "COMBAT_DIFFICULT": [
            EventMapping("COMBAT_DIFFICULT", "这个敌人很强……要小心！", "worried", "建议切换到克制元素角色", 30),
            EventMapping("COMBAT_DIFFICULT", "Boss来了！集中注意力！", "worried", "注意躲避攻击", 25),
        ],

        # === Danger ===
        "DANGER_DODGE_SUCCESS": [
            EventMapping("DANGER_DODGE_SUCCESS", "好险！幸好躲开了！", "surprised", "", 30),
            EventMapping("DANGER_DODGE_SUCCESS", "闪避成功！反应不错嘛～", "happy", "", 30),
        ],
        "DANGER_HIT": [
            EventMapping("DANGER_HIT", "呜……被打到了……我们更小心一点吧。", "worried", "血量下降了，考虑使用护盾或治疗", 20),
            EventMapping("DANGER_HIT", "小心！血量掉了不少！", "worried", "", 20),
        ],
        "LOW_HP": [
            EventMapping("LOW_HP", "血量不多了！要切换角色吗？", "worried", "建议切换到满血角色", 10),
            EventMapping("LOW_HP", "危险！快切人或者吃食物！", "worried", "HP < 30%", 5),
        ],

        # === Collection ===
        "COLLECTION_SUCCESS": [
            EventMapping("COLLECTION_SUCCESS", "又收集到材料了！还差一些呢～", "happy", "", 40),
            EventMapping("COLLECTION_SUCCESS", "收获满满！继续加油！", "happy", "", 40),
        ],
        "COLLECTION_COMPLETE": [
            EventMapping("COLLECTION_COMPLETE", "太好了！采集任务完成了！", "excited", "可以前往下一个地点了", 20),
            EventMapping("COLLECTION_COMPLETE", "今天的采集目标达成！辛苦了！", "happy", "", 20),
        ],
        "COLLECTION_FAILED": [
            EventMapping("COLLECTION_FAILED", "啊，没采集成功……再试一次吧！", "worried", "", 40),
            EventMapping("COLLECTION_FAILED", "失败了……可能是距离太远？", "calm", "尝试靠近一些", 40),
        ],

        # === Navigation ===
        "OBSTACLE_BLOCKING": [
            EventMapping("OBSTACLE_BLOCKING", "前面好像过不去，我们绕路吧～", "calm", "", 50),
            EventMapping("OBSTACLE_BLOCKING", "路被挡住了，换个方向试试？", "calm", "", 50),
        ],
        "ARRIVED_AT_DESTINATION": [
            EventMapping("ARRIVED_AT_DESTINATION", "到了！就是这里！", "excited", "", 30),
            EventMapping("ARRIVED_AT_DESTINATION", "到达目的地！开始工作吧～", "happy", "", 30),
        ],

        # === Skill/System ===
        "SKILL_FAILED": [
            EventMapping("SKILL_FAILED", "啊，技能没打中，调整一下！", "worried", "", 45),
            EventMapping("SKILL_FAILED", "放空了……没关系，再来！", "calm", "", 45),
        ],
        "BOSS_PHASE_CHANGE": [
            EventMapping("BOSS_PHASE_CHANGE", "Boss变强了！集中注意力！", "worried", "注意新的攻击模式", 15),
            EventMapping("BOSS_PHASE_CHANGE", "阶段转换了！不要掉以轻心！", "worried", "", 15),
        ],
        "RESIN_FULL": [
            EventMapping("RESIN_FULL", "旅行者，树脂满了哦！不要浪费～", "happy", "建议刷圣遗物本或地脉", 60),
        ],
        "DAILY_COMPLETE": [
            EventMapping("DAILY_COMPLETE", "今天的委托都完成了！辛苦了！", "excited", "记得去凯瑟琳领奖励", 20),
        ],
        "STAMINA_LOW": [
            EventMapping("STAMINA_LOW", "体力快没了……歇一歇吧", "worried", "停止冲刺", 35),
        ],
        "TELEPORT_START": [
            EventMapping("TELEPORT_START", "传送中……等一下哦～", "calm", "", 50),
        ],
        "LOADING_WAIT": [
            EventMapping("LOADING_WAIT", "加载中……聊聊天吧？", "calm", "", 70),
        ],

        # === Misc ===
        "IDLE_TOO_LONG": [
            EventMapping("IDLE_TOO_LONG", "旅行者？还在吗？", "worried", "", 80),
            EventMapping("IDLE_TOO_LONG", "嗯……要继续吗？", "calm", "", 80),
        ],
        "ERROR_OCCURRED": [
            EventMapping("ERROR_OCCURRED", "出问题了……让我重新整理一下", "worried", "系统错误，请检查", 10),
        ],
    }

    def __init__(self) -> None:
        self._last_event_time: dict[str, float] = {}
        self._personality: str = "friendly"
        self._name: str = "帕伊蒙"
        self._variant_idx: dict[str, int] = {}

    def on_event(self, event: str, context: dict | None = None) -> PersonaResponse | None:
        """Convert a system event into a persona response."""
        variants = self.EVENT_MAP.get(event)
        if not variants:
            return None

        mapping = self._select_variant(variants)
        now = time.perf_counter()

        if not self._check_cooldown(event, now, mapping.cooldown_ms):
            return None

        self._last_event_time[event] = now

        text = mapping.text
        if context:
            text = self.format_with_context(text, context)

        return PersonaResponse(
            text=text,
            emotion=mapping.emotion,
            suggestion=mapping.suggestion,
            priority=mapping.priority,
        )

    def on_combat_state(
        self,
        danger_score: float,
        hp_ratios: list[float],
        cooldown_states: dict[str, bool],
    ) -> PersonaResponse | None:
        """Generate response based on real-time combat state."""
        if hp_ratios and min(hp_ratios) < 0.3:
            return self.on_event("LOW_HP")

        if danger_score > 0.7:
            return self.on_event("COMBAT_DIFFICULT")

        if danger_score > 0.4:
            return self.on_event("DANGER_HIT")

        return None

    def format_with_context(self, template: str, context: dict) -> str:
        """Format a response template with context variables."""
        try:
            return template.format(**context)
        except KeyError:
            return template

    def _check_cooldown(self, event: str, now: float, cooldown_ms: int) -> bool:
        """Check if event is on cooldown. Returns True if can fire."""
        last = self._last_event_time.get(event)
        if last is None:
            return True
        elapsed_ms = (now - last) * 1000.0
        return elapsed_ms >= cooldown_ms

    def _select_variant(self, variants: list[EventMapping]) -> EventMapping:
        """Round-robin variant selection."""
        event = variants[0].event
        idx = self._variant_idx.get(event, 0)
        selected = variants[idx % len(variants)]
        self._variant_idx[event] = idx + 1
        return selected
