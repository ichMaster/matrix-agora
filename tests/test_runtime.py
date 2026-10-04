import logging
import sys
from logging.handlers import RotatingFileHandler

import pytest

import agents.agent as agent_mod
from agents.runtime import LOG_BACKUPS, LOG_MAX_BYTES, acquire_lock, lock_holder, setup_logging


def test_a_second_instance_is_refused_until_the_first_releases(tmp_path):
    path = tmp_path / "state" / "ada.lock"
    first = acquire_lock(path)
    assert first is not None and lock_holder(path) == __import__("os").getpid()
    assert acquire_lock(path) is None  # another descriptor = another instance
    first.release()
    again = acquire_lock(path)
    assert again is not None
    again.release()


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for h in [h for h in root.handlers if h not in before]:
        root.removeHandler(h)
        h.close()


def test_logging_goes_to_console_and_a_rotating_file(tmp_path, clean_root_logger):
    file = setup_logging("ada", tmp_path / "logs")
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_agora", False)]
    rot = [h for h in ours if isinstance(h, RotatingFileHandler)]
    assert len(ours) == 2 and len(rot) == 1
    assert (rot[0].maxBytes, rot[0].backupCount) == (LOG_MAX_BYTES, LOG_BACKUPS) == (1_000_000, 3)
    logging.getLogger("agent").info("joined")
    rot[0].flush()
    assert file == tmp_path / "logs" / "ada.log" and "joined" in file.read_text(encoding="utf-8")
    assert logging.getLogger("nio").level == logging.WARNING  # no line per room event (v3.4 review #3)
    setup_logging("ada", tmp_path / "logs")  # idempotent: no duplicate handlers
    assert len([h for h in logging.getLogger().handlers if getattr(h, "_agora", False)]) == 2


def test_main_exits_on_a_held_lock_without_logging_in(tmp_path, monkeypatch, clean_root_logger):
    from tests.test_chronicle import CFG
    lock_path = tmp_path / "ada.lock"
    monkeypatch.setattr(type(CFG), "lock_file", property(lambda self: lock_path))
    monkeypatch.setattr(agent_mod, "load_config", lambda _: CFG)
    monkeypatch.setattr(agent_mod, "setup_logging", lambda name: None)
    monkeypatch.setattr(agent_mod, "Agent", lambda *a, **k: pytest.fail("must not start"))
    monkeypatch.setattr(sys, "argv", ["agent.py", "agents/ada.toml"])
    held = acquire_lock(lock_path)
    try:
        with pytest.raises(SystemExit) as exc:
            agent_mod.main()
        assert exc.value.code == 1
    finally:
        held.release()
