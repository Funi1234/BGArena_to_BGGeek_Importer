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
            conn.commit()

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
