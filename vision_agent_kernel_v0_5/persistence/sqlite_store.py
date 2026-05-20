from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)")

    def put(self, key: str, value: dict[str, Any]) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute("REPLACE INTO kv(key, value, updated_at) VALUES (?, ?, ?)", (key, json.dumps(value, ensure_ascii=False), time.time()))

    def get(self, key: str) -> dict[str, Any] | None:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

