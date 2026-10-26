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
