from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app_service.web_search_service import (
    SearchResult,
    SearchBackend,
    StubSearchBackend,
    WebSearchService,
)


class TestStubBackendReturnsEmpty:
    def test_returns_empty_list(self):
        backend = StubSearchBackend()
        assert backend.search("anything") == []

    def test_ignores_max_results(self):
        backend = StubSearchBackend()
        assert backend.search("query", max_results=10) == []


class TestSearchGameInfoConstructsQuery:
    def test_combines_game_and_topic(self):
        captured: list[str] = []

        class SpyBackend:
            def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
                captured.append(query)
                return []

        svc = WebSearchService(backend=SpyBackend())
        svc.search_game_info("Genshin Impact", "best team comp")
        assert captured == ["Genshin Impact best team comp"]


class TestSummarizeConcatenatesSnippets:
    def test_joins_snippets(self):
        results = [
            SearchResult("a", "http://a", "snippet a", "stub"),
            SearchResult("b", "http://b", "snippet b", "stub"),
        ]
        svc = WebSearchService()
        assert svc.summarize(results) == "snippet a\nsnippet b"

    def test_empty_results(self):
        svc = WebSearchService()
        assert svc.summarize([]) == ""


class TestCustomBackend:
    def test_uses_injected_backend(self):
        class FakeBackend:
            def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
                return [SearchResult("t", "http://u", "s", "fake", 0.9)]

        svc = WebSearchService(backend=FakeBackend())
        results = svc.search("test")
        assert len(results) == 1
        assert results[0].source == "fake"
        assert results[0].confidence == 0.9


class TestSearchResultFrozen:
    def test_frozen_dataclass(self):
        r = SearchResult("t", "http://u", "s", "stub")
        with pytest.raises(FrozenInstanceError):
            r.title = "changed"  # type: ignore[misc]
