"""Game mapper for BGA to BGG game ID mapping."""

import sqlite3
import requests
import re
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
from fuzzywuzzy import fuzz
from bs4 import BeautifulSoup
from bga_game_names import get_display_name, get_bgg_id


class GameMapper:
    """Maps BGA game names to BGG game IDs."""

    def __init__(self, db_path: Path, auto_confirm_threshold: int = 95, bgg_cookies: Optional[Dict[str, str]] = None, bga_client=None):
        """Initialize game mapper.

        Args:
            db_path: Path to SQLite database file
            auto_confirm_threshold: Fuzzy match score threshold for auto-confirmation
            bgg_cookies: Optional BGG session cookies for API access
            bga_client: Optional BGA client to fetch game display names
        """
        self.db_path = db_path
        self.auto_confirm_threshold = auto_confirm_threshold
        self.bga_client = bga_client

        # Create session with proper headers and cookies
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "dnt": "1",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1"
        })

        # Add BGG cookies if provided
        if bgg_cookies:
            self.session.cookies.update(bgg_cookies)

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS game_mappings (
                    bga_name TEXT PRIMARY KEY,
                    bgg_id INTEGER NOT NULL,
                    bgg_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_mapping(self, bga_name: str) -> Optional[Tuple[int, str]]:
        """Get BGG game ID for BGA game name from cache.

        Args:
            bga_name: BGA game name

        Returns:
            Tuple of (bgg_id, bgg_name) or None if not cached
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT bgg_id, bgg_name FROM game_mappings WHERE bga_name = ?",
                (bga_name,)
            )
            result = cursor.fetchone()
            return tuple(result) if result else None

    def save_mapping(self, bga_name: str, bgg_id: int, bgg_name: str) -> None:
        """Save a game mapping to database.

        Args:
            bga_name: BGA game name
            bgg_id: BGG game ID
            bgg_name: BGG game name
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO game_mappings
                (bga_name, bgg_id, bgg_name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (bga_name, bgg_id, bgg_name, datetime.now())
            )
            conn.commit()

    def search_bgg(self, query: str) -> List[Dict[str, Any]]:
        """Search BoardGameGeek for games matching query via JSON API.

        Args:
            query: Search query

        Returns:
            List of game dictionaries with id, name, year, and type
        """
        url = "https://boardgamegeek.com/search/boardgame"
        params = {
            "nosession": "1",
            "q": query,
            "showcount": "20"
        }

        # Set referer header
        self.session.headers["referer"] = f"https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q={query}"

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            # Parse JSON response
            data = response.json()
            results = []

            # BGG JSON response structure: {"items": [...]}
            items = data.get("items", [])

            for item in items:
                try:
                    game = self._parse_bgg_json_item(item)
                    if game:
                        results.append(game)
                except Exception as e:
                    continue

            return results

        except requests.RequestException as e:
            print(f"Warning: BGG search error: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Warning: BGG JSON parse error: {e}")
            return []

    def _parse_bgg_json_item(self, item: Dict) -> Optional[Dict[str, Any]]:
        """Parse a single search result item from BGG JSON.

        Args:
            item: Item dictionary from BGG JSON response

        Returns:
            Game dictionary or None
        """
        # Extract ID
        game_id = item.get("id")
        if not game_id:
            return None

        # Extract name
        name = item.get("name") or item.get("nameprimary")
        if not name:
            return None

        # Extract year
        year = item.get("yearpublished", "Unknown")

        return {
            "id": int(game_id),
            "name": name,
            "year": str(year) if year != "Unknown" else "Unknown",
            "type": "boardgame"
        }

    def find_best_matches(self, bga_name: str, limit: int = 5) -> List[Tuple[Dict[str, Any], int]]:
        """Find best matching BGG games for BGA game name.

        Args:
            bga_name: BGA game name
            limit: Maximum number of results

        Returns:
            List of tuples (game_dict, match_score) sorted by score descending
        """
        # Convert BGA internal name to human-readable for better search
        human_name = self._humanize_game_name(bga_name)

        # Search BGG with human-readable name
        results = self.search_bgg(human_name)

        # If no results with human name, try original
        if not results:
            time.sleep(0.5)  # Rate limiting
            results = self.search_bgg(bga_name)

        # Calculate fuzzy match scores against both BGA name and human name
        matches = []
        for game in results:
            # Use token set ratio for better matching (ignores word order)
            score1 = fuzz.token_set_ratio(bga_name.lower(), game["name"].lower())
            score2 = fuzz.token_set_ratio(human_name.lower(), game["name"].lower())
            score = max(score1, score2)  # Take best match
            matches.append((game, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches[:limit]

    def interactive_map(self, bga_name: str) -> Optional[Tuple[int, str]]:
        """Interactively map a BGA game to BGG game.

        Args:
            bga_name: BGA game name

        Returns:
            Tuple of (bgg_id, bgg_name) or None if user cancels
        """
        # First, try to get game info from BGA (includes display_name and bgg_id!)
        bga_game_info = None
        display_name = None
        bga_bgg_id = None

        if self.bga_client:
            print(f"\nFetching game info from BGA...")
            bga_game_info = self.bga_client.get_game_info(bga_name)

            if bga_game_info:
                display_name = bga_game_info.get("display_name")
                bga_bgg_id = bga_game_info.get("bgg_id")

                if display_name:
                    print(f"  ℹ️  Display name from BGA: '{display_name}'")

                # If BGA provides BGG ID, use it directly!
                if bga_bgg_id:
                    print(f"✅ BGA provides BGG ID: {bga_bgg_id}")
                    print(f"   Auto-selecting: '{display_name}' (BGG ID: {bga_bgg_id})")
                    # Fetch BGG game name to confirm
                    bgg_name = self._get_game_name_from_id(bga_bgg_id)
                    if bgg_name:
                        print(f"   Verified on BGG: '{bgg_name}'")
                        return (bga_bgg_id, bgg_name)
                    else:
                        # BGG name fetch failed, but we trust BGA's ID
                        print(f"   Using BGA's BGG ID (couldn't verify name)")
                        return (bga_bgg_id, display_name)

        # Fallback: check hardcoded mapping if BGA didn't provide info
        if not display_name:
            display_name = get_display_name(bga_name)
            known_bgg_id = get_bgg_id(bga_name)

            if known_bgg_id:
                print(f"\n✅ Using hardcoded game mapping:")
                print(f"   '{bga_name}' → '{display_name}' (BGG ID: {known_bgg_id})")
                bgg_name = self._get_game_name_from_id(known_bgg_id)
                if bgg_name:
                    return (known_bgg_id, bgg_name)
                else:
                    return (known_bgg_id, display_name)

        # Use display name for BGG search
        search_name = display_name

        print(f"\nSearching BGG for: '{search_name}'")
        print(f"  (Tip: Search boardgamegeek.com for '{search_name}' to find the game)")
        matches = self.find_best_matches(search_name)

        if not matches:
            print("No matches found on BGG (API may be blocking requests).")
            print(f"Please search manually at: https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q={bga_name}")
            manual_id = input("Enter BGG game ID manually (or press Enter to skip): ").strip()

            if manual_id and manual_id.isdigit():
                # Fetch game name from BGG
                game_info = self._get_game_info(int(manual_id))
                if game_info:
                    return (int(manual_id), game_info["name"])

            return None

        # Display matches
        print("\nTop matches:")
        for idx, (game, score) in enumerate(matches, 1):
            confidence = "✓ HIGH" if score >= self.auto_confirm_threshold else ""
            print(f"  {idx}. {game['name']} ({game['year']}) - ID: {game['id']} - Match: {score}% {confidence}")

        print(f"  {len(matches) + 1}. Enter custom BGG ID")
        print(f"  {len(matches) + 2}. Skip this game")

        # Auto-confirm if high confidence
        if matches[0][1] >= self.auto_confirm_threshold:
            confirm = input(f"\nAuto-select option 1? [Y/n]: ").strip().lower()
            if confirm in ('', 'y', 'yes'):
                game, _ = matches[0]
                return (game["id"], game["name"])

        # Get user selection
        while True:
            choice = input(f"\nSelect option (1-{len(matches) + 2}): ").strip()

            if not choice.isdigit():
                print("Please enter a number")
                continue

            choice_num = int(choice)

            if 1 <= choice_num <= len(matches):
                game, _ = matches[choice_num - 1]
                return (game["id"], game["name"])

            elif choice_num == len(matches) + 1:
                manual_id = input("Enter BGG game ID: ").strip()
                if manual_id.isdigit():
                    game_info = self._get_game_info(int(manual_id))
                    if game_info:
                        return (int(manual_id), game_info["name"])
                print("Invalid game ID")

            elif choice_num == len(matches) + 2:
                return None

            else:
                print(f"Please enter a number between 1 and {len(matches) + 2}")

    def _get_game_info(self, game_id: int) -> Optional[Dict[str, str]]:
        """Get game information from BGG by ID via web scraping.

        Args:
            game_id: BGG game ID

        Returns:
            Dictionary with game info or None if not found
        """
        url = f"https://boardgamegeek.com/boardgame/{game_id}"

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Try to find game name - usually in h1 or title
            name = None

            # Try meta tag
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                name = meta_title.get('content', '')

            # Try h1
            if not name:
                h1 = soup.find('h1')
                if h1:
                    name = h1.get_text(strip=True)

            # Try title tag
            if not name:
                title = soup.find('title')
                if title:
                    # Title is usually like "Game Name | Board Game | BoardGameGeek"
                    name = title.get_text(strip=True).split('|')[0].strip()

            if name:
                # Try to extract year
                year = "Unknown"
                year_span = soup.find('span', class_='game-year')
                if year_span:
                    year_match = re.search(r'\d{4}', year_span.get_text())
                    if year_match:
                        year = year_match.group(0)

                return {
                    "name": name,
                    "year": year
                }

        except requests.RequestException as e:
            print(f"Error fetching game info: {e}")

        return None

    def get_all_mappings(self) -> List[Tuple[str, int, str]]:
        """Get all game mappings from database.

        Returns:
            List of tuples (bga_name, bgg_id, bgg_name)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT bga_name, bgg_id, bgg_name FROM game_mappings ORDER BY bga_name"
            )
            return cursor.fetchall()

    def _get_game_name_from_id(self, game_id: int) -> Optional[str]:
        """Get BGG game name from game ID.

        Args:
            game_id: BGG game ID

        Returns:
            Game name or None
        """
        game_info = self._get_game_info(game_id)
        return game_info["name"] if game_info else None

    def _humanize_game_name(self, bga_name: str) -> str:
        """Convert BGA internal name to human-readable name.

        Args:
            bga_name: BGA internal game name (e.g., 'sevenwondersdice')

        Returns:
            Human-readable name (e.g., '7 Wonders Dice')
        """
        # Common BGA name patterns
        name_map = {
            "arknova": "Ark Nova",
            "sevenwondersdice": "7 Wonders Dice",
            "sevenwonders": "7 Wonders",
            "tipperary": "Tipperary",
            "cannonades": "Cannonades",
            "mlem": "MLEM",
        }

        if bga_name in name_map:
            return name_map[bga_name]

        # Generic conversion: add spaces before capitals, capitalize words
        # Insert space before capital letters
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', bga_name)
        # Capitalize each word
        return ' '.join(word.capitalize() for word in spaced.split())

    def clear_all(self) -> int:
        """Clear all game mappings from database.

        Returns:
            Number of records deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM game_mappings")
            conn.commit()
            return cursor.rowcount
