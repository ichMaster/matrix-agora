"""v8 (synchronization step 2, 2026-11-15) — Lumi's agora space API v1, the seam between Lumi's v3 and our v8.1 bridge:
the contract file is Lumi's (`~/development/lumi/docs/agora-space-api.json`), copied here byte for byte as
`tests/fixtures/lumi_agora_api_v1.json`. These tests pin what our bridge relies on, so a new copy that changes it fails
here first, not in the room (made-up lines only; no network)."""

import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).parent / "fixtures" / "lumi_agora_api_v1.json").read_text(encoding="utf-8"))


def test_it_is_api_v1_owned_by_lumi_on_the_box():
    assert CONTRACT["version"] == 1 and CONTRACT["owner"] == "lumi"
    assert CONTRACT["base_url"] == {"prod": "http://192.168.1.197:8765", "dev": "http://192.168.1.197:8766"}
    assert CONTRACT["auth"]["client_header"] == "X-Lumi-Client: agora"


def test_a_turn_carries_the_trigger_alone_and_answers_reply_or_pass_without_her_thinking():
    turn = CONTRACT["endpoints"]["turn"]
    assert (turn["request"]["method"], turn["request"]["path"]) == ("POST", "/v1/turn")
    assert set(turn["request"]["body"]) == {"channel", "speaker", "register", "turn_id", "text"}  # R1: never resent lines
    assert turn["request"]["body"]["channel"] == "agora" and turn["request"]["body"]["register"] == "voice"
    for case in ("turn", "turn_pass"):
        body = CONTRACT["endpoints"][case]["response"]["body"]
        assert body["outcome"] in ("reply", "pass") and "thinking" not in body and "state" not in body
        assert {"model", "input_tokens", "output_tokens", "latency_ms"} <= set(body["stats"])   # our usage line
    assert CONTRACT["endpoints"]["turn_pass"]["response"]["body"]["reply"] == ""


def test_observe_retract_and_health_as_the_bridge_reads_them():
    observe = CONTRACT["endpoints"]["observe"]
    assert set(observe["request"]["body"]) == {"channel", "lines"}
    assert all(set(line) == {"id", "speaker", "text", "ts"} for line in observe["request"]["body"]["lines"])
    assert set(observe["response"]["body"]) == {"stored", "known"}
    assert CONTRACT["endpoints"]["retract"]["response"]["body"] == {"retracted": True}
    assert CONTRACT["endpoints"]["health"]["response"]["body"]["agora"] == 1


def test_the_statuses_that_are_silence_and_the_limits():
    silence = CONTRACT["silence"]
    assert {409, 429, 500, 502, 503, 504} == set(silence["statuses"]) and silence["outcome"] == "pass"
    assert silence["timeout_s"] > CONTRACT["limits"]["timeout_s"]          # R7: never cut a reply Lumi still makes
    assert {e["status"] for e in CONTRACT["errors"]} >= {401, 403, 404, 409, 422, 429, 502, 504}
    assert CONTRACT["limits"]["observe_batch_max"] >= 1 and CONTRACT["limits"]["max_turns_per_hour"] >= 1
