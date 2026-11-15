"""Board Game Arena API client."""

import requests
from secure_session import OriginSession
from typing import List, Dict, Any, Optional
import json
import time
from datetime import datetime


class BGAClient:
    """Client for fetching game history from Board Game Arena."""

    BASE_URL = "https://boardgamearena.com"

    def __init__(self, player_id: str, cookies: Dict[str, str], request_delay: float = 1.0):
        """Initialize BGA client.

        Args:
            player_id: BGA player ID
            cookies: Dictionary of BGA session cookies
            request_delay: Delay between requests in seconds
        """
        self.player_id = player_id
        self.request_delay = request_delay

        # Create session with cookies
        self.session = OriginSession("boardgamearena.com", cookies)

        # Set required headers
        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "en-GB,en;q=0.7",
            "dnt": "1",
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # Extract x-request-token from cookies (typically TournoiEnLigneidt value)
        if "TournoiEnLigneidt" in cookies:
            self.session.headers["x-request-token"] = cookies["TournoiEnLigneidt"]

    def fetch_games(self, page: int = 1, update_stats: bool = False) -> Optional[Dict]:
        """Fetch games page from BGA.

        Args:
            page: Page number (1-indexed)
            update_stats: Whether to update stats (only for first page)

        Returns:
            JSON response dict or None on error
        """
        url = f"{self.BASE_URL}/gamestats/gamestats/getGames.html"

        params = {
            "player": self.player_id,
            "opponent_id": "0",
            "finished": "0",
            "page": str(page),
            "updateStats": "1" if (page == 1 and update_stats) else "0",
            "dojo.preventCache": str(int(time.time() * 1000))
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            # Rate limiting
            time.sleep(self.request_delay)

            # Parse JSON response
            return response.json()

        except requests.RequestException as e:
            print(f"Error fetching BGA games page {page}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing BGA JSON response: {e}")
            return None

    def parse_games_json(self, response: Dict) -> List[Dict[str, Any]]:
        """Parse game data from BGA JSON response.

        Args:
            response: JSON response from getGames.html

        Returns:
            List of game dictionaries
        """
        games = []

        # BGA response structure: {"status": 1, "data": {"tables": [...]}}
        if not response or response.get("status") != 1:
            return games

        tables = response.get("data", {}).get("tables", [])

        for table in tables:
            try:
                game = self._parse_game_table(table)
                if game:
                    games.append(game)
            except Exception as e:
                print(f"Warning: Failed to parse game table: {e}")
                continue

        return games

    def _parse_game_table(self, table: Dict) -> Optional[Dict[str, Any]]:
        """Parse a single game table from BGA JSON.

        Args:
            table: Table dictionary from BGA response

        Returns:
            Game dictionary or None if parsing fails
        """
        # Extract basic info
        table_id = table.get("table_id")
        game_name = table.get("game_name")  # Internal BGA game name
        game_id = table.get("game_id")

        # Parse timestamps
        start_timestamp = int(table.get("start", 0))
        end_timestamp = int(table.get("end", 0))

        # An unfinished table cannot represent a completed play.
        if not end_timestamp:
            return None

        play_date = datetime.fromtimestamp(end_timestamp).strftime("%Y-%m-%d")

        # Parse players
        player_names = table.get("player_names", "").split(",")
        scores = table.get("scores", "").split(",")
        ranks = table.get("ranks", "").split(",")

        def parse_integer(values, index):
            try:
                return int(values[index])
            except (IndexError, ValueError, TypeError):
                return None

        # Build player list with scores
        players = []
        player_details = []
        for i, name in enumerate(player_names):
            if name:
                player_info = name.strip()
                if i < len(scores) and scores[i]:
                    player_info += f" ({scores[i]})"
                players.append(player_info)
                player_details.append({
                    "name": name.strip(),
                    "score": parse_integer(scores, i),
                    "rank": parse_integer(ranks, i),
                })

        return {
            "id": table_id,
            "name": game_name,
            "game_id": game_id,
            "date": play_date,
            "players": players,
            "scores": scores,
            "ranks": ranks,
            "player_details": player_details,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp
        }

    def fetch_all_games(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all games from BGA with pagination.

        Args:
            limit: Maximum number of games to fetch (None for all)

        Returns:
            List of all game dictionaries
        """
        all_games = []
        page = 1
        consecutive_empty_pages = 0
        max_empty_pages = 3  # Stop after N consecutive empty pages

        print(f"Fetching games from BGA (player ID: {self.player_id})...")

        while True:
            print(f"  Fetching page {page}...", end=" ")

            response = self.fetch_games(page, update_stats=(page == 1))
            if not response:
                print("failed (no response)")
                break

            games = self.parse_games_json(response)

            tables = response.get("data", {}).get("tables", [])
            if not tables:
                consecutive_empty_pages += 1
                print(f"empty ({consecutive_empty_pages}/{max_empty_pages})")

                if consecutive_empty_pages >= max_empty_pages:
                    print("  No more games found")
                    break
            else:
                consecutive_empty_pages = 0
                all_games.extend(games)
                print(f"found {len(games)} completed games (total: {len(all_games)})")

                if limit and len(all_games) >= limit:
                    all_games = all_games[:limit]
                    print(f"  Reached limit of {limit} games")
                    break

            page += 1

        return all_games

    def get_game_info(self, game_name: str) -> Optional[Dict[str, Any]]:
        """Fetch game information from BGA gameDetails endpoint.

        Args:
            game_name: BGA internal game name (e.g., 'sevenwondersdice')

        Returns:
            Dictionary with game info including display_name and bgg_id
        """
        url = f"{self.BASE_URL}/gamelist/gamelist/gameDetails.html"

        # Set additional headers for POST request
        headers = {
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "origin": "https://boardgamearena.com",
            "referer": "https://boardgamearena.com/gamepanel",
        }

        data = {"game": game_name}

        try:
            response = self.session.post(url, data=data, headers=headers, timeout=15)
            response.raise_for_status()

            # Parse JSON response
            result = response.json()

            if result.get("status") == 1:
                game_data = result.get("results", {})

                return {
                    "name": game_name,
                    "display_name": game_data.get("game_name"),
                    "bgg_id": game_data.get("bgg_id"),
                    "designer": game_data.get("designer"),
                    "year": game_data.get("year"),
                    "publisher": game_data.get("publisher")
                }
            else:
                print(f"  Warning: BGA returned status {result.get('status')}")
                return None

        except json.JSONDecodeError as e:
            print(f"  Warning: JSON parse error: {e}")
            return None
        except requests.RequestException as e:
            print(f"  Warning: HTTP request error: {e}")
            return None
        except Exception as e:
            print(f"  Warning: Unexpected error: {e}")
            return None

    def parse_date(self, bga_date: str) -> Optional[str]:
        """Parse BGA date string to ISO format.

        Args:
            bga_date: BGA date string (already in YYYY-MM-DD from JSON)

        Returns:
            ISO date string (YYYY-MM-DD) or None if invalid
        """
        # Dates from JSON are already in YYYY-MM-DD format
        if bga_date and len(bga_date) == 10:
            return bga_date

        print(f"Warning: Invalid date format '{bga_date}'")
        return None
