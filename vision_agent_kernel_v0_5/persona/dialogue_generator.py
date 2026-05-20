from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from persona.event_translator import EventTranslator


@dataclass(frozen=True, slots=True)
class DialogueLine:
    message: str
    overlay_state: str
    emotion: str


class DialogueGenerator:
    def __init__(self, translator: EventTranslator) -> None:
        self._translator = translator

    def generate(self, event_code: str, payload: dict[str, Any] | None = None, persona_id: str = "default_companion") -> DialogueLine:
        del payload
        state = {
            "TARGET_LOST": "遇到问题",
            "NO_TASK_PROGRESS": "思考中",
            "RECOVERY_STARTED": "执行中",
            "SKILL_TIMEOUT": "遇到问题",
            "TASK_COMPLETE": "完成",
            "FOCUS_LOST": "暂停",
            "EMERGENCY_STOP": "暂停",
            "DODGE_REFLEX": "执行中",
        }.get(event_code, "观察中")
        emotion = self._translator.emotion(event_code, persona_id)
        return DialogueLine(message=self._translator.translate(event_code, persona_id), overlay_state=state, emotion=emotion)
