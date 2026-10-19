"""v5.2 — the authenticated media download: the Bearer token, the cap, a malformed mxc (client.send faked)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from agents.matrix import download


class FakeContent:
    """Like aiohttp's stream: one read returns at most what has arrived — here `chunk` bytes at a time."""

    def __init__(self, body, chunk=4):
        self.body, self.chunk, self.asked = body, chunk, []

    async def read(self, n=-1):
        self.asked.append(n)
        take = self.chunk if n < 0 else min(n, self.chunk)
        out, self.body = self.body[:take], self.body[take:]
        return out


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
    assert resp.content.asked[0] == 1001 and resp.released


def test_the_download_reads_to_the_end_not_the_first_chunk():
    """The v5.4 DoD: a 23.6 s voice came down as its first 13 s — one read returns only what has arrived."""
    voice = bytes(range(256)) * 400
    resp = FakeResp(body=voice)
    resp.content.chunk = 4096
    client, _ = client_with(resp)
    assert asyncio.run(download(client, "mxc://agora.lan/abc", 200_000)) == voice
    assert len(resp.content.asked) > 2 and all(n <= 200_001 for n in resp.content.asked)


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


@pytest.mark.parametrize("where", ["send", "read"])
def test_a_dropped_connection_is_a_failed_download_not_an_exception(caplog, where):
    """v5.2 review #1: the homeserver restarts mid-download — None, logged by type, never a dead task."""
    resp = FakeResp()

    async def boom(*a, **kw):
        raise ConnectionResetError("gone")

    if where == "read":
        resp.content.read = boom
        client, _ = client_with(resp)
    else:
        client = SimpleNamespace(send=boom, access_token="tok-123")
    assert asyncio.run(download(client, "mxc://agora.lan/abc", 1000)) is None
    assert "download failed: ConnectionResetError" in caplog.text
