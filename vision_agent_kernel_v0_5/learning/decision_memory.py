from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    strategy_id: str
    goal: str
    capsule_id: str
    screen_state: str
    plan_json: str
    success: bool
    duration_sec: float
    attempts: int
    confidence: float
    created_at: float

    def plan_steps(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.plan_json)
        except json.JSONDecodeError:
            return []


@dataclass(frozen=True, slots=True)
class DecisionQuery:
    goal: str = ""
    capsule_id: str = ""
    screen_state: str = ""
    limit: int = 10


@dataclass(slots=True)
class DecisionMemoryStats:
    total_records: int = 0
    success_rate: float = 0.0
    by_capsule: dict[str, float] = field(default_factory=dict)
    by_goal_prefix: dict[str, float] = field(default_factory=dict)


class DecisionMemory:
    """Persistent storage for successful and failed mission strategies."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            data_dir = Path(os.getenv("AURORA_DATA_DIR", "data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "decision_memory.db")
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._insert_count = 0
        self._init_db()

    def close(self) -> None:
        with self._conn_lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _conn_ctx(self) -> sqlite3.Connection:
        with self._conn_lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self._db_path)
            return self._conn

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategies (
                strategy_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                capsule_id TEXT NOT NULL,
                screen_state TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_sec REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 1,
                confidence REAL NOT NULL DEFAULT 0.5,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_goal ON strategies(goal);
            CREATE INDEX IF NOT EXISTS idx_capsule ON strategies(capsule_id);
            CREATE INDEX IF NOT EXISTS idx_screen ON strategies(screen_state);
            CREATE INDEX IF NOT EXISTS idx_success ON strategies(success);
        """)
        conn.commit()
        # Keep the connection open for in-memory DBs; close for file-backed
        if self._db_path == ":memory:":
            self._conn = conn
        else:
            conn.close()

    def record(
        self,
        goal: str,
        capsule_id: str,
        screen_state: str,
        plan: list[dict[str, Any]],
        success: bool,
        duration_sec: float,
        attempts: int = 1,
        confidence: float = 0.5,
    ) -> str:
        strategy_id = f"{capsule_id}:{uuid.uuid4().hex[:12]}"
        plan_json = json.dumps(plan, ensure_ascii=False)
        now = time.time()  # Wall-clock to match prune()'s wall-clock comparison
        conn = self._conn_ctx()
        conn.execute(
            "INSERT INTO strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (strategy_id, goal, capsule_id, screen_state, plan_json,
             int(success), duration_sec, attempts, confidence, now),
        )
        conn.commit()
        self._insert_count += 1
        if self._insert_count % 500 == 0:
            self.prune()
        return strategy_id

    def query(self, query: DecisionQuery) -> list[StrategyRecord]:
        conditions: list[str] = []
        params: list[Any] = []

        if query.goal:
            conditions.append("goal LIKE ?")
            params.append(f"%{query.goal}%")
        if query.capsule_id:
            conditions.append("capsule_id = ?")
            params.append(query.capsule_id)
        if query.screen_state:
            conditions.append("screen_state = ?")
            params.append(query.screen_state)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM strategies WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params.append(query.limit)

        conn = self._conn_ctx()
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def best_strategy_for(self, goal: str, capsule_id: str, screen_state: str = "") -> StrategyRecord | None:
        sql = "SELECT * FROM strategies WHERE goal LIKE ? AND capsule_id = ? AND success = 1"
        params: list[Any] = [f"%{goal}%", capsule_id]
        if screen_state:
            sql += " AND screen_state = ?"
            params.append(screen_state)
        sql += " ORDER BY confidence DESC, duration_sec ASC LIMIT 1"
        conn = self._conn_ctx()
        row = conn.execute(sql, params).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def success_rate(self, capsule_id: str = "", goal: str = "") -> float:
        conditions = []
        params: list[Any] = []
        if capsule_id:
            conditions.append("capsule_id = ?")
            params.append(capsule_id)
        if goal:
            conditions.append("goal LIKE ?")
            params.append(f"%{goal}%")
        where = " AND ".join(conditions) if conditions else "1=1"
        conn = self._conn_ctx()
        total = conn.execute(f"SELECT COUNT(*) FROM strategies WHERE {where}", params).fetchone()[0]
        if total == 0:
            return 0.0
        successes = conn.execute(
            f"SELECT COUNT(*) FROM strategies WHERE {where} AND success = 1", params
        ).fetchone()[0]
        return successes / total

    def stats(self) -> DecisionMemoryStats:
        conn = self._conn_ctx()
        total = conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
        if total == 0:
            return DecisionMemoryStats()
        successes = conn.execute("SELECT COUNT(*) FROM strategies WHERE success = 1").fetchone()[0]
        capsule_rows = conn.execute(
            "SELECT capsule_id, AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) "
            "FROM strategies GROUP BY capsule_id"
        ).fetchall()
        by_capsule = {row[0]: round(row[1], 3) for row in capsule_rows}
        return DecisionMemoryStats(
            total_records=total,
            success_rate=round(successes / total, 3),
            by_capsule=by_capsule,
        )

    def prune(self, max_age_days: int = 30) -> int:
        """Remove old low-confidence records while protecting top-3 per (goal, capsule_id).

        For each (goal, capsule_id) group the three highest-confidence records are
        always kept, regardless of age.  Only records outside this protected set that
        are also older than *max_age_days* are deleted.
        """
        # Intentional use of wall-clock time for calendar-day age calculation.
        cutoff = time.time() - (max_age_days * 86400)
        conn = self._conn_ctx()

        # Perform the delete in a single query using a subquery to avoid SQLite variable limits
        cursor = conn.execute(
            """
            DELETE FROM strategies 
            WHERE created_at < ? 
              AND strategy_id NOT IN (
                  SELECT strategy_id
                  FROM (
                      SELECT strategy_id,
                             ROW_NUMBER() OVER (
                                 PARTITION BY goal, capsule_id
                                 ORDER BY confidence DESC, created_at DESC
                             ) AS rn
                      FROM strategies
                  ) ranked
                  WHERE rn <= 3
              )
            """,
            (cutoff,),
        )

        conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> StrategyRecord:
        return StrategyRecord(
            strategy_id=row[0], goal=row[1], capsule_id=row[2],
            screen_state=row[3], plan_json=row[4], success=bool(row[5]),
            duration_sec=row[6], attempts=row[7], confidence=row[8],
            created_at=row[9],
        )
