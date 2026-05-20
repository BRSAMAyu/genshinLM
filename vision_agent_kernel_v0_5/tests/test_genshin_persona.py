from __future__ import annotations

import time

from app_service.genshin_persona import EventMapping, GenshinPersona, PersonaResponse


class TestGenshinPersona:
    def setup_method(self) -> None:
        self.p = GenshinPersona()

    def test_target_found_returns_response(self) -> None:
        resp = self.p.on_event("TARGET_FOUND")
        assert resp is not None
        assert isinstance(resp, PersonaResponse)
        assert resp.text != ""
        assert resp.emotion in ("excited", "happy")

    def test_combat_victory_happy(self) -> None:
        resp = self.p.on_event("COMBAT_VICTORY")
        assert resp is not None
        assert resp.emotion == "happy" or resp.emotion == "excited"

    def test_unknown_event_returns_none(self) -> None:
        resp = self.p.on_event("NONEXISTENT_EVENT_42")
        assert resp is None

    def test_context_formatting(self) -> None:
        template = "收集到了{item_name}！还差{remaining}个。"
        result = self.p.format_with_context(template, {"item_name": "绝云椒椒", "remaining": 3})
        assert result == "收集到了绝云椒椒！还差3个。"

    def test_cooldown_prevents_repeat(self) -> None:
        resp1 = self.p.on_event("TARGET_FOUND")
        assert resp1 is not None
        resp2 = self.p.on_event("TARGET_FOUND")
        assert resp2 is None

    def test_low_hp_triggers_response(self) -> None:
        resp = self.p.on_combat_state(danger_score=0.1, hp_ratios=[0.2, 0.8], cooldown_states={})
        assert resp is not None
        assert resp.emotion == "worried"

    def test_danger_hit_high_priority(self) -> None:
        mappings = GenshinPersona.EVENT_MAP["DANGER_HIT"]
        priorities = [m.priority for m in mappings]
        assert all(p <= 25 for p in priorities)

    def test_idle_event_exists(self) -> None:
        assert "IDLE_TOO_LONG" in GenshinPersona.EVENT_MAP
        mappings = GenshinPersona.EVENT_MAP["IDLE_TOO_LONG"]
        assert len(mappings) >= 1

    def test_on_combat_state_danger(self) -> None:
        resp = self.p.on_combat_state(danger_score=0.8, hp_ratios=[1.0], cooldown_states={})
        assert resp is not None

    def test_on_combat_state_safe(self) -> None:
        resp = self.p.on_combat_state(danger_score=0.0, hp_ratios=[1.0, 1.0], cooldown_states={})
        assert resp is None

    def test_event_map_completeness(self) -> None:
        expected = [
            "TARGET_LOST", "TARGET_FOUND", "TARGET_DEFEATED",
            "COMBAT_START", "COMBAT_VICTORY", "COMBAT_DIFFICULT",
            "DANGER_DODGE_SUCCESS", "DANGER_HIT", "LOW_HP",
            "COLLECTION_SUCCESS", "COLLECTION_COMPLETE", "COLLECTION_FAILED",
            "OBSTACLE_BLOCKING", "ARRIVED_AT_DESTINATION",
            "SKILL_FAILED", "BOSS_PHASE_CHANGE", "RESIN_FULL",
            "DAILY_COMPLETE", "STAMINA_LOW", "TELEPORT_START",
            "LOADING_WAIT", "IDLE_TOO_LONG", "ERROR_OCCURRED",
        ]
        for event in expected:
            assert event in GenshinPersona.EVENT_MAP, f"Missing event: {event}"
        assert len(GenshinPersona.EVENT_MAP) >= 15

    def test_variants_provide_variety(self) -> None:
        mappings = GenshinPersona.EVENT_MAP["TARGET_FOUND"]
        assert len(mappings) >= 2
        texts = {m.text for m in mappings}
        assert len(texts) == len(mappings)

    def test_cooldown_expires_allows_repeat(self) -> None:
        resp1 = self.p.on_event("TARGET_DEFEATED")
        assert resp1 is not None
        self.p._last_event_time["TARGET_DEFEATED"] = time.perf_counter() - 10.0
        resp2 = self.p.on_event("TARGET_DEFEATED")
        assert resp2 is not None

    def test_persona_response_frozen(self) -> None:
        resp = PersonaResponse(text="test", emotion="happy")
        try:
            resp.text = "modified"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_event_mapping_frozen(self) -> None:
        em = EventMapping(event="X", text="t", emotion="e", suggestion="s", priority=1)
        try:
            em.event = "Y"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_format_with_context_missing_key(self) -> None:
        result = self.p.format_with_context("没有占位符的文本", {"unused": 1})
        assert result == "没有占位符的文本"

    def test_on_combat_state_danger_hit_threshold(self) -> None:
        resp = self.p.on_combat_state(danger_score=0.5, hp_ratios=[0.9], cooldown_states={})
        assert resp is not None

    def test_variant_round_robin(self) -> None:
        variants = GenshinPersona.EVENT_MAP["TARGET_FOUND"]
        if len(variants) < 2:
            return
        # Burn cooldown by backdating
        texts: list[str] = []
        for _ in range(4):
            self.p._last_event_time["TARGET_FOUND"] = time.perf_counter() - 10.0
            resp = self.p.on_event("TARGET_FOUND")
            assert resp is not None
            texts.append(resp.text)
        assert texts[0] != texts[1] or len(set(texts)) > 1
