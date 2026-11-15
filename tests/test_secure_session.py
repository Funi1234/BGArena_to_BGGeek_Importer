"""Credential boundaries for authenticated HTTP sessions."""
import unittest

import requests
from requests.adapters import BaseAdapter
from requests.models import Response

from secure_session import OriginSession


class RedirectAdapter(BaseAdapter):
    def __init__(self, location):
        self.location = location
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        response = Response()
        response.status_code = 302
        response.headers['Location'] = self.location
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass


class OriginSessionTests(unittest.TestCase):
    def test_bgg_http_redirect_is_upgraded_only_for_same_host(self):
        session = OriginSession('boardgamegeek.com', {'session': 'secret'})
        response = Response()
        response.status_code = 302
        response.headers['Location'] = 'http://boardgamegeek.com/user/example?x=1'
        self.assertEqual(session.get_redirect_target(response),
                         'https://boardgamegeek.com/user/example?x=1')
        response.headers['Location'] = 'http://attacker.example/'
        self.assertEqual(session.get_redirect_target(response), 'http://attacker.example/')

    def test_cross_origin_redirect_never_sent(self):
        session = OriginSession('boardgamearena.com', {'session': 'secret'})
        session.headers['x-request-token'] = 'secret-token'
        adapter = RedirectAdapter('https://attacker.example/')
        session.mount('https://', adapter)
        with self.assertRaises(requests.exceptions.InvalidURL):
            session.get('https://boardgamearena.com/')
        self.assertEqual(len(adapter.requests), 1)

    def test_cookies_scoped_to_secure_origin(self):
        session = OriginSession('boardgamegeek.com', {'session': 'secret'})
        for url in ('https://attacker.example/', 'http://boardgamegeek.com/'):
            request = session.prepare_request(requests.Request('GET', url))
            self.assertNotIn('Cookie', request.headers)
            with self.assertRaises(requests.exceptions.InvalidURL):
                session.send(request)
        request = session.prepare_request(requests.Request('GET', 'https://boardgamegeek.com/'))
        self.assertEqual(request.headers['Cookie'], 'session=secret')


if __name__ == '__main__':
    unittest.main()
