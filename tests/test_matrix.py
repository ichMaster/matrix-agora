"""v5.2 — the authenticated media download: the Bearer token, the cap, a malformed mxc (client.send faked)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from agents.matrix import download


class FakeContent:
    def __init__(self, body):
        self.body, self.asked = body, None

    async def read(self, n=-1):
        self.asked = n
        return self.body[:n] if n >= 0 else self.body


class FakeResp:
    def __init__(self, status=200, body=b"OggS", length=None):
        self.status, self.content, self.released = status, FakeContent(body), False
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def release(self):
        self.released = True


def client_with(resp):
    seen = {}

    async def send(method, path, data=None, headers=None):
        seen.update(method=method, path=path, headers=headers)
        return resp

    return SimpleNamespace(send=send, access_token="tok-123"), seen


def test_the_download_uses_the_authenticated_media_api():
    resp = FakeResp(body=b"OggS-voice")
    client, seen = client_with(resp)
    assert asyncio.run(download(client, "mxc://agora.lan/AbC_d-9", 1000)) == b"OggS-voice"
    assert seen == {"method": "GET", "path": "/_matrix/client/v1/media/download/agora.lan/AbC_d-9",
                    "headers": {"Authorization": "Bearer tok-123"}}
    assert resp.content.asked == 1001 and resp.released


@pytest.mark.parametrize("resp,why", [
    (FakeResp(status=404), "HTTP 404"),
    (FakeResp(length=5000), "5000 bytes over the cap"),
    (FakeResp(body=b"x" * 1500), "over the cap"),
])
def test_a_failed_or_oversized_download_is_none(caplog, resp, why):
    caplog.set_level(logging.INFO)
    client, _ = client_with(resp)
    assert asyncio.run(download(client, "mxc://agora.lan/abc", 1000)) is None
    assert why in caplog.text and "tok-123" not in caplog.text and resp.released


@pytest.mark.parametrize("mxc", ["https://evil/x", "mxc://agora.lan/../etc", "mxc://agora.lan/a/b", "", None])
def test_a_malformed_mxc_never_reaches_the_server(mxc):
    client, seen = client_with(FakeResp())
    assert asyncio.run(download(client, mxc, 1000)) is None and seen == {}
