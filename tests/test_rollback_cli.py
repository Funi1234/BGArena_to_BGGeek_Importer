import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner
from main import cli
from play_tracker import PlayTracker


class RollbackCliTests(unittest.TestCase):
    def test_preview_and_confirm_keep_uncertain_deletion_blocked(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'history.db'
            tracker = PlayTracker(path)
            tracker.begin_submission('10', 1, '2026-01-01', ['user'], None, 'Game')
            tracker.finish_submission('10', 'Game', 123, 'batch-a')
            config = SimpleNamespace(database_path=path, bgg_username='user', bgg_user_id='1',
                                     bgg_cookies={}, request_delay=0, max_retries=1)
            with patch('main.Config', return_value=config), patch('main.BGGClient') as client:
                runner = CliRunner()
                preview = runner.invoke(cli, ['rollback', 'batch-a'])
                self.assertEqual(preview.exit_code, 0, preview.output)
                self.assertIn('BGG play 123', preview.output)
                client.assert_not_called()
                result = runner.invoke(cli, ['rollback', 'batch-a', '--confirm'], input='y\n')
                self.assertEqual(result.exit_code, 0, result.output)
                client.return_value.delete_play.assert_called_once_with('123')
                self.assertEqual(tracker.table_status('10'), 'pending')
                runner.invoke(cli, ['rollback', 'batch-a', '--confirm'], input='y\n')
                client.return_value.delete_play.assert_called_once()
                result = runner.invoke(cli, ['resolve-rollback', '10', 'deleted'])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIsNone(tracker.table_status('10'))
