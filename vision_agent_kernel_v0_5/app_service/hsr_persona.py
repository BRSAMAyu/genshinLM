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


class HSRPersona:
    """Honkai: Star Rail companion persona — 星穹列车组风格."""

    EVENT_MAP: dict[str, list[EventMapping]] = {
        # === Combat Waves ===
        "WAVE_START": [
            EventMapping("WAVE_START", "新的波次来了，准备迎战！", "excited", "注意弱点击破", 40),
            EventMapping("WAVE_START", "敌人增援到了，别大意！", "calm", "", 40),
        ],
        "WAVE_CLEAR": [
            EventMapping("WAVE_CLEAR", "这波清理完毕！继续保持！", "happy", "", 30),
            EventMapping("WAVE_CLEAR", "漂亮！下一波还远吗？", "excited", "", 30),
        ],
        "COMBAT_VICTORY": [
            EventMapping("COMBAT_VICTORY", "战斗胜利！开拓者果然厉害！", "happy", "", 20),
            EventMapping("COMBAT_VICTORY", "完美收官！列车组又立一功！", "excited", "", 20),
        ],
        "COMBAT_DIFFICULT": [
            EventMapping("COMBAT_DIFFICULT", "这波有点棘手……注意技能点分配！", "worried", "建议保留SP给关键角色", 30),
            EventMapping("COMBAT_DIFFICULT", "敌人很强，合理利用弱点击破！", "worried", "优先攻击弱点敌人", 25),
        ],
        "WEAKNESS_BROKEN": [
            EventMapping("WEAKNESS_BROKEN", "弱点击破成功！趁现在输出！", "excited", "击破后追加伤害", 30),
            EventMapping("WEAKNESS_BROKEN", "韧性条打空了！全力进攻！", "happy", "", 30),
        ],

        # === SP Management ===
        "SP_LOW": [
            EventMapping("SP_LOW", "技能点不够了！先用普攻攒一攒", "worried", "使用普攻恢复SP", 35),
            EventMapping("SP_LOW", "SP紧张，先存点再爆发吧", "calm", "", 35),
        ],
        "HP_LOW": [
            EventMapping("HP_LOW", "血量告急！丰饶角色该出手了", "worried", "建议使用治疗技能", 10),
            EventMapping("HP_LOW", "危险！快切治疗或者开大招保命！", "worried", "HP < 30%", 5),
        ],

        # === Navigation ===
        "OBSTACLE_BLOCKING": [
            EventMapping("OBSTACLE_BLOCKING", "路被挡住了，换条路线吧", "calm", "", 50),
            EventMapping("OBSTACLE_BLOCKING", "前面过不去，绕个路试试？", "calm", "", 50),
        ],
        "ARRIVED_AT_DESTINATION": [
            EventMapping("ARRIVED_AT_DESTINATION", "到达目的地！开始探索吧～", "excited", "", 30),
            EventMapping("ARRIVED_AT_DESTINATION", "到了到了！看看这里有什么", "happy", "", 30),
        ],

        # === Simulated Universe ===
        "BLESSING_CHOSEN": [
            EventMapping("BLESSING_CHOSEN", "新祝福到手了！这次运气不错", "happy", "", 40),
            EventMapping("BLESSING_CHOSEN", "好的祝福选择！继续前进", "calm", "", 40),
        ],
        "CURIO_ACQUIRED": [
            EventMapping("CURIO_ACQUIRED", "获得新奇物了！不知道有什么效果", "surprised", "", 40),
            EventMapping("CURIO_ACQUIRED", "奇物入手，小心副作用哦", "calm", "检查奇物效果", 40),
        ],
        "DOMAIN_ENTER": [
            EventMapping("DOMAIN_ENTER", "进入新区域！保持警惕", "calm", "", 50),
            EventMapping("DOMAIN_ENTER", "新的领域……不知道前方有什么", "worried", "", 50),
        ],

        # === System ===
        "REWARD_CLAIMED": [
            EventMapping("REWARD_CLAIMED", "奖励到手！又是收获满满的一天", "happy", "", 40),
            EventMapping("REWARD_CLAIMED", "领取成功！记得检查背包", "happy", "", 40),
        ],
        "DAILY_COMPLETE": [
            EventMapping("DAILY_COMPLETE", "今天的任务都完成了！辛苦开拓者！", "excited", "", 20),
        ],
        "STAMINA_FULL": [
            EventMapping("STAMINA_FULL", "开拓者，开拓力满了！别浪费哦", "happy", "建议刷模拟宇宙或副本", 60),
        ],
        "TARGET_LOST": [
            EventMapping("TARGET_LOST", "目标消失了……让我重新定位", "worried", "", 50),
            EventMapping("TARGET_LOST", "咦？敌人去哪了？", "surprised", "", 50),
        ],
        "LOADING_WAIT": [
            EventMapping("LOADING_WAIT", "跃迁中……稍等一下", "calm", "", 70),
        ],
        "IDLE_TOO_LONG": [
            EventMapping("IDLE_TOO_LONG", "开拓者？列车马上就要开了哦", "calm", "", 80),
            EventMapping("IDLE_TOO_LONG", "嗯？在发呆吗？要不要继续？", "calm", "", 80),
        ],
        "ERROR_OCCURRED": [
            EventMapping("ERROR_OCCURRED", "出状况了……让我重新调整一下", "worried", "系统异常，请检查", 10),
        ],
    }

    def __init__(self) -> None:
        self._last_event_time: dict[str, float] = {}
        self._variant_idx: dict[str, int] = {}

    def on_event(self, event: str, context: dict | None = None) -> PersonaResponse | None:
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
        sp_level: int,
        hp_ratios: list[float],
    ) -> PersonaResponse | None:
        if hp_ratios and min(hp_ratios) < 0.3:
            return self.on_event("HP_LOW")
        if sp_level <= 1:
            return self.on_event("SP_LOW")
        return None

    def format_with_context(self, template: str, context: dict) -> str:
        try:
            return template.format(**context)
        except KeyError:
            return template

    def _check_cooldown(self, event: str, now: float, cooldown_ms: int) -> bool:
        last = self._last_event_time.get(event)
        if last is None:
            return True
        elapsed_ms = (now - last) * 1000.0
        return elapsed_ms >= cooldown_ms

    def _select_variant(self, variants: list[EventMapping]) -> EventMapping:
        event = variants[0].event
        idx = self._variant_idx.get(event, 0)
        selected = variants[idx % len(variants)]
        self._variant_idx[event] = idx + 1
        return selected
