import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bga_client import BGAClient
from bgg_client import BGGClient
from play_conversion import build_player_data


class PlayAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.bga = BGAClient('123', {}, request_delay=0)
        self.table = {'table_id': '1', 'game_name': 'game', 'start': '100',
                      'end': '200', 'player_names': 'Alice,Bob,Carol',
                      'scores': '2,8,8', 'ranks': '1,2,2'}
        self.config = SimpleNamespace(bga_username='Alice', bgg_username='A', player_mappings={})

    def test_rank_winners_and_ties_ignore_scores(self):
        self.table['ranks'] = '1,1,3'
        game = self.bga._parse_game_table(self.table)
        players = build_player_data(game, self.config)
        self.assertEqual([p.get('win', False) for p in players], [True, True, False])
        self.assertNotIn('duration', game)
        bgg = BGGClient.__new__(BGGClient)
        bgg.username, bgg.user_id = 'A', 1
        payload = bgg._build_payload(10, '2026-01-01', players)
        self.assertEqual([p.get('win', 0) for p in payload['players']], [1, 1, 0])
        self.assertEqual(payload['length'], 0)

    def test_unfinished_and_limit(self):
        unfinished = dict(self.table, end='0')
        self.assertIsNone(self.bga._parse_game_table(unfinished))
        self.bga.fetch_games = Mock(return_value={'status': 1, 'data': {'tables': [unfinished, self.table, self.table]}})
        games = self.bga.fetch_all_games(limit=1)
        self.assertEqual(len(games), 1)
        self.bga.fetch_games.assert_called_once()

    def test_missing_rank_does_not_guess(self):
        self.table['ranks'] = ''
        players = build_player_data(self.bga._parse_game_table(self.table), self.config)
        self.assertFalse(any(p.get('win') for p in players))


if __name__ == '__main__':
    unittest.main()
