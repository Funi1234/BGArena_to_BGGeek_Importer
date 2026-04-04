#!/usr/bin/env python3
"""BGA to BGG Play Sync - Main CLI application."""

import click
import sys
import time
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from config import Config
from bga_client import BGAClient
from bgg_client import BGGClient
from game_mapper import GameMapper
from play_tracker import PlayTracker


@click.group()
def cli():
    """BGA to BGG Play Sync - Synchronize your Board Game Arena plays to BoardGameGeek."""
    pass


@cli.command()
@click.option('--dry-run', is_flag=True, help='Preview actions without submitting to BGG')
@click.option('--limit', type=int, help='Maximum number of plays to process')
@click.option('--force', is_flag=True, help='Re-submit plays even if already submitted')
def sync(dry_run: bool, limit: Optional[int], force: bool):
    """Sync plays from BGA to BGG."""

    # Load configuration
    try:
        config = Config()
        config.ensure_database_directory()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    # Override dry-run from config if specified
    if dry_run:
        config.dry_run = True

    # Initialize clients
    click.echo("🔧 Initializing clients...")

    bga = BGAClient(
        player_id=config.bga_player_id,
        cookies=config.bga_cookies,
        request_delay=config.request_delay
    )

    bgg = BGGClient(
        username=config.bgg_username,
        user_id=config.bgg_user_id,
        cookies=config.bgg_cookies,
        request_delay=config.request_delay,
        max_retries=config.max_retries
    )

    # Test BGG connection
    click.echo("🔌 Testing BGG connection...")
    if not bgg.test_connection():
        click.echo("❌ BGG connection failed. Please check your cookies.", err=True)
        sys.exit(1)
    click.echo("✅ BGG connection successful")

    # Initialize database components
    mapper = GameMapper(config.database_path, config.auto_confirm_high_confidence, config.bgg_cookies, bga)
    tracker = PlayTracker(config.database_path)

    # Fetch games from BGA
    click.echo(f"\n📥 Fetching games from BGA...")
    games = bga.fetch_all_games(limit=limit)

    if not games:
        click.echo("❌ No games found on BGA", err=True)
        sys.exit(1)

    click.echo(f"✅ Found {len(games)} plays on BGA\n")

    # Process each game
    stats = {
        "submitted": 0,
        "skipped_duplicate": 0,
        "skipped_no_mapping": 0,
        "failed": 0
    }

    with tqdm(games, desc="Processing plays", unit="play") as pbar:
        for game in pbar:
            pbar.set_description(f"Processing: {game['name'][:30]}")

            # Parse date
            play_date = bga.parse_date(game['date']) if game['date'] else None
            if not play_date:
                click.echo(f"\n⚠️  Skipping {game['name']}: Invalid date {game['date']}")
                stats["failed"] += 1
                continue

            # Get or create game mapping
            mapping = mapper.get_mapping(game['name'])

            if not mapping:
                # Interactive mapping
                click.echo(f"\n")  # New line for interactive prompt
                mapping = mapper.interactive_map(game['name'])

                if mapping:
                    mapper.save_mapping(game['name'], mapping[0], mapping[1])
                    click.echo(f"💾 Saved mapping: '{game['name']}' → '{mapping[1]}' (BGG ID: {mapping[0]})\n")
                else:
                    click.echo(f"⏭️  Skipped mapping for '{game['name']}'")
                    stats["skipped_no_mapping"] += 1
                    continue

            bgg_id, bgg_name = mapping

            # Get players and map BGA username to BGG username
            # Also extract scores from player names
            bga_players = game.get('players', [])

            # Parse players with scores: "SnowSnep (63)" -> {name: "SnowSnep", score: 63}
            player_data = []
            for player_str in bga_players:
                # Extract name and score
                if '(' in player_str:
                    parts = player_str.split('(')
                    player_name = parts[0].strip()
                    score_str = parts[1].rstrip(')').strip()
                    # Handle negative scores and non-numeric values
                    try:
                        score = int(score_str)
                    except ValueError:
                        score = None
                else:
                    player_name = player_str.strip()
                    score = None

                # Map BGA username to BGG username
                bgg_username = None
                if player_name == config.bga_username:
                    # Current user
                    mapped_player_name = config.bgg_username
                    bgg_username = config.bgg_username
                elif player_name in config.player_mappings:
                    # Mapped friend
                    mapped_player_name = config.player_mappings[player_name]
                    bgg_username = mapped_player_name  # Assume mapped name is their BGG username
                else:
                    # No mapping, use BGA name as-is
                    mapped_player_name = player_name

                player_data.append({
                    'name': mapped_player_name,
                    'username': bgg_username,
                    'score': score
                })

            # Ensure user is in the list (should already be there from BGA)
            if not any(p['name'] == config.bgg_username for p in player_data):
                player_data.insert(0, {'name': config.bgg_username, 'score': None})

            # Determine winner (highest score)
            # Find player with highest score
            max_score = None
            winner_idx = None
            for idx, p in enumerate(player_data):
                if p['score'] is not None:
                    if max_score is None or p['score'] > max_score:
                        max_score = p['score']
                        winner_idx = idx

            # Check for duplicate (includes duration to distinguish multiple plays on same day)
            player_names = [p['name'] for p in player_data]
            duration = game.get('duration')
            if not force and tracker.is_duplicate(bgg_id, play_date, player_names, duration):
                stats["skipped_duplicate"] += 1
                continue

            # Submit to BGG
            if config.dry_run:
                score_info = f" (scores: {', '.join([str(p['score']) for p in player_data])})" if any(p['score'] for p in player_data) else ""
                winner_info = f" - Winner: {player_data[winner_idx]['name']}" if winner_idx is not None else ""
                click.echo(f"\n[DRY RUN] Would submit: {bgg_name} on {play_date} with {len(player_data)} players{score_info}{winner_info}")
                stats["submitted"] += 1
            else:
                success = bgg.submit_play(
                    game_id=bgg_id,
                    play_date=play_date,
                    players=player_data,
                    duration_minutes=game.get('duration'),
                    game_slug=bgg_name.lower().replace(' ', '-'),
                    winner_idx=winner_idx
                )

                if success:
                    tracker.record_play(bgg_id, play_date, player_names, duration, game['name'])
                    stats["submitted"] += 1
                else:
                    click.echo(f"\n❌ Failed to submit: {bgg_name} on {play_date}")
                    stats["failed"] += 1

    # Print summary
    click.echo(f"\n📊 Summary:")
    click.echo(f"  ✅ Submitted: {stats['submitted']}")
    click.echo(f"  ⏭️  Skipped (duplicates): {stats['skipped_duplicate']}")
    click.echo(f"  ⏭️  Skipped (no mapping): {stats['skipped_no_mapping']}")
    click.echo(f"  ❌ Failed: {stats['failed']}")

    if config.dry_run:
        click.echo(f"\n💡 This was a dry run. Use without --dry-run to actually submit plays.")


@cli.command()
@click.argument('bga_name')
def map(bga_name: str):
    """Manually map a BGA game to BGG."""

    try:
        config = Config()
        config.ensure_database_directory()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    mapper = GameMapper(config.database_path, config.auto_confirm_high_confidence, config.bgg_cookies, None)

    # Check if already mapped
    existing = mapper.get_mapping(bga_name)
    if existing:
        click.echo(f"ℹ️  '{bga_name}' is already mapped to '{existing[1]}' (ID: {existing[0]})")
        overwrite = click.confirm("Do you want to create a new mapping?", default=False)
        if not overwrite:
            return

    # Interactive mapping
    mapping = mapper.interactive_map(bga_name)

    if mapping:
        mapper.save_mapping(bga_name, mapping[0], mapping[1])
        click.echo(f"✅ Saved mapping: '{bga_name}' -> '{mapping[1]}' (ID: {mapping[0]})")
    else:
        click.echo("❌ Mapping cancelled")


@cli.command()
def show_mappings():
    """Show all game mappings."""

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    mapper = GameMapper(config.database_path)
    mappings = mapper.get_all_mappings()

    if not mappings:
        click.echo("No game mappings found")
        return

    click.echo(f"\n📋 Game Mappings ({len(mappings)}):\n")
    for bga_name, bgg_id, bgg_name in mappings:
        click.echo(f"  {bga_name} → {bgg_name} (ID: {bgg_id})")


@cli.command()
def show_stats():
    """Show submission statistics."""

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    tracker = PlayTracker(config.database_path)
    stats = tracker.get_stats()

    click.echo(f"\n📊 Submission Statistics:\n")
    click.echo(f"  Total plays submitted: {stats['total_plays']}")

    if stats['top_games']:
        click.echo(f"\n  Top games:")
        for game in stats['top_games']:
            click.echo(f"    {game['game']}: {game['count']} plays")

    if stats['recent_plays']:
        click.echo(f"\n  Recent submissions:")
        for play in stats['recent_plays']:
            click.echo(f"    {play['game']} on {play['play_date']}")


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to reset all mappings?')
def reset_mappings():
    """Clear all game mappings (WARNING: cannot be undone)."""

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    mapper = GameMapper(config.database_path)
    count = mapper.clear_all()

    click.echo(f"✅ Deleted {count} game mappings")


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to reset submission history?')
def reset_history():
    """Clear submission history (WARNING: cannot be undone)."""

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    tracker = PlayTracker(config.database_path)
    count = tracker.clear_all()

    click.echo(f"✅ Deleted {count} submission records")


@cli.command()
@click.option('--dry-run', is_flag=True, default=True, help='Preview deletions without actually deleting')
@click.option('--confirm', is_flag=True, help='Actually delete plays (skips dry-run)')
@click.option('--player-name', required=True, help='Player name to search for in plays (e.g., old BGA username)')
def cleanup_plays(dry_run: bool, confirm: bool, player_name: str):
    """Delete BGG plays containing a specific player name (e.g., old BGA username).

    By default runs in dry-run mode. Use --confirm to actually delete.
    """

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    # Override dry-run if confirm is set
    if confirm:
        dry_run = False

    click.echo(f"🔍 Searching for plays containing player '{player_name}'...")
    click.echo("⚠️  Note: BGG play fetching via web scraping may not be reliable")
    click.echo(f"   Consider manually reviewing plays at: https://boardgamegeek.com/plays/byuser/user/{config.bgg_username}\n")

    # For now, show manual instructions since BGG play fetching is complex
    click.echo("Manual cleanup steps:")
    click.echo(f"1. Go to https://boardgamegeek.com/plays/byuser/user/{config.bgg_username}")
    click.echo(f"2. Filter plays containing '{player_name}'")
    click.echo("3. Note the play IDs you want to delete")
    click.echo("4. Use this command to delete specific play IDs:\n")
    click.echo("   uv run main.py delete-play <play_id> --confirm\n")


@cli.command()
@click.argument('play_id')
@click.option('--confirm', is_flag=True, help='Actually delete the play')
def delete_play(play_id: str, confirm: bool):
    """Delete a specific BGG play by ID."""

    try:
        config = Config()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    bgg = BGGClient(
        username=config.bgg_username,
        user_id=config.bgg_user_id,
        cookies=config.bgg_cookies,
        request_delay=config.request_delay,
        max_retries=config.max_retries
    )

    if not confirm:
        click.echo(f"⚠️  DRY RUN: Would delete play ID {play_id}")
        click.echo("   Use --confirm to actually delete")
        return

    click.echo(f"🗑️  Deleting play ID {play_id}...")
    success = bgg.delete_play(play_id)

    if success:
        click.echo(f"✅ Successfully deleted play {play_id}")
    else:
        click.echo(f"❌ Failed to delete play {play_id}", err=True)


@cli.command()
@click.option('--dry-run', is_flag=True, help='Preview actions without actually submitting to BGG')
@click.option('--limit', type=int, help='Maximum number of plays to process')
@click.option('--force', is_flag=True, help='Re-submit plays even if already submitted')
def full_sync(dry_run: bool, limit: Optional[int], force: bool):
    """Full sync: Import BGG plays to local DB, then sync BGA plays to BGG.

    This is the recommended workflow to prevent duplicates:
    1. Import existing plays from BGG into local database
    2. Sync new plays from BGA to BGG (skipping duplicates)
    """

    try:
        config = Config()
        config.ensure_database_directory()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    # Override dry-run from config if specified
    if dry_run:
        config.dry_run = True

    click.echo("🔄 Full Sync: BGG → Local → BGA → BGG")
    click.echo("=" * 60)

    # Step 1: Import from BGG
    click.echo("\n📥 Step 1/2: Importing existing plays from BGG...")
    click.echo("⚠️  Note: This may take a while with rate limiting\n")

    bgg = BGGClient(
        username=config.bgg_username,
        user_id=config.bgg_user_id,
        cookies=config.bgg_cookies,
        request_delay=config.request_delay,
        max_retries=config.max_retries
    )

    tracker = PlayTracker(config.database_path)

    # Import from BGG (limited pages for performance)
    bgg_imported = 0
    bgg_page = 1
    bgg_page_limit = 10  # Reasonable default to not take forever

    while bgg_page <= bgg_page_limit:
        plays = bgg.get_plays(config.bgg_username, page=bgg_page)
        if not plays:
            break

        for play in plays:
            game_id = play.get('game_id')
            game_name = play.get('game_name')
            play_date = play.get('date')
            player_count = play.get('player_count', 0)

            if not game_id or not game_name or not play_date:
                continue

            try:
                bgg_id = int(game_id)
            except (ValueError, TypeError):
                continue

            if not player_count or player_count < 1:
                player_count = 1

            players = [config.bgg_username]
            for i in range(1, player_count):
                players.append(f"Player{i}")

            # Parse date
            try:
                from datetime import datetime
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        parsed_date = datetime.strptime(play_date, fmt)
                        play_date_iso = parsed_date.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    continue
            except Exception:
                continue

            if not tracker.is_duplicate(bgg_id, play_date_iso, players):
                tracker.record_play(bgg_id, play_date_iso, players, duration=None, bga_game_name=None)
                bgg_imported += 1

        bgg_page += 1
        time.sleep(config.request_delay)

    click.echo(f"✅ Step 1 Complete: Imported {bgg_imported} plays from BGG\n")

    # Step 2: Sync from BGA to BGG
    click.echo("📥 Step 2/2: Syncing plays from BGA to BGG...\n")

    bga = BGAClient(
        player_id=config.bga_player_id,
        cookies=config.bga_cookies,
        request_delay=config.request_delay
    )

    # Test BGG connection
    if not bgg.test_connection():
        click.echo("❌ BGG connection failed. Please check your cookies.", err=True)
        sys.exit(1)

    mapper = GameMapper(config.database_path, config.auto_confirm_high_confidence, config.bgg_cookies, bga)

    # Fetch games from BGA
    games = bga.fetch_all_games(limit=limit)

    if not games:
        click.echo("❌ No games found on BGA", err=True)
        sys.exit(1)

    click.echo(f"Found {len(games)} plays on BGA\n")

    # Process BGA plays (same logic as sync command)
    stats = {
        "submitted": 0,
        "skipped_duplicate": 0,
        "skipped_no_mapping": 0,
        "failed": 0
    }

    with tqdm(games, desc="Processing plays", unit="play") as pbar:
        for game in pbar:
            pbar.set_description(f"Processing: {game['name'][:30]}")

            play_date = bga.parse_date(game['date']) if game['date'] else None
            if not play_date:
                stats["failed"] += 1
                continue

            mapping = mapper.get_mapping(game['name'])
            if not mapping:
                click.echo(f"\n")
                mapping = mapper.interactive_map(game['name'])
                if mapping:
                    mapper.save_mapping(game['name'], mapping[0], mapping[1])
                    click.echo(f"💾 Saved mapping: '{game['name']}' → '{mapping[1]}' (BGG ID: {mapping[0]})\n")
                else:
                    click.echo(f"⏭️  Skipped mapping for '{game['name']}'")
                    stats["skipped_no_mapping"] += 1
                    continue

            bgg_id, bgg_name = mapping
            bga_players = game.get('players', [])

            player_data = []
            for player_str in bga_players:
                if '(' in player_str:
                    parts = player_str.split('(')
                    player_name = parts[0].strip()
                    score_str = parts[1].rstrip(')').strip()
                    try:
                        score = int(score_str)
                    except ValueError:
                        score = None
                else:
                    player_name = player_str.strip()
                    score = None

                bgg_username = None
                if player_name == config.bga_username:
                    mapped_player_name = config.bgg_username
                    bgg_username = config.bgg_username
                elif player_name in config.player_mappings:
                    mapped_player_name = config.player_mappings[player_name]
                    bgg_username = mapped_player_name
                else:
                    mapped_player_name = player_name

                player_data.append({
                    'name': mapped_player_name,
                    'username': bgg_username,
                    'score': score
                })

            if not any(p['name'] == config.bgg_username for p in player_data):
                player_data.insert(0, {'name': config.bgg_username, 'score': None})

            max_score = None
            winner_idx = None
            for idx, p in enumerate(player_data):
                if p['score'] is not None:
                    if max_score is None or p['score'] > max_score:
                        max_score = p['score']
                        winner_idx = idx

            player_names = [p['name'] for p in player_data]
            duration = game.get('duration')

            if not force and tracker.is_duplicate(bgg_id, play_date, player_names, duration):
                stats["skipped_duplicate"] += 1
                continue

            if config.dry_run:
                stats["submitted"] += 1
            else:
                success = bgg.submit_play(
                    game_id=bgg_id,
                    play_date=play_date,
                    players=player_data,
                    duration_minutes=duration,
                    game_slug=bgg_name.lower().replace(' ', '-'),
                    winner_idx=winner_idx
                )

                if success:
                    tracker.record_play(bgg_id, play_date, player_names, duration, game['name'])
                    stats["submitted"] += 1
                else:
                    stats["failed"] += 1

    click.echo(f"\n" + "=" * 60)
    click.echo(f"📊 Full Sync Complete!")
    click.echo(f"  BGG Import: {bgg_imported} plays")
    click.echo(f"  BGA Sync: {stats['submitted']} submitted, {stats['skipped_duplicate']} duplicates, {stats['failed']} failed")

    if config.dry_run:
        click.echo(f"\n💡 This was a dry run. Use without --dry-run to actually submit plays.")


@cli.command()
@click.option('--limit', type=int, help='Maximum number of pages to fetch')
def import_bgg(limit: Optional[int]):
    """Import existing BGG plays into local database.

    Use this to populate your local database with plays already on BGG.
    This prevents re-submitting duplicates when you sync from BGA.
    """

    try:
        config = Config()
        config.ensure_database_directory()
    except ValueError as e:
        click.echo(f"❌ Configuration error:\n{e}", err=True)
        sys.exit(1)

    click.echo("📥 Importing plays from BGG to local database...")
    click.echo("⚠️  Note: This may be blocked by Cloudflare protection\n")

    bgg = BGGClient(
        username=config.bgg_username,
        user_id=config.bgg_user_id,
        cookies=config.bgg_cookies,
        request_delay=config.request_delay,
        max_retries=config.max_retries
    )

    mapper = GameMapper(config.database_path, config.auto_confirm_high_confidence, config.bgg_cookies, None)
    tracker = PlayTracker(config.database_path)

    page = 1
    total_imported = 0
    total_skipped = 0

    while True:
        if limit and page > limit:
            break

        click.echo(f"📄 Fetching page {page}...")
        plays = bgg.get_plays(config.bgg_username, page=page)

        if not plays:
            click.echo("  No more plays found")
            break

        for play in plays:
            game_id = play.get('game_id')
            game_name = play.get('game_name')
            play_date = play.get('date')
            player_count = play.get('player_count', 0)

            if not game_id or not game_name or not play_date:
                total_skipped += 1
                continue

            # Convert game_id to int
            try:
                bgg_id = int(game_id)
            except (ValueError, TypeError):
                total_skipped += 1
                continue

            # Generate placeholder player list (we don't have actual names from this BGG page)
            # Use player count to generate generic player names
            if not player_count or player_count < 1:
                player_count = 1  # Default to solo if count is missing

            players = [config.bgg_username]  # User is always first
            for i in range(1, player_count):
                players.append(f"Player{i}")  # Generic names for other players

            # Parse date (BGG format: "YYYY-MM-DD")
            try:
                from datetime import datetime
                # Try common date formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        parsed_date = datetime.strptime(play_date, fmt)
                        play_date_iso = parsed_date.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    total_skipped += 1
                    continue
            except Exception:
                total_skipped += 1
                continue

            # Check if already in database
            if tracker.is_duplicate(bgg_id, play_date_iso, players):
                # Silently skip duplicates (already in DB)
                total_skipped += 1
                continue

            # Import into database
            tracker.record_play(bgg_id, play_date_iso, players, duration=None, bga_game_name=None)
            total_imported += 1
            # Show progress every 10 imports
            if total_imported % 10 == 0:
                click.echo(f"  ✅ Imported {total_imported} plays so far...")

        page += 1
        time.sleep(config.request_delay)

    click.echo(f"\n📊 BGG Import Complete:")
    click.echo(f"  ✅ Imported: {total_imported} plays")
    click.echo(f"  ⏭️  Skipped: {total_skipped} plays (already in database)")
    click.echo(f"\n💡 Tip: Run 'uv run main.py sync' to sync plays from BGA to BGG")


if __name__ == '__main__':
    cli()
