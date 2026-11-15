# BGA to BGG Play Sync

Automatically synchronize your game play history from Board Game Arena (BGA) to BoardGameGeek (BGG).

## Features

- 🎮 Fetch game history from Board Game Arena
- 🎯 Intelligent game mapping with fuzzy search
- 🔄 Local tracking of imported BGA table IDs
- 💾 Local caching of game mappings
- 🎨 Interactive CLI with progress tracking
- 🧪 Dry-run mode for testing

## Installation

### Using uv (Recommended)

1. Install [uv](https://github.com/astral-sh/uv) if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone or download this repository

3. Create your configuration file:
```bash
cp .env.example .env
```

That's it! `uv` will automatically manage dependencies when you run commands.

### Using pip (Alternative)

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create your configuration file:
```bash
cp .env.example .env
```

## Configuration

You need to extract cookies from your browser for both Board Game Arena and BoardGameGeek.

### Quick Setup

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Follow the detailed setup guide:**
   - See [SETUP_GUIDE.md](SETUP_GUIDE.md) for **detailed step-by-step instructions**
   - Or follow the quick version below

### Quick Version - Getting Cookies

**For BGA:**
1. Log in to [boardgamearena.com](https://boardgamearena.com)
2. Press F12 → Network tab
3. Go to your game stats page
4. Find request to `getGames.html`
5. Right-click → Copy as cURL
6. Extract cookies: `PHPSESSID`, `TournoiEnLigneid`, `TournoiEnLignetk`, `TournoiEnLigneidt`, `TournoiEnLignetkt`
7. Extract player ID from URL parameter

**For BGG:**
1. Log in to [boardgamegeek.com](https://boardgamegeek.com)
2. Press F12 → Network tab
3. Try logging a play on any game
4. Find request to `geekplay.php`
5. Right-click → Copy as cURL
6. Extract cookies: `bggusername`, `bggpassword`, `SessionID`, `_cfuvid`
7. Extract user ID from SessionID (numbers after 'u')

### .env File Format

```env
# Board Game Arena
BGA_PLAYER_ID=your_player_id_here
BGA_USERNAME=your_bga_username_here
BGA_COOKIES={"PHPSESSID": "xxx", "TournoiEnLigneid": "xxx", "TournoiEnLignetk": "xxx", "TournoiEnLigneidt": "xxx", "TournoiEnLignetkt": "xxx"}

# BoardGameGeek
BGG_USERNAME=your_bgg_username_here
BGG_USER_ID=your_bgg_user_id_here
BGG_COOKIES={"bggusername": "your_bgg_username_here", "bggpassword": "xxx", "SessionID": "xxx", "_cfuvid": "xxx"}
```

**📖 For detailed instructions, see [SETUP_GUIDE.md](SETUP_GUIDE.md)**

## Usage

There are three main workflows depending on your needs:

### Workflow 1: Full Sync

Inspect existing BGG plays, then sync BGA plays:

```bash
uv run main.py full-sync
```

BGG's play listing does not provide reliable BGA table IDs, so existing BGG plays cannot be automatically matched to BGA plays. Check your BGG history before syncing to avoid importing plays already logged there. The local database prevents repeat submissions made by this tool.

**Options:**
- `--dry-run`: Preview what would be submitted
- `--limit N`: Limit BGA plays to sync
- `--force`: Ignore legacy fingerprints; tracked table IDs remain protected

**Example:**
```bash
# First time setup - import BGG history and sync BGA plays
uv run main.py full-sync --dry-run
```

### Workflow 2: Import from BGG Only

Inspect your existing BGG plays (no BGA sync):

```bash
uv run main.py import-bgg
```

**Options:**
- `--limit N`: Limit pages to fetch from BGG

The listing is informational; it does not mark BGA tables as already submitted.

### Workflow 3: Sync from BGA to BGG

Sync plays from BGA to BGG without importing BGG history first:

```bash
uv run main.py sync
```

**Options:**
- `--dry-run`: Preview actions without submitting
- `--limit N`: Process only first N plays
- `--force`: Ignore legacy fingerprints; tracked table IDs remain protected

**Examples:**
```bash
# Test run
uv run main.py sync --dry-run --limit 10

# Sync first 50 plays
uv run main.py sync --limit 50

# Force re-submit all plays
uv run main.py sync --force  # Ignore legacy fingerprints
```

### Game Mapping

The first time a BGA game is encountered, you'll be prompted to map it to a BGG game:

```
Searching BGG for: 'Ark Nova'

Top matches:
  1. Ark Nova (2021) - ID: 342942 - Match: 100% ✓ HIGH
  2. Ark Nova: Marine Worlds (2023) - ID: 392614 - Match: 78%
  3. Enter custom BGG ID
  4. Skip this game

Select option (1-4):
```

**Manual mapping:**
```bash
uv run main.py map "Ark Nova"
```

### View Statistics

```bash
# Show all game mappings
uv run main.py show-mappings

# Show submission statistics
uv run main.py show-stats
```

### Reset Data

```bash
# Clear all game mappings
uv run main.py reset-mappings

# Clear submission history (allows re-submitting all plays)
uv run main.py reset-history
```

> **Note:** If using pip instead of uv, replace `uv run main.py` with `python main.py` in all commands.

## How It Works

1. **Fetch from BGA**: Retrieves your game history using BGA's internal API
2. **Map Games**: First-time games are mapped to BGG through interactive search
3. **Check Local History**: Skips BGA tables already tracked by this installation
4. **Transform Data**: Converts BGA play data to BGG's expected format
5. **Submit to BGG**: Posts plays to BGG via their web form endpoint
6. **Track Submissions**: Records successful submissions to prevent duplicates

Only a response with a positive BGG play ID is treated as confirmed; other responses are uncertain, including a generic success flag. If a submission has an uncertain outcome, check the play on BGG before continuing. The table stays blocked, including with `--force`. After checking, run `uv run main.py resolve-submission TABLE_ID submitted` if the play exists, or `uv run main.py resolve-submission TABLE_ID retry` if it does not. A lost database or resetting history removes this protection.

### Roll back an import batch

New confirmed submissions record their BGG play IDs and an import batch ID. Run `uv run main.py rollback` to list available plays and batches, then `uv run main.py rollback BATCH_ID` to preview one batch. To request deletion of its listed plays, run `uv run main.py rollback BATCH_ID --confirm` and answer the confirmation prompt.

Deletion requests are not automatically verified. For each pending play, check BGG, then run `uv run main.py resolve-rollback TABLE_ID deleted` if it is gone, or `uv run main.py resolve-rollback TABLE_ID present` if it remains. A pending deletion blocks resubmission. Resolving it as deleted removes the local submission record, allowing a later sync to import it again. Plays imported before BGG play IDs were recorded, including manually resolved submissions, cannot be rolled back with this command. Back up the local database; resetting history removes rollback records. Existing tracked table IDs cannot be overwritten with `--force` because doing so would lose their rollback information.

## Data Storage

All data is stored locally in a SQLite database at `~/.bga2bgg/data.db`:

- **Game Mappings**: BGA game name → BGG game ID
- **Submitted Plays**: BGA table IDs and submission status to prevent repeat submissions

## Troubleshooting

### "Configuration errors: BGA_COOKIES not set"

Make sure you've copied `.env.example` to `.env` and filled in your cookie values.

### "BGG connection failed"

Your BGG cookies may have expired. Re-copy them from your browser following the configuration steps above.

### "No games found on BGA"

1. Check that your `BGA_PLAYER_ID` is correct
2. Verify your BGA cookies are still valid
3. Try re-copying the cookies from your browser

### Plays not appearing on BGG

1. Check your BGG profile to verify the plays were submitted
2. Try a dry run first: `python main.py sync --dry-run --limit 1`
3. Check that the game mapping is correct: `python main.py show-mappings`

### Rate Limiting

The tool includes automatic rate limiting (1 second delay between requests by default). You can adjust this by creating a `config.yaml` file:

```bash
cp config.yaml.example config.yaml
```

Then edit `config.yaml`:

```yaml
request_delay: 2  # Increase to 2 seconds between requests
```

## Advanced Configuration

Create a `config.yaml` file from the example template:

```bash
cp config.yaml.example config.yaml
```

Then customize the settings:

```yaml
# Database location
database_path: ~/.bga2bgg/data.db

# Sync settings
dry_run: false
auto_confirm_high_confidence: true  # Auto-map games with >95% match

# Rate limiting
request_delay: 1
max_retries: 3
retry_backoff: 2

# Logging
log_level: INFO
```

## Limitations

- **BGA API**: Uses unofficial endpoints that may change
- **Cookie Expiration**: Cookies expire and need to be refreshed periodically
- **Game Mapping**: Some games may require manual mapping if names differ significantly
- **Date Formats**: BGA date parsing may need adjustment for different locales
- **Duplicate Detection**: Uses BGA table IDs for new submissions. Legacy records are matched conservatively by their old fingerprint, which can suppress a distinct play. Existing BGG plays cannot be matched reliably to BGA tables.
- **Abandoned Games**: Tables without an end time are skipped, but completed tables that were abandoned cannot currently be identified reliably.

## Privacy & Security

- Cookies in `.env` grant access to your accounts. Keep the file private, do not share it, and restrict access (on Unix: `chmod 600 .env`). `.env` and `.env.*` are ignored by git, but gitignore does not protect already tracked files or backups. The BGG connection check only tests a public page; it does not verify authentication.
- No data is sent to third parties
- All operations are local or direct to BGA/BGG

## License

This project is licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later).

This means you are free to use, modify, and distribute this software, but any derivative works must also be released under the GPL-3.0 license. See the [LICENSE](LICENSE) file for full details.

## Disclaimer

This tool is unofficial and not affiliated with Board Game Arena or BoardGameGeek. It automates actions you could do manually through their websites.

**Important:** Web scraping and automation may violate Board Game Arena's Terms of Service. Use responsibly and consider the impact on their servers.
