"""WebSearchService — real-time web search for game knowledge queries.

Supports pluggable backends:
- MiniMaxSearchBackend: Uses MiniMax MCP web_search tool
- SerpApiBackend: Uses SerpAPI (if API key available)
- StubSearchBackend: Returns empty results for dry-run / tests
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    confidence: float = 0.0


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class StubSearchBackend:
    """Returns empty results — used in dry-run mode and tests."""

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return []


class MiniMaxSearchBackend:
    """Searches via MiniMax MCP web_search endpoint.

    Uses the local MCP server at 127.0.0.1:15721 (or configured URL).
    Falls back gracefully if the MCP server is unavailable.
    """

    def __init__(self, endpoint: str = "http://127.0.0.1:15721") -> None:
        self._endpoint = endpoint.rstrip("/")

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        payload = json.dumps({
            "tool": "web_search",
            "args": {"query": query},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self._endpoint}/tools/call",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("[MiniMaxSearch] Request failed: %s", exc)
            return []

        results: list[SearchResult] = []
        entries = body if isinstance(body, list) else body.get("results", body.get("organic", []))
        for entry in entries[:max_results]:
            if isinstance(entry, dict):
                results.append(SearchResult(
                    title=entry.get("title", ""),
                    url=entry.get("link", entry.get("url", "")),
                    snippet=entry.get("snippet", ""),
                    source="minimax",
                    confidence=0.7,
                ))
        return results


class SerpApiBackend:
    """Searches via SerpAPI (Google Search Results API).

    Requires SERPAPI_KEY environment variable.
    """

    def __init__(self, api_key: str = "") -> None:
        import os
        self._api_key = api_key or os.getenv("SERPAPI_KEY", "")

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self._api_key:
            return []

        params = urllib.parse.urlencode({
            "q": query,
            "api_key": self._api_key,
            "engine": "google",
            "num": max_results,
        })
        url = f"https://serpapi.com/search?{params}"

        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("[SerpApi] Request failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for entry in body.get("organic_results", [])[:max_results]:
            results.append(SearchResult(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                snippet=entry.get("snippet", ""),
                source="serpapi",
                confidence=0.8,
            ))
        return results


class WebSearchService:
    """Real-time web search for game knowledge queries.

    Auto-selects the best available backend:
    1. MiniMax MCP (if running)
    2. SerpAPI (if key available)
    3. Stub (dry-run fallback)
    """

    def __init__(self, backend: SearchBackend | None = None, *, auto_detect: bool = True) -> None:
        if backend is not None:
            self._backend: SearchBackend = backend
        elif auto_detect:
            self._backend = self._auto_detect_backend()
        else:
            self._backend = StubSearchBackend()

    @staticmethod
    def _auto_detect_backend() -> SearchBackend:
        """Try MiniMax first, then SerpAPI, then stub."""
        import os

        # Try MiniMax MCP
        minimax = MiniMaxSearchBackend()
        try:
            probe = urllib.request.Request(
                "http://127.0.0.1:15721/health",
                method="GET",
            )
            with urllib.request.urlopen(probe, timeout=2):
                log.info("[WebSearch] Using MiniMax MCP backend")
                return minimax
        except Exception:
            pass

        # Try SerpAPI
        if os.getenv("SERPAPI_KEY"):
            log.info("[WebSearch] Using SerpAPI backend")
            return SerpApiBackend()

        log.info("[WebSearch] No search backend available, using stub")
        return StubSearchBackend()

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return self._backend.search(query, max_results)

    def search_game_info(self, game: str, topic: str) -> list[SearchResult]:
        query = f"{game} {topic}"
        return self.search(query)

    def summarize(self, results: list[SearchResult]) -> str:
        return "\n".join(r.snippet for r in results)
