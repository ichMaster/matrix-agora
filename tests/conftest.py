"""Every test runs with the agents' state redirected away from the live state/."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    from agents import config

    monkeypatch.setattr(config.AgentConfig, "memory_file",
                        property(lambda self: tmp_path / f"{self.localpart}.memory.md"))
    monkeypatch.setattr(config.AgentConfig, "state_file",
                        property(lambda self: tmp_path / f"{self.localpart}.json"))
