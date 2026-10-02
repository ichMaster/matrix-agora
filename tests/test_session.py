import json
import stat

from agents.session import load_session, save_session


def test_round_trip_atomic_and_private(tmp_path):
    p = tmp_path / "state" / "ada.json"
    save_session(p, "@ada:agora.lan", "DEV1", "secret-token")
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600
    assert not p.with_suffix(".tmp").exists()  # atomic: no temp file left behind
    s = load_session(p)
    assert s == {"user_id": "@ada:agora.lan", "device_id": "DEV1", "access_token": "secret-token"}


def test_missing_file_means_password_login(tmp_path):
    assert load_session(tmp_path / "ada.json") is None


def test_corrupt_file_means_password_login(tmp_path):
    p = tmp_path / "ada.json"
    p.write_text("{not json")
    assert load_session(p) is None


def test_incomplete_file_means_password_login(tmp_path):
    p = tmp_path / "ada.json"
    p.write_text(json.dumps({"user_id": "@ada:agora.lan", "device_id": ""}))
    assert load_session(p) is None
