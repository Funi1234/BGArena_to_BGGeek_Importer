"""Play tracker for duplicate prevention."""

import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class PlayTracker:
    """Tracks submitted plays to prevent duplicates."""

    def __init__(self, db_path: Path):
        """Initialize play tracker with database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submitted_plays (
                    play_hash TEXT PRIMARY KEY,
                    bga_game_name TEXT,
                    bgg_game_id INTEGER,
                    play_date TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(submitted_plays)")}
            for name in ("bgg_play_id", "batch_id", "rollback_state"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE submitted_plays ADD COLUMN {name} TEXT")
            conn.commit()

    def begin_submission(self, table_id: str, game_id: int, play_date: str,
                         players: List[str], duration: Optional[int],
                         bga_game_name: str, force: bool = False) -> bool:
        """Reserve a table before POST. An interrupted reservation remains blocked."""
        if table_id is None or not str(table_id).strip():
            return False
        key = "bga:" + str(table_id)
        legacy = self._generate_hash(game_id, play_date, players, duration)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT bga_game_name FROM submitted_plays WHERE play_hash = ?", (key,)).fetchone()
            # Pending is never overridden by --force: it may already exist on BGG.
            if row:
                return False
            if not force and conn.execute("SELECT 1 FROM submitted_plays WHERE play_hash = ?", (legacy,)).fetchone():
                return False
            conn.execute("INSERT OR REPLACE INTO submitted_plays (play_hash, bga_game_name, bgg_game_id, play_date) VALUES (?, ?, ?, ?)",
                         (key, "__pending__", game_id, play_date))
            return True

    def finish_submission(self, table_id: str, bga_game_name: str, play_id=None, batch_id=None) -> None:
        """Mark a reserved table as verified after an explicit success response."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE submitted_plays SET bga_game_name = ?, bgg_play_id = ?, batch_id = ? WHERE play_hash = ?",
                         (bga_game_name, str(play_id) if play_id else None, batch_id, "bga:" + str(table_id)))

    def rollback_records(self, batch_id=None):
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT batch_id, play_hash, bga_game_name, play_date, bgg_play_id, rollback_state FROM submitted_plays WHERE bgg_play_id IS NOT NULL"
            args = ()
            if batch_id:
                query += " AND batch_id = ?"
                args = (batch_id,)
            return conn.execute(query + " ORDER BY batch_id, play_date, play_hash", args).fetchall()

    def begin_rollback(self, table_key, play_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("UPDATE submitted_plays SET rollback_state = 'pending' WHERE play_hash = ? AND bgg_play_id = ? AND rollback_state IS NULL", (table_key, str(play_id)))
            return cursor.rowcount == 1

    def resolve_rollback(self, table_id, resolution):
        with sqlite3.connect(self.db_path) as conn:
            key = 'bga:' + str(table_id)
            if resolution == 'deleted':
                cursor = conn.execute("DELETE FROM submitted_plays WHERE play_hash = ? AND rollback_state = 'pending'", (key,))
            else:
                cursor = conn.execute("UPDATE submitted_plays SET rollback_state = NULL WHERE play_hash = ? AND rollback_state = 'pending'", (key,))
            return cursor.rowcount == 1

    def table_status(self, table_id: str) -> Optional[str]:
        if table_id is None or not str(table_id).strip():
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT bga_game_name, rollback_state FROM submitted_plays WHERE play_hash = ?", ("bga:" + str(table_id),)).fetchone()
        return ("pending" if row[0] == "__pending__" or row[1] == 'pending' else "submitted") if row else None

    def resolve_submission(self, table_id: str, resolution: str) -> bool:
        """Apply the user's manual BGG verification to a pending reservation."""
        if resolution not in ("submitted", "retry"):
            raise ValueError("Invalid resolution")
        with sqlite3.connect(self.db_path) as conn:
            if resolution == "retry":
                cursor = conn.execute("DELETE FROM submitted_plays WHERE play_hash = ? AND bga_game_name = '__pending__'", ("bga:" + str(table_id),))
            else:
                cursor = conn.execute("UPDATE submitted_plays SET bga_game_name = 'Manually verified' WHERE play_hash = ? AND bga_game_name = '__pending__'", ("bga:" + str(table_id),))
            return cursor.rowcount == 1

    def _generate_hash(self, game_id: int, play_date: str, players: List[str], duration: Optional[int] = None) -> str:
        """Generate unique hash for a play.

        Args:
            game_id: BGG game ID
            play_date: Play date in YYYY-MM-DD format
            players: List of player names
            duration: Optional game duration in minutes

        Returns:
            SHA256 hash string
        """
        # Sort players to ensure consistent hashing regardless of order
        players_sorted = sorted(players)
        # Include duration to distinguish multiple plays of same game on same day
        duration_str = str(duration) if duration is not None else "unknown"
        unique_string = f"{game_id}|{play_date}|{'|'.join(players_sorted)}|{duration_str}"
        return hashlib.sha256(unique_string.encode()).hexdigest()

    def is_duplicate(self, game_id: int, play_date: str, players: List[str], duration: Optional[int] = None) -> bool:
        """Check if a play has already been submitted.

        Args:
            game_id: BGG game ID
            play_date: Play date in YYYY-MM-DD format
            players: List of player names
            duration: Optional game duration in minutes

        Returns:
            True if play already exists in database
        """
        play_hash = self._generate_hash(game_id, play_date, players, duration)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM submitted_plays WHERE play_hash = ?",
                (play_hash,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    def record_play(
        self,
        game_id: int,
        play_date: str,
        players: List[str],
        duration: Optional[int] = None,
        bga_game_name: Optional[str] = None
    ) -> None:
        """Record a submitted play in the database.

        Args:
            game_id: BGG game ID
            play_date: Play date in YYYY-MM-DD format
            players: List of player names
            duration: Optional game duration in minutes
            bga_game_name: Optional BGA game name
        """
        play_hash = self._generate_hash(game_id, play_date, players, duration)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO submitted_plays
                (play_hash, bga_game_name, bgg_game_id, play_date, submitted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (play_hash, bga_game_name, game_id, play_date, datetime.now())
            )
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about submitted plays.

        Returns:
            Dictionary with statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total plays
            cursor = conn.execute("SELECT COUNT(*) FROM submitted_plays")
            total_plays = cursor.fetchone()[0]

            # Plays by game
            cursor = conn.execute("""
                SELECT bga_game_name, COUNT(*) as count
                FROM submitted_plays
                WHERE bga_game_name IS NOT NULL
                GROUP BY bga_game_name
                ORDER BY count DESC
                LIMIT 10
            """)
            top_games = cursor.fetchall()

            # Recent plays
            cursor = conn.execute("""
                SELECT bga_game_name, play_date, submitted_at
                FROM submitted_plays
                ORDER BY submitted_at DESC
                LIMIT 5
            """)
            recent_plays = cursor.fetchall()

            return {
                "total_plays": total_plays,
                "top_games": [{"game": name, "count": count} for name, count in top_games],
                "recent_plays": [
                    {"game": game, "play_date": play_date, "submitted_at": submitted_at}
                    for game, play_date, submitted_at in recent_plays
                ]
            }

    def clear_all(self) -> int:
        """Clear all submitted plays from database.

        Returns:
            Number of records deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM submitted_plays")
            conn.commit()
            return cursor.rowcount
