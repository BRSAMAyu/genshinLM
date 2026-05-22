from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from planning.screen_state_claim import (
    ClaimSource,
    PlayerStatusClaim,
    ScreenStateClaim,
    ScreenStateKind,
    UIElementClaim,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VLMOutput:
    screen_state: str
    player_status: dict[str, str]
    visible_objects: list[dict[str, str]]
    ui_elements: dict[str, str]
    scene_description: str
    suggested_action: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class ClassifierOutput:
    screen_state: str
    confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class OcrOutput:
    text: str
    confidence: float
    bbox_norm: tuple[float, float, float, float]
    source: str


class ScreenStateClaimBuilder:
    """Fuses VLM, OCR, and classifier outputs into a unified ScreenStateClaim."""

    def build(
        self,
        game_id: str,
        frame_id: int,
        vlm: VLMOutput | None = None,
        classifier: ClassifierOutput | None = None,
        ocr_results: list[OcrOutput] | None = None,
    ) -> ScreenStateClaim:
        screen_state = self._resolve_screen_state(vlm, classifier)
        confidence = self._resolve_confidence(vlm, classifier)
        source = self._resolve_source(vlm, classifier)
        ui_elements = self._build_ui_elements(vlm, ocr_results)
        player_status = self._build_player_status(vlm)
        visible_objects = tuple(vlm.visible_objects) if vlm else ()
        interaction_prompt = self._extract_interaction_prompt(vlm, ocr_results)
        scene_description = vlm.scene_description if vlm else ""
        raw_vlm = vlm.raw_text if vlm else ""
        raw_ocr = tuple(r.text for r in (ocr_results or []))

        return ScreenStateClaim(
            game_id=game_id,
            screen_state=screen_state,
            confidence=confidence,
            source=source,
            ui_elements=tuple(ui_elements),
            player_status=player_status,
            visible_objects=visible_objects,
            interaction_prompt=interaction_prompt,
            scene_description=scene_description,
            frame_id=frame_id,
            timestamp=time.time(),
            raw_vlm_text=raw_vlm,
            raw_ocr_texts=raw_ocr,
        )

    @staticmethod
    def _resolve_screen_state(vlm: VLMOutput | None, classifier: ClassifierOutput | None) -> ScreenStateKind:
        candidates: list[str] = []
        if classifier:
            candidates.append(classifier.screen_state)
        if vlm:
            candidates.append(vlm.screen_state)
        valid_states: set[str] = {
            "overworld", "combat", "turn_based_combat", "dialog", "menu",
            "map", "loading", "inventory", "shop", "quest_log",
            "reward_screen", "boss_fight", "cutscene", "unknown",
        }
        for c in candidates:
            if c in valid_states:
                return c  # type: ignore[return-value]
        if candidates:
            normalized = candidates[0].lower().replace(" ", "_")
            if normalized in valid_states:
                return normalized  # type: ignore[return-value]
        return "unknown"

    @staticmethod
    def _resolve_confidence(vlm: VLMOutput | None, classifier: ClassifierOutput | None) -> float:
        if vlm and classifier:
            return 0.6 * classifier.confidence + 0.4 * 0.75
        if classifier:
            return classifier.confidence
        if vlm:
            return 0.75
        return 0.3

    @staticmethod
    def _resolve_source(vlm: VLMOutput | None, classifier: ClassifierOutput | None) -> ClaimSource:
        if vlm and classifier:
            return "hybrid"
        if vlm:
            return "vlm"
        if classifier:
            return "classifier"
        return "unknown"

    @staticmethod
    def _build_ui_elements(
        vlm: VLMOutput | None,
        ocr_results: list[OcrOutput] | None,
    ) -> list[UIElementClaim]:
        elements: list[UIElementClaim] = []
        if vlm and vlm.ui_elements:
            for i, (key, value) in enumerate(vlm.ui_elements.items()):
                if not value or value == "null":
                    continue
                role = _infer_role(key)
                elements.append(UIElementClaim(
                    element_id=f"vlm:{key}:{i}",
                    role=role,
                    text=value,
                    bbox_norm=(0.0, 0.0, 0.0, 0.0),
                    confidence=0.7,
                    source="vlm",
                    clickable=role in ("button", "dialog_option", "menu_item"),
                ))
        if ocr_results:
            for i, ocr in enumerate(ocr_results):
                if ocr.confidence < 0.5:
                    continue
                text = ocr.text.strip()
                if len(text) < 2:
                    continue
                role = _infer_role_from_text(text)
                elements.append(UIElementClaim(
                    element_id=f"ocr:{i}",
                    role=role,
                    text=text,
                    bbox_norm=ocr.bbox_norm,
                    confidence=ocr.confidence,
                    source=ocr.source,
                    clickable=role in ("button", "dialog_option", "menu_item", "list_item"),
                ))
        return elements

    @staticmethod
    def _build_player_status(vlm: VLMOutput | None) -> PlayerStatusClaim:
        if not vlm:
            return PlayerStatusClaim()
        ps = vlm.player_status
        health_pct = None
        if "health" in ps:
            h = ps["health"].lower()
            if "full" in h:
                health_pct = 100.0
            elif "damaged" in h:
                health_pct = 60.0
            elif "critical" in h:
                health_pct = 20.0
        sp = None
        if "skill_points" in ps:
            try:
                sp = int(ps["skill_points"])
            except (ValueError, TypeError):
                pass
        return PlayerStatusClaim(
            health_pct=health_pct,
            skill_points=sp,
            position=ps.get("position_in_frame", "unknown"),
        )

    @staticmethod
    def _extract_interaction_prompt(
        vlm: VLMOutput | None,
        ocr_results: list[OcrOutput] | None,
    ) -> str:
        if vlm and vlm.ui_elements:
            prompt = vlm.ui_elements.get("interaction_prompt", "")
            if prompt and prompt != "null":
                return prompt
        if ocr_results:
            for ocr in ocr_results:
                t = ocr.text.lower()
                if any(kw in t for kw in ("talk", "interact", "f -", "按 f", "按f", "press", "交互", "互动", "对话")):
                    return ocr.text
                if any(kw in t for kw in ("talk", "interact", "f -", "对话", "交互", "按 f", "press")):
                    return ocr.text
        return ""


def _infer_role(key: str) -> str:
    k = key.lower()
    if "button" in k or "btn" in k:
        return "button"
    if "prompt" in k:
        return "interaction_prompt"
    if "quest" in k:
        return "quest_text"
    if "notification" in k or "toast" in k:
        return "notification"
    if "dialog" in k or "option" in k:
        return "dialog_option"
    return "text"


def _infer_role_from_text(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("领取", "claim", "确认", "confirm", "确定", "ok", "开始", "start", "接受", "accept")):
        return "button"
    if any(w in t for w in ("f -", "按 f", "按f", "press", "交互", "互动", "interact", "talk", "对话")):
        return "interaction_prompt"
    if any(w in t for w in ("奖励", "reward", "奖励已领取", "已完成", "领取成功", "获得")):
        return "notification"
    if any(w in t for w in ("委托", "任务", "quest", "mission", "每日", "追踪")):
        return "quest_text"
    if any(w in t for w in ("领取", "claim", "确认", "confirm", "确定", "ok", "开始", "start", "接受", "accept")):
        return "button"
    if any(w in t for w in ("f -", "按 f", "press", "交互", "interact", "talk", "对话")):
        return "interaction_prompt"
    if any(w in t for w in ("奖励", "reward", "奖励已领取", "已完成")):
        return "notification"
    if any(w in t for w in ("委托", "任务", "quest", "mission", "每日")):
        return "quest_text"
    return "text"
