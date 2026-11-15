"""BoardGameGeek form submission client."""

import requests
from secure_session import OriginSession
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import random
import time
from urllib.parse import quote


class BGGClient:
    """Client for submitting plays to BoardGameGeek."""

    BASE_URL = "https://boardgamegeek.com"

    def __init__(
        self,
        username: str,
        user_id: str,
        cookies: Dict[str, str],
        request_delay: float = 1.0,
        max_retries: int = 3
    ):
        """Initialize BGG client.

        Args:
            username: BGG username
            user_id: BGG user ID
            cookies: Dictionary of BGG session cookies
            request_delay: Delay between requests in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.username = username
        self.user_id = int(user_id)
        self.request_delay = request_delay
        self.max_retries = max_retries

        # Create session with cookies
        self.session = OriginSession("boardgamegeek.com", cookies)

        # Set required headers
        self.session.headers.update({
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en;q=0.5",
            "content-type": "application/json;charset=UTF-8",
            "dnt": "1",
            "origin": self.BASE_URL,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin"
        })

    def submit_play(
        self,
        game_id: int,
        play_date: str,
        players: List[Dict[str, Any]],
        duration_minutes: Optional[int] = None,
        game_slug: str = "game",
        winner_idx: Optional[int] = None
    ) -> Optional[int]:
        """Submit a play to BoardGameGeek.

        Args:
            game_id: BGG game ID
            play_date: Play date in YYYY-MM-DD format
            players: List of player dicts with 'name' and optional 'score'
            duration_minutes: Game duration in minutes
            game_slug: Game name slug for referer (can be anything)
            winner_idx: Index of winning player (if known)

        Returns:
            Positive BGG play ID if confirmed, otherwise None.
        """
        # Prepare payload
        payload = self._build_payload(
            game_id=game_id,
            play_date=play_date,
            players=players,
            duration_minutes=duration_minutes,
            winner_idx=winner_idx
        )

        # Set referer header
        self.session.headers["referer"] = f"{self.BASE_URL}/boardgame/{game_id}/{quote(game_slug, safe='')}"

        # A POST can have succeeded even when its response was lost. Never retry it.
        try:
            response = self.session.post(
                f"{self.BASE_URL}/geekplay.php", json=payload, timeout=15
            )
            time.sleep(self.request_delay)
            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError:
                    result = None
                if isinstance(result, dict) and not result.get("error"):
                    play_id = result.get("playid")
                    if not isinstance(play_id, bool) and str(play_id).isdigit() and int(play_id) > 0:
                        return int(play_id)
            print("  Submission outcome is uncertain; check BGG before retrying.")
        except requests.RequestException as e:
            print(f"  Submission outcome is uncertain ({e}); check BGG before retrying.")
        return None

    def _build_payload(
        self,
        game_id: int,
        play_date: str,
        players: List[Dict[str, Any]],
        duration_minutes: Optional[int] = None,
        winner_idx: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build JSON payload for play submission.

        Args:
            game_id: BGG game ID
            play_date: Play date in YYYY-MM-DD format (e.g., "2026-03-31")
            players: List of player dicts with 'name' and optional 'score'
            duration_minutes: Optional duration in minutes
            winner_idx: Optional index of winning player

        Returns:
            Dictionary payload for BGG API
        """
        # Parse play date
        play_date_obj = datetime.strptime(play_date, "%Y-%m-%d")

        # Convert to ISO datetime with timezone (BGG expects UTC midnight of previous day)
        # If play date is 2026-03-31, BGG expects "2026-03-30T23:00:00.000Z" for some timezones
        # We'll use the play date at midnight UTC
        iso_datetime = play_date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        iso_datetime_str = iso_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Calculate hours and minutes
        hours = 0
        minutes = duration_minutes or 0
        if duration_minutes:
            hours = duration_minutes // 60
            minutes = duration_minutes % 60

        # Build players array
        players_array = []

        for idx, player in enumerate(players):
            player_name = player['name']
            player_score = player.get('score')
            bgg_username = player.get('username')  # BGG username if known

            # Check if this is the logged-in user
            is_current_user = (player_name == self.username or bgg_username == self.username)

            player_obj = {
                "name": player_name,
                "selected": False
            }

            # Add username if known (for registered BGG users)
            if is_current_user:
                player_obj["username"] = self.username
                player_obj["userid"] = self.user_id
                player_obj["avatarfile"] = ""
                player_obj["avatar"] = False
            elif bgg_username:
                # Friend with BGG account
                player_obj["username"] = bgg_username
            else:
                # Anonymous player needs disambiguator
                player_obj["username"] = ""
                player_obj["disambiguator"] = random.random()

            # Add score if available
            if player_score is not None:
                player_obj["score"] = str(player_score)

            # Mark as winner if this is the winning player
            if player.get("win") or (winner_idx is not None and idx == winner_idx):
                player_obj["win"] = 1

            players_array.append(player_obj)

        # If no players, add current user
        if not players_array:
            players_array.append({
                "name": self.username,
                "username": self.username,
                "userid": self.user_id,
                "avatarfile": "",
                "avatar": False,
                "selected": False
            })

        # Build complete payload
        payload = {
            "players": players_array,
            "quantity": 1,
            "date": iso_datetime_str,
            "twitter": False,
            "bsky": False,
            "location": "BoardGameArena",  # Add location to indicate source
            "minutes": minutes,
            "hours": hours,
            "userfilter": "",
            "objecttype": "thing",
            "objectid": str(game_id),
            "playdate": play_date,
            "length": duration_minutes or 0,
            "ajax": 1,
            "action": "save"
        }

        return payload

    def delete_play(self, play_id: str) -> bool:
        """Delete a play from BoardGameGeek.

        Args:
            play_id: BGG play ID to delete

        Returns:
            True if deletion successful
        """
        payload = {
            "playid": str(play_id),
            "ajax": 1,
            "finalize": 1,
            "action": "delete"
        }

        try:
            response = self.session.post(
                f"{self.BASE_URL}/geekplay.php",
                json=payload,
                timeout=15
            )

            time.sleep(self.request_delay)

            if response.status_code == 200:
                return True
            else:
                print(f"  Delete failed: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"  Delete failed: {e}")
            return False

    def get_plays(self, username: Optional[str] = None, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch plays for a user from BGG.

        Args:
            username: BGG username (defaults to authenticated user)
            page: Page number

        Returns:
            List of play dictionaries
        """
        # Use geekplay.php endpoint with user ID
        url = f"{self.BASE_URL}/geekplay.php"
        params = {
            "userid": self.user_id,
            "redirect": 1,
            "action": "bydate",
            "subtype": "boardgame",
            "page": page
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            plays = []

            # BGG structure: date headers in <th> followed by play rows
            # Find all tables with class forum_table (there are multiple, we want the plays table)
            tables = soup.find_all('table', class_='forum_table')

            # The plays table is typically the last/largest one with date headers
            table = None
            for t in tables:
                # Look for a table that has date links
                if t.find('a', href=lambda x: x and '/plays/bydate/' in x):
                    table = t
                    break

            if not table:
                return plays

            rows = table.find_all('tr')
            current_date = None

            for row in rows:
                # Check if this is a date header row
                th = row.find('th')
                if th:
                    # Extract date from link like: /plays/bydate/user/Funi1234/start/2026-04-03/end/2026-04-03
                    date_link = th.find('a')
                    if date_link:
                        date_text = date_link.get_text(strip=True)
                        current_date = date_text
                    continue

                # This is a play row
                try:
                    # Extract game name - find all boardgame links and get the one with text
                    game_links = row.find_all('a', href=lambda x: x and '/boardgame/' in x)
                    game_link = None
                    game_name = None
                    for link in game_links:
                        text = link.get_text(strip=True)
                        if text:  # Skip empty links (like image thumbnails)
                            game_link = link
                            game_name = text
                            break

                    if not game_link or not game_name:
                        continue

                    # Extract BGG game ID from link
                    game_href = game_link.get('href', '')
                    game_id_match = game_href.split('/boardgame/')[1].split('/')[0] if '/boardgame/' in game_href else None

                    # Extract play ID from delete form
                    play_id = None
                    play_id_input = row.find('input', {'name': 'playid'})
                    if play_id_input:
                        play_id = play_id_input.get('value')

                    # Extract player count and location from td elements
                    tds = row.find_all('td')
                    player_count = None
                    location = None

                    if len(tds) >= 3:
                        # Second td is player count
                        player_count_text = tds[1].get_text(strip=True)
                        try:
                            player_count = int(player_count_text)
                        except ValueError:
                            pass

                        # Third td is location
                        location = tds[2].get_text(strip=True)

                    plays.append({
                        'play_id': play_id,
                        'game_id': game_id_match,
                        'game_name': game_name,
                        'date': current_date,
                        'player_count': player_count,
                        'location': location
                    })

                except Exception as e:
                    continue

            print(f"  Found {len(plays)} plays on page {page}")
            return plays

        except requests.RequestException as e:
            print(f"Error fetching plays: {e}")
            return []

    def test_connection(self) -> bool:
        """Test reachability of a public BGG profile (not authentication).

        Returns:
            True if the public profile is reachable
        """
        try:
            # Try to access a user profile page
            response = self.session.get(
                f"{self.BASE_URL}/user/{self.username}",
                timeout=10
            )

            if response.status_code == 200:
                return True
            else:
                print(f"BGG connection test failed: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"BGG connection test failed: {e}")
            return False
