"""Every test runs with the agents' state redirected away from the live state/. A test marked `canon` reads the
private canon (`agents/canon/`, gitignored since v5.9.1): it runs on the Mac, where the canon lives, and is skipped
where it is absent — CI."""

from pathlib import Path

import pytest

CANON = Path(__file__).resolve().parent.parent / "agents" / "canon"
HAS_CANON = (CANON / "common.md").is_file()


def pytest_configure(config):
    config.addinivalue_line("markers", "canon: reads the private canon in agents/canon/ (skipped where it is absent)")


def pytest_collection_modifyitems(config, items):
    if HAS_CANON:
        return
    skip = pytest.mark.skip(reason="agents/canon/ is private (gitignored): it lives on the Mac and the host")
    for item in items:
        if item.get_closest_marker("canon"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    from agents import config

    monkeypatch.setattr(config.AgentConfig, "memory_file",
                        property(lambda self: tmp_path / f"{self.localpart}.memory.md"))
    monkeypatch.setattr(config.AgentConfig, "state_file",
                        property(lambda self: tmp_path / f"{self.localpart}.json"))


@pytest.fixture(autouse=True)
def _no_network_fetchers(monkeypatch):
    """v5.11 (and v5.10 review #5): an agent built in a test never reaches Open-Meteo or Zaxid.net through its
    default fetchers. A test that forgets to pass a canned one fails here, even where the agent swallows the error."""
    from agents import agent

    reached = []

    async def weather(*_a, **_k):
        reached.append("weather")
        raise RuntimeError("a test reached the network: pass agent.weather_fetch")

    async def citynews(*_a, **_k):
        reached.append("citynews")
        raise RuntimeError("a test reached the network: pass agent.citynews_fetch")

    async def reading(*_a, **_k):  # v5.12: her reading's sources — Zaxid.net's pages and the Guardian
        reached.append("reading")
        raise RuntimeError("a test reached the network: pass Sources(fetch_json=…, fetch_text=…)")

    from agents import reading as reading_module

    monkeypatch.setattr(agent, "fetch_weather", weather)
    monkeypatch.setattr(agent, "fetch_citynews", citynews)
    monkeypatch.setattr(reading_module, "http_fetch", reading)
    monkeypatch.setattr(reading_module, "http_text", reading)
    yield
    assert not reached, f"a test reached the network through the default fetcher: {', '.join(reached)}"
