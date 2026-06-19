"""GameKnowledgeStore: persistent structured knowledge for game facts.

Stores entity attributes, quest prerequisites, NPC locations, enemy weaknesses,
and other game knowledge in a queryable SQLite database. Knowledge survives
restarts and can be populated from exploration, VLM observations, or manual entry.

Phase 4 roadmap: long-term growth through accumulated game knowledge.

Features:
- Conflict resolution: when multiple sources disagree on the same fact,
  resolves by source priority + confidence + recency
- Knowledge decay: older or low-confidence facts gradually fade,
  with configurable half-life and pruning threshold
- Source trust tracking: sources that consistently provide accurate info
  gain higher effective weight in conflicts
"""
from __future__ import annotations

import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Source priority: higher = more trusted. Manual > wiki > vlm > exploration
_SOURCE_PRIORITY: dict[str, int] = {
    "manual": 100,
    "wiki": 80,
    "vlm": 50,
    "exploration": 30,
    "inferred": 20,
    "unknown": 10,
}

# Default decay half-life in seconds (7 days)
_DEFAULT_HALF_LIFE_SEC: float = 7 * 24 * 3600.0


@dataclass(frozen=True, slots=True)
class KnowledgeFact:
    fact_id: str
    category: str  # npc, quest, enemy, location, item, mechanic
    subject: str
    attribute: str
    value: str
    source: str  # vlm, exploration, manual, wiki
    confidence: float
    game_id: str
    created_at: float
    updated_at: float = 0.0
    access_count: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    category: str = ""
    subject: str = ""
    attribute: str = ""
    game_id: str = ""
    min_confidence: float = 0.0
    min_effective_confidence: float = 0.0  # after decay
    limit: int = 20


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    """Result of resolving a conflict between multiple facts."""
    winning_fact_id: str
    winning_value: str
    discarded_count: int
    resolution_method: str  # "priority", "confidence", "recency"


class GameKnowledgeStore:
    """Persistent store for structured game knowledge.

    Handles conflict resolution and knowledge decay automatically.
    """

    def __init__(
        self,
        db_path: str | None = None,
        decay_half_life_sec: float = _DEFAULT_HALF_LIFE_SEC,
        prune_effective_below: float = 0.05,
    ) -> None:
        if db_path is None:
            data_dir = Path(os.getenv("AURORA_DATA_DIR", "data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "game_knowledge.db")
        self._db_path = db_path
        self._half_life = decay_half_life_sec
        self._prune_threshold = prune_effective_below
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._source_trust: dict[str, float] = {}
        self._init_db()

    def _conn_ctx(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self._db_path)
                if self._db_path == ":memory:":
                    self._init_schema(self._conn)
            return self._conn

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        self._init_schema(conn)
        conn.commit()
        if self._db_path == ":memory:":
            self._conn = conn
        else:
            conn.close()

    @staticmethod
    def _init_schema(conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'unknown',
                confidence REAL NOT NULL DEFAULT 0.5,
                game_id TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL DEFAULT 0,
                access_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
            CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
            CREATE INDEX IF NOT EXISTS idx_facts_game ON facts(game_id);
            CREATE INDEX IF NOT EXISTS idx_facts_compound ON facts(subject, attribute, game_id);

            CREATE TABLE IF NOT EXISTS source_trust (
                source TEXT PRIMARY KEY,
                trust_score REAL NOT NULL DEFAULT 1.0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                incorrect_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS conflict_log (
                conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                attribute TEXT NOT NULL,
                game_id TEXT NOT NULL,
                winner_fact_id TEXT NOT NULL,
                discarded_count INTEGER NOT NULL,
                method TEXT NOT NULL,
                resolved_at REAL NOT NULL
            );
        """)

    def store(
        self,
        category: str,
        subject: str,
        attribute: str,
        value: str,
        source: str = "exploration",
        confidence: float = 0.5,
        game_id: str = "",
    ) -> str:
        """Store a knowledge fact with conflict resolution.

        If a fact with the same (subject, attribute, game_id) but different value
        already exists, resolves the conflict by source priority + confidence + recency.
        Returns fact_id of the winning fact.
        """
        import hashlib
        raw = f"{category}:{subject}:{attribute}:{game_id}"
        fact_id = hashlib.md5(raw.encode()).hexdigest()[:16]

        conn = self._conn_ctx()
        now = time.time()

        # Check for existing fact with same key
        existing = conn.execute(
            "SELECT fact_id, value, source, confidence, created_at FROM facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()

        if existing is not None:
            existing_value = existing[1]
            if existing_value == value:
                # Same value — just update confidence and timestamp
                new_confidence = max(existing[3], confidence)
                conn.execute(
                    "UPDATE facts SET confidence = ?, updated_at = ?, "
                    "access_count = access_count + 1 WHERE fact_id = ?",
                    (new_confidence, now, fact_id),
                )
                conn.commit()
                return fact_id

            # Different value — conflict! Resolve it
            resolution = self._resolve_conflict(
                existing_fact_id=existing[0],
                existing_value=existing[1],
                existing_source=existing[2],
                existing_confidence=existing[3],
                existing_created=existing[4],
                new_value=value,
                new_source=source,
                new_confidence=confidence,
                subject=subject,
                attribute=attribute,
                game_id=game_id,
            )

            if resolution.winning_value == value:
                # New value wins — replace
                conn.execute(
                    "UPDATE facts SET value = ?, source = ?, confidence = ?, "
                    "updated_at = ? WHERE fact_id = ?",
                    (value, source, confidence, now, fact_id),
                )
                self._update_source_feedback(source, correct=True)
                self._update_source_feedback(existing[2], correct=False)
            else:
                # Existing value wins — just bump access count
                conn.execute(
                    "UPDATE facts SET updated_at = ?, access_count = access_count + 1 WHERE fact_id = ?",
                    (now, fact_id),
                )
                self._update_source_feedback(existing[2], correct=True)
                self._update_source_feedback(source, correct=False)

            # Log conflict
            conn.execute(
                "INSERT INTO conflict_log (subject, attribute, game_id, winner_fact_id, "
                "discarded_count, method, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (subject, attribute, game_id, fact_id,
                 resolution.discarded_count, resolution.resolution_method, now),
            )
            conn.commit()
            return fact_id

        # No conflict — insert new
        conn.execute(
            """INSERT OR REPLACE INTO facts
               (fact_id, category, subject, attribute, value, source, confidence, game_id,
                created_at, updated_at, access_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (fact_id, category, subject, attribute, value, source, confidence, game_id, now, now),
        )
        conn.commit()
        return fact_id

    def query(self, query: KnowledgeQuery) -> list[KnowledgeFact]:
        """Query facts matching criteria."""
        conditions: list[str] = []
        params: list[Any] = []

        if query.category:
            conditions.append("category = ?")
            params.append(query.category)
        if query.subject:
            conditions.append("subject LIKE ?")
            params.append(f"%{query.subject}%")
        if query.attribute:
            conditions.append("attribute = ?")
            params.append(query.attribute)
        if query.game_id:
            conditions.append("game_id = ?")
            params.append(query.game_id)
        if query.min_confidence > 0:
            conditions.append("confidence >= ?")
            params.append(query.min_confidence)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM facts WHERE {where} ORDER BY confidence DESC LIMIT ?"
        params.append(query.limit)

        conn = self._conn_ctx()
        rows = conn.execute(sql, params).fetchall()
        facts = [self._row_to_fact(row) for row in rows]

        # Apply decay filter if requested
        if query.min_effective_confidence > 0:
            facts = [
                f for f in facts
                if self._effective_confidence(f) >= query.min_effective_confidence
            ]

        # Bump access count
        for f in facts:
            conn.execute(
                "UPDATE facts SET access_count = access_count + 1 WHERE fact_id = ?",
                (f.fact_id,),
            )
        conn.commit()

        return facts

    def get(self, category: str, subject: str, attribute: str, game_id: str = "") -> KnowledgeFact | None:
        """Get a specific fact."""
        import hashlib
        raw = f"{category}:{subject}:{attribute}:{game_id}"
        fact_id = hashlib.md5(raw.encode()).hexdigest()[:16]
        conn = self._conn_ctx()
        row = conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE facts SET access_count = access_count + 1 WHERE fact_id = ?", (fact_id,))
        conn.commit()
        return self._row_to_fact(row)

    def categories(self, game_id: str = "") -> list[str]:
        """List all categories."""
        conn = self._conn_ctx()
        if game_id:
            rows = conn.execute(
                "SELECT DISTINCT category FROM facts WHERE game_id = ? ORDER BY category",
                (game_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT category FROM facts ORDER BY category").fetchall()
        return [r[0] for r in rows]

    def subjects(self, category: str = "", game_id: str = "") -> list[str]:
        """List all subjects, optionally filtered by category."""
        conn = self._conn_ctx()
        conditions = []
        params: list[Any] = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if game_id:
            conditions.append("game_id = ?")
            params.append(game_id)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(
            f"SELECT DISTINCT subject FROM facts WHERE {where} ORDER BY subject", params
        ).fetchall()
        return [r[0] for r in rows]

    def effective_confidence(self, fact: KnowledgeFact) -> float:
        """Public accessor for decayed confidence."""
        return self._effective_confidence(fact)

    def prune_decayed(self) -> int:
        """Remove facts whose effective confidence has fallen below the prune threshold.

        Returns count of pruned facts.
        """
        conn = self._conn_ctx()
        rows = conn.execute("SELECT * FROM facts").fetchall()
        pruned = 0
        now = time.time()
        for row in rows:
            fact = self._row_to_fact(row)
            eff = self._effective_confidence(fact)
            if eff < self._prune_threshold:
                conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact.fact_id,))
                pruned += 1
        if pruned > 0:
            conn.commit()
            log.info("[KnowledgeStore] Pruned %d decayed facts (threshold=%.2f)", pruned, self._prune_threshold)
        return pruned

    def get_conflict_history(self, game_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Get conflict resolution history for auditing."""
        conn = self._conn_ctx()
        if game_id:
            rows = conn.execute(
                "SELECT * FROM conflict_log WHERE game_id = ? ORDER BY resolved_at DESC LIMIT ?",
                (game_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conflict_log ORDER BY resolved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "conflict_id": r[0], "subject": r[1], "attribute": r[2],
                "game_id": r[3], "winner_fact_id": r[4],
                "discarded_count": r[5], "method": r[6], "resolved_at": r[7],
            }
            for r in rows
        ]

    def get_source_trust_scores(self) -> dict[str, float]:
        """Get current trust scores for all sources."""
        conn = self._conn_ctx()
        rows = conn.execute("SELECT source, trust_score FROM source_trust").fetchall()
        return {r[0]: r[1] for r in rows}

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge store statistics."""
        conn = self._conn_ctx()
        total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        by_category: dict[str, int] = {}
        for row in conn.execute("SELECT category, COUNT(*) FROM facts GROUP BY category"):
            by_category[row[0]] = row[1]
        conflicts = conn.execute("SELECT COUNT(*) FROM conflict_log").fetchone()[0]
        return {
            "total_facts": total,
            "by_category": by_category,
            "total_conflicts": conflicts,
            "decay_half_life_days": self._half_life / 86400.0,
            "prune_threshold": self._prune_threshold,
        }

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_conflict(
        self,
        existing_fact_id: str,
        existing_value: str,
        existing_source: str,
        existing_confidence: float,
        existing_created: float,
        new_value: str,
        new_source: str,
        new_confidence: float,
        subject: str,
        attribute: str,
        game_id: str,
    ) -> ConflictResolution:
        """Resolve conflict between existing and new fact values.

        Resolution strategy (in priority order):
        1. Source priority: higher-priority source wins
        2. Confidence: if sources have equal priority, higher confidence wins
        3. Recency: if still tied, newer fact wins
        4. Source trust: accumulated trust score breaks remaining ties
        """
        existing_priority = _SOURCE_PRIORITY.get(existing_source, 10)
        new_priority = _SOURCE_PRIORITY.get(new_source, 10)

        existing_trust = self._source_trust.get(existing_source, 1.0)
        new_trust = self._source_trust.get(new_source, 1.0)

        # Weighted scores
        existing_score = (
            existing_priority * 10.0 +
            existing_confidence * 100.0 +
            existing_trust * 20.0
        )
        new_score = (
            new_priority * 10.0 +
            new_confidence * 100.0 +
            new_trust * 20.0
        )

        if new_score > existing_score:
            method = "priority" if new_priority != existing_priority else (
                "confidence" if abs(new_confidence - existing_confidence) > 0.1 else "recency"
            )
            return ConflictResolution(
                winning_fact_id=existing_fact_id,  # will be updated with new value
                winning_value=new_value,
                discarded_count=1,
                resolution_method=method,
            )
        else:
            method = "priority" if existing_priority != new_priority else (
                "confidence" if abs(existing_confidence - new_confidence) > 0.1 else "recency"
            )
            return ConflictResolution(
                winning_fact_id=existing_fact_id,
                winning_value=existing_value,
                discarded_count=1,
                resolution_method=method,
            )

    def _update_source_feedback(self, source: str, correct: bool) -> None:
        """Update trust score for a source based on conflict resolution outcome."""
        conn = self._conn_ctx()
        if correct:
            conn.execute(
                "INSERT INTO source_trust (source, trust_score, correct_count, incorrect_count) "
                "VALUES (?, 1.0, 1, 0) ON CONFLICT(source) DO UPDATE SET "
                "correct_count = correct_count + 1, "
                "trust_score = CAST(correct_count + 1 AS REAL) / (correct_count + incorrect_count + 1)",
                (source,),
            )
        else:
            conn.execute(
                "INSERT INTO source_trust (source, trust_score, correct_count, incorrect_count) "
                "VALUES (?, 1.0, 0, 1) ON CONFLICT(source) DO UPDATE SET "
                "incorrect_count = incorrect_count + 1, "
                "trust_score = CAST(correct_count AS REAL) / (correct_count + incorrect_count + 1)",
                (source,),
            )
        # Cache locally
        rows = conn.execute(
            "SELECT trust_score FROM source_trust WHERE source = ?", (source,)
        ).fetchone()
        if rows:
            self._source_trust[source] = rows[0]

    # ------------------------------------------------------------------
    # Knowledge decay
    # ------------------------------------------------------------------

    def _effective_confidence(self, fact: KnowledgeFact) -> float:
        """Compute effective confidence with time decay and access reinforcement.

        Decay formula: conf * exp(-age * ln(2) / half_life) * (1 + log(1 + access_count) * 0.1)

        Facts accessed frequently decay more slowly (reinforcement).
        """
        now = time.time()
        age = now - fact.updated_at if fact.updated_at > 0 else now - fact.created_at
        if age < 0:
            age = 0

        # Exponential decay
        decay = math.exp(-age * math.log(2) / self._half_life)

        # Access reinforcement: frequently accessed facts decay more slowly
        reinforcement = 1.0 + math.log1p(fact.access_count) * 0.1

        return min(1.0, fact.confidence * decay * reinforcement)

    @staticmethod
    def _row_to_fact(row: tuple[Any, ...]) -> KnowledgeFact:
        return KnowledgeFact(
            fact_id=row[0], category=row[1], subject=row[2],
            attribute=row[3], value=row[4], source=row[5],
            confidence=row[6], game_id=row[7], created_at=row[8],
            updated_at=row[9] if len(row) > 9 else 0.0,
            access_count=row[10] if len(row) > 10 else 0,
        )
