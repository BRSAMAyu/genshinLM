"""E-32: Exploration history persistence and efficiency evaluation.

Tracks visited locations, chest openings, and exploration efficiency
to optimize future exploration routes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocationVisit:
    """Record of visiting a location."""
    location_id: str
    region: str
    timestamp: float
    duration_seconds: float = 0.0
    chest_found: int = 0
    chest_opened: int = 0
    enemy_encounters: int = 0
    quest_progress: float = 0.0


@dataclass(frozen=True, slots=True)
class ExplorationStats:
    """Exploration statistics for a region."""
    region: str
    total_visits: int
    total_time_seconds: float
    chests_found: int
    chests_opened: int
    efficiency_ratio: float  # chests opened / time spent
    undiscovered_count: int = 0
    completion_percentage: float = 0.0


class ExplorationHistory:
    """Persistent exploration history tracker."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path("data/exploration_history.db")
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._current_visit: LocationVisit | None = None
        self._visit_start: float = 0.0

        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS location_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id TEXT NOT NULL,
                region TEXT NOT NULL,
                timestamp REAL NOT NULL,
                duration_seconds REAL DEFAULT 0.0,
                chest_found INTEGER DEFAULT 0,
                chest_opened INTEGER DEFAULT 0,
                enemy_encounters INTEGER DEFAULT 0,
                quest_progress REAL DEFAULT 0.0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS region_stats (
                region TEXT PRIMARY KEY,
                total_visits INTEGER DEFAULT 0,
                total_time_seconds REAL DEFAULT 0.0,
                chests_found INTEGER DEFAULT 0,
                chests_opened INTEGER DEFAULT 0,
                last_visited REAL DEFAULT 0.0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS undiscovered_locations (
                location_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                hints_available INTEGER DEFAULT 0
            )
        """)

        self._conn.commit()
        log.info("[ExplorationHistory] Database initialized at %s", self._db_path)

    def start_visit(self, location_id: str, region: str) -> None:
        """Start tracking a visit to a location."""
        self._visit_start = time.perf_counter()
        self._current_visit = LocationVisit(
            location_id=location_id,
            region=region,
            timestamp=time.perf_counter(),
        )
        log.debug("[ExplorationHistory] Visit started: %s in %s", location_id, region)

    def end_visit(
        self,
        chest_found: int = 0,
        chest_opened: int = 0,
        enemy_encounters: int = 0,
        quest_progress: float = 0.0,
    ) -> LocationVisit | None:
        """End current visit and record stats."""
        if self._current_visit is None or self._conn is None:
            return None

        duration = time.perf_counter() - self._visit_start
        self._current_visit = LocationVisit(
            location_id=self._current_visit.location_id,
            region=self._current_visit.region,
            timestamp=self._current_visit.timestamp,
            duration_seconds=duration,
            chest_found=chest_found,
            chest_opened=chest_opened,
            enemy_encounters=enemy_encounters,
            quest_progress=quest_progress,
        )

        # Insert visit record
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO location_visits
            (location_id, region, timestamp, duration_seconds, chest_found, chest_opened, enemy_encounters, quest_progress)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._current_visit.location_id,
                self._current_visit.region,
                self._current_visit.timestamp,
                self._current_visit.duration_seconds,
                self._current_visit.chest_found,
                self._current_visit.chest_opened,
                self._current_visit.enemy_encounters,
                self._current_visit.quest_progress,
            ),
        )

        # Update region stats
        cursor.execute(
            """
            INSERT INTO region_stats (region, total_visits, total_time_seconds, chests_found, chests_opened, last_visited)
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(region) DO UPDATE SET
                total_visits = total_visits + 1,
                total_time_seconds = total_time_seconds + excluded.total_time_seconds,
                chests_found = chests_found + excluded.chests_found,
                chests_opened = chests_opened + excluded.chest_opened,
                last_visited = excluded.last_visited
            """,
            (
                self._current_visit.region,
                duration,
                chest_found,
                chest_opened,
                time.perf_counter(),
            ),
        )

        self._conn.commit()
        log.info(
            "[ExplorationHistory] Visit ended: %s, duration=%.1fs, chests=%d/%d",
            self._current_visit.location_id, duration, chest_opened, chest_found
        )

        visit = self._current_visit
        self._current_visit = None
        return visit

    def get_region_stats(self, region: str) -> ExplorationStats:
        """Get exploration statistics for a region."""
        if self._conn is None:
            return ExplorationStats(
                region=region,
                total_visits=0,
                total_time_seconds=0.0,
                chests_found=0,
                chests_opened=0,
                efficiency_ratio=0.0,
            )

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT total_visits, total_time_seconds, chests_found, chests_opened FROM region_stats WHERE region = ?",
            (region,),
        )
        row = cursor.fetchone()

        if row is None:
            return ExplorationStats(
                region=region,
                total_visits=0,
                total_time_seconds=0.0,
                chests_found=0,
                chests_opened=0,
                efficiency_ratio=0.0,
            )

        total_visits, total_time, chests_found, chests_opened = row
        efficiency = chests_opened / max(total_time, 1.0) * 60.0  # chests per hour

        return ExplorationStats(
            region=region,
            total_visits=total_visits,
            total_time_seconds=total_time,
            chests_found=chests_found,
            chests_opened=chest_opened,
            efficiency_ratio=efficiency,
        )

    def get_undiscovered_locations(self, region: str | None = None) -> list[str]:
        """Get list of undiscovered location IDs."""
        if self._conn is None:
            return []

        cursor = self._conn.cursor()
        if region:
            cursor.execute(
                "SELECT location_id FROM undiscovered_locations WHERE region = ?",
                (region,),
            )
        else:
            cursor.execute("SELECT location_id FROM undiscovered_locations")

        return [row[0] for row in cursor.fetchall()]

    def mark_undiscovered(self, location_id: str, region: str) -> None:
        """Mark a location as undiscovered (potential target)."""
        if self._conn is None:
            return
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO undiscovered_locations (location_id, region) VALUES (?, ?)",
            (location_id, region),
        )
        self._conn.commit()

    def mark_discovered(self, location_id: str) -> None:
        """Mark a location as discovered (remove from undiscovered list)."""
        if self._conn is None:
            return
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM undiscovered_locations WHERE location_id = ?", (location_id,))
        self._conn.commit()

    def get_recent_visits(self, region: str | None = None, limit: int = 20) -> list[LocationVisit]:
        """Get recent location visits."""
        if self._conn is None:
            return []

        cursor = self._conn.cursor()
        if region:
            cursor.execute(
                "SELECT location_id, region, timestamp, duration_seconds, chest_found, chest_opened, enemy_encounters, quest_progress "
                "FROM location_visits WHERE region = ? ORDER BY timestamp DESC LIMIT ?",
                (region, limit),
            )
        else:
            cursor.execute(
                "SELECT location_id, region, timestamp, duration_seconds, chest_found, chest_opened, enemy_encounters, quest_progress "
                "FROM location_visits ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )

        return [
            LocationVisit(
                location_id=row[0],
                region=row[1],
                timestamp=row[2],
                duration_seconds=row[3],
                chest_found=row[4],
                chest_opened=row[5],
                enemy_encounters=row[6],
                quest_progress=row[7],
            )
            for row in cursor.fetchall()
        ]

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "ExplorationHistory":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()