from __future__ import annotations

from persona.persona_profile import PersonaRegistry


class EventTranslator:
    def __init__(self, registry: PersonaRegistry) -> None:
        self._registry = registry

    def translate(self, event_code: str, persona_id: str = "default_companion") -> str:
        profile = self._registry.get(persona_id)
        return profile.event_templates.get(event_code, f"收到事件 {event_code}，我会按安全策略处理。")

    def emotion(self, event_code: str, persona_id: str = "default_companion") -> str:
        profile = self._registry.get(persona_id)
        return profile.emotion_map.get(event_code, "normal")
