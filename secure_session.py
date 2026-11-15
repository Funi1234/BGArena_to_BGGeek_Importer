"""HTTP sessions restricted to a single HTTPS origin."""

from urllib.parse import urlsplit, urlunsplit

import requests


class OriginSession(requests.Session):
    """Keep cookies and sensitive headers on their intended HTTPS host."""

    def __init__(self, host, cookies):
        super().__init__()
        self.host = host
        for name, value in cookies.items():
            self.cookies.set(name, value, domain=host, path="/", secure=True)

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        try:
            allowed = (url.scheme == "https" and url.hostname == self.host
                       and url.port in (None, 443) and url.username is None
                       and url.password is None)
        except ValueError:
            allowed = False
        if not allowed:
            raise requests.exceptions.InvalidURL("Request outside the permitted HTTPS origin")
        return super().send(request, **kwargs)

    def get_redirect_target(self, response):
        target = super().get_redirect_target(response)
        if target and self.host == "boardgamegeek.com":
            url = urlsplit(target)
            try:
                if (url.scheme == "http" and url.hostname == self.host
                        and url.port in (None, 80) and url.username is None
                        and url.password is None):
                    target = urlunsplit(("https", self.host, url.path, url.query, url.fragment))
            except ValueError:
                pass
        return target
