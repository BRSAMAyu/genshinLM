"""Tests for GameKnowledgeStore."""
from __future__ import annotations

from learning.game_knowledge_store import GameKnowledgeStore, KnowledgeQuery


class TestGameKnowledgeStore:
    def test_store_and_get(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        fid = store.store("npc", "Amber", "location", "Mondstadt tower", game_id="genshin")
        assert fid
        fact = store.get("npc", "Amber", "location", game_id="genshin")
        assert fact is not None
        assert fact.value == "Mondstadt tower"

    def test_query_by_category(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("enemy", "Hilichurl", "weakness", "pyro", game_id="genshin")
        store.store("enemy", "Slime", "weakness", "depends on element", game_id="genshin")
        store.store("npc", "Katheryne", "location", "Adventurers Guild", game_id="genshin")
        results = store.query(KnowledgeQuery(category="enemy"))
        assert len(results) == 2

    def test_query_by_confidence(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("item", "Sweet Flower", "type", "material", confidence=0.9)
        store.store("item", "Apple", "type", "food", confidence=0.3)
        results = store.query(KnowledgeQuery(min_confidence=0.5))
        assert len(results) == 1
        assert results[0].subject == "Sweet Flower"

    def test_upsert_replaces(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("npc", "Paimon", "role", "guide", game_id="genshin")
        store.store("npc", "Paimon", "role", "companion", game_id="genshin", confidence=0.95)
        fact = store.get("npc", "Paimon", "role", game_id="genshin")
        assert fact is not None
        assert fact.value == "companion"
        assert fact.confidence == 0.95

    def test_categories(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("npc", "A", "x", "1")
        store.store("enemy", "B", "x", "2")
        store.store("quest", "C", "x", "3")
        cats = store.categories()
        assert "npc" in cats
        assert "enemy" in cats
        assert "quest" in cats

    def test_subjects(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("npc", "Amber", "location", "Mondstadt")
        store.store("npc", "Kaeya", "location", "Mondstadt")
        subs = store.subjects(category="npc")
        assert "Amber" in subs
        assert "Kaeya" in subs

    def test_query_by_game_id(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("npc", "A", "x", "1", game_id="genshin")
        store.store("npc", "B", "x", "2", game_id="starrail")
        results = store.query(KnowledgeQuery(game_id="genshin"))
        assert len(results) == 1
        assert results[0].subject == "A"

    def test_close_and_reuse(self) -> None:
        store = GameKnowledgeStore(db_path=":memory:")
        store.store("npc", "A", "x", "1")
        store.close()
        # After close, in-memory DB reconnects with fresh schema
        results = store.query(KnowledgeQuery())
        assert len(results) == 0  # data lost on close for :memory:
