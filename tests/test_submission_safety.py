import unittest
from unittest.mock import Mock
from tempfile import TemporaryDirectory
from pathlib import Path

import requests
from bgg_client import BGGClient
from play_tracker import PlayTracker


class SubmissionSafetyTests(unittest.TestCase):
    def test_unicode_game_slug_is_safe_in_referer_header(self):
        client = BGGClient('user', '1', {}, request_delay=0)
        response = Mock(status_code=200)
        response.json.return_value = {'playid': 123}
        client.session.post = Mock(return_value=response)
        self.assertEqual(client.submit_play(1, '2026-01-01', [], game_slug='arigatō'), 123)
        referer = client.session.headers['referer']
        self.assertIn('arigat%C5%8D', referer)
        referer.encode('ascii')

    def test_only_explicit_success_is_accepted_and_never_retries(self):
        for status, body, expected in [(200, {'success': True}, None),
                                       (200, {'playid': 123}, 123),
                                       (200, {'error': 'failed'}, None),
                                       (200, {}, None), (500, {}, None)]:
            with self.subTest(status=status, body=body):
                client = BGGClient('user', '1', {}, request_delay=0, max_retries=3)
                response = Mock(status_code=status)
                response.json.return_value = body
                client.session.post = Mock(return_value=response)
                self.assertEqual(client.submit_play(1, '2026-01-01', []), expected)
                client.session.post.assert_called_once()
        client = BGGClient('user', '1', {}, request_delay=0)
        client.session.post = Mock(side_effect=requests.Timeout())
        self.assertFalse(client.submit_play(1, '2026-01-01', []))
        client.session.post.assert_called_once()

    def test_table_identity_and_uncertain_reservation(self):
        with TemporaryDirectory() as directory:
            tracker = PlayTracker(Path(directory) / 'history.db')
            args = (1, '2026-01-01', ['user'], None, 'Game')
            self.assertTrue(tracker.begin_submission('10', *args))
            self.assertFalse(tracker.begin_submission('10', *args, force=True))
            self.assertEqual(tracker.table_status('10'), 'pending')
            self.assertTrue(tracker.begin_submission('11', *args))
            tracker.finish_submission('11', 'Game')
            self.assertFalse(tracker.begin_submission('11', *args))
            self.assertTrue(tracker.resolve_submission('10', 'retry'))
            self.assertTrue(tracker.begin_submission('10', *args))
            self.assertTrue(tracker.resolve_submission('10', 'submitted'))
            self.assertEqual(tracker.table_status('10'), 'submitted')
            self.assertFalse(tracker.begin_submission(None, *args))

    def test_legacy_records_are_conservatively_respected(self):
        with TemporaryDirectory() as directory:
            tracker = PlayTracker(Path(directory) / 'history.db')
            tracker.record_play(1, '2026-01-01', ['user'], None, 'Game')
            self.assertFalse(tracker.begin_submission('10', 1, '2026-01-01', ['user'], None, 'Game'))

    def test_rollback_requires_manual_resolution_and_blocks_resubmission(self):
        with TemporaryDirectory() as directory:
            tracker = PlayTracker(Path(directory) / 'history.db')
            args = (1, '2026-01-01', ['user'], None, 'Game')
            self.assertTrue(tracker.begin_submission('10', *args))
            tracker.finish_submission('10', 'Game', 123, 'batch-a')
            self.assertEqual(len(tracker.rollback_records('batch-a')), 1)
            self.assertEqual(tracker.rollback_records('other'), [])
            self.assertFalse(tracker.begin_rollback('bga:10', '999'))
            self.assertTrue(tracker.begin_rollback('bga:10', '123'))
            self.assertFalse(tracker.begin_rollback('bga:10', '123'))
            self.assertEqual(tracker.table_status('10'), 'pending')
            self.assertFalse(tracker.begin_submission('10', *args, force=True))
            self.assertTrue(tracker.resolve_rollback('10', 'present'))
            self.assertTrue(tracker.begin_rollback('bga:10', '123'))
            self.assertTrue(tracker.resolve_rollback('10', 'deleted'))
            self.assertEqual(tracker.rollback_records('batch-a'), [])
            self.assertTrue(tracker.begin_submission('10', *args))
