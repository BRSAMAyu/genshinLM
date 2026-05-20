from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PersonaProfile:
    persona_id: str
    name: str
    style: str
    tone: str
    avatar_asset: str
    voice_config: dict[str, Any]
    event_templates: dict[str, str]
    safety_style: str
    technical_detail_level: str
    emotion_map: dict[str, str] = field(default_factory=dict)


DEFAULT_TEMPLATES = {
    "TARGET_LOST": "目标跑出视野啦，我正在重新搜索。",
    "NO_TASK_PROGRESS": "这里好像被挡住了，我换个方向试试。",
    "RECOVERY_STARTED": "我先做一次恢复动作，再继续任务。",
    "SKILL_TIMEOUT": "这个动作没有在预期时间内完成，我会先停下来检查。",
    "TASK_COMPLETE": "任务完成，已经整理好结果。",
    "FOCUS_LOST": "目标窗口失焦了，我先暂停，避免误操作。",
    "EMERGENCY_STOP": "紧急停止已触发，输入已释放。",
    "DODGE_REFLEX": "检测到危险，我先闪避一下。",
}

DEFAULT_EMOTIONS = {
    "TARGET_LOST": "nervous",
    "NO_TASK_PROGRESS": "thinking",
    "RECOVERY_STARTED": "thinking",
    "SKILL_TIMEOUT": "warning",
    "TASK_COMPLETE": "happy",
    "FOCUS_LOST": "warning",
    "EMERGENCY_STOP": "warning",
    "DODGE_REFLEX": "nervous",
}


class PersonaRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._path = root / "configs" / "personas.json"
        if not self._path.exists():
            self._write_defaults()

    def list_profiles(self) -> list[PersonaProfile]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        profiles = []
        changed = False
        for item in data.get("personas", []):
            if "emotion_map" not in item:
                item["emotion_map"] = DEFAULT_EMOTIONS
                changed = True
            profiles.append(PersonaProfile(**item))
        if changed:
            self._path.write_text(json.dumps({"personas": [asdict(profile) for profile in profiles]}, indent=2, ensure_ascii=False), encoding="utf-8")
        return profiles

    def get(self, persona_id: str) -> PersonaProfile:
        for profile in self.list_profiles():
            if profile.persona_id == persona_id:
                return profile
        return self.list_profiles()[0]

    def _write_defaults(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        calm_emotions = {**DEFAULT_EMOTIONS, "TARGET_LOST": "thinking", "DODGE_REFLEX": "warning"}
        developer_emotions = {**DEFAULT_EMOTIONS, "TARGET_LOST": "thinking", "DODGE_REFLEX": "warning"}
        profiles = [
            PersonaProfile("default_companion", "Aurora", "balanced", "warm", "assets/avatar/default_companion.png", {}, DEFAULT_TEMPLATES, "friendly_safe", "medium", DEFAULT_EMOTIONS),
            PersonaProfile("cheerful_guide", "Mira", "cheerful_guide", "bright", "assets/avatar/cheerful_guide.png", {}, DEFAULT_TEMPLATES, "friendly_safe", "low", DEFAULT_EMOTIONS),
            PersonaProfile("calm_operator", "Sera", "calm_operator", "calm", "assets/avatar/calm_operator.png", {}, DEFAULT_TEMPLATES, "precise_safe", "high", calm_emotions),
            PersonaProfile("healing_partner", "Nagi", "healing_partner", "soft", "assets/avatar/healing_partner.png", {}, DEFAULT_TEMPLATES, "gentle_safe", "low", DEFAULT_EMOTIONS),
            PersonaProfile("developer_mode", "Dev Console", "developer_mode", "technical", "assets/avatar/developer_mode.png", {}, DEFAULT_TEMPLATES, "technical_safe", "high", developer_emotions),
        ]
        self._path.write_text(json.dumps({"personas": [asdict(profile) for profile in profiles]}, indent=2, ensure_ascii=False), encoding="utf-8")
