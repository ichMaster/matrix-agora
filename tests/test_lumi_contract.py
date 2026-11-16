"""v8 (synchronization step 2, 2026-11-15) — Lumi's agora space API v1, the seam between Lumi's v3 and our v8.1 bridge:
the contract file is Lumi's (`~/development/lumi/docs/agora-space-api.json`), copied here byte for byte as
`tests/fixtures/lumi_agora_api_v1.json`. These tests pin what our bridge relies on, so a new copy that changes it fails
here first, not in the room (made-up lines only; no network)."""

import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).parent / "fixtures" / "lumi_agora_api_v1.json").read_text(encoding="utf-8"))


def test_it_is_api_v2_owned_by_lumi_on_the_box():
    assert CONTRACT["version"] == 2 and CONTRACT["owner"] == "lumi"  # v2 (Lumi v3.4, sync step 11): + her initiative
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
    retract = CONTRACT["endpoints"]["retract"]
    assert retract["response"] == {"status": 200, "body": {"retracted": True}}
    # R8 (Lumi bf17105): a retract is always a 200 — nothing stored (a pass, a timeout, a second retract) is `false`, and
    # a 404 means only that the space is off, never a retract
    assert retract["response_nothing_stored"] == {"status": 200, "body": {"retracted": False}}
    assert all("never a retract" in e["when"] for e in CONTRACT["errors"] if e["status"] == 404)
    assert CONTRACT["endpoints"]["health"]["response"]["body"]["agora"] == 2  # 1 = the v1 routes, 2 = + her initiative


def test_the_statuses_that_are_silence_and_the_limits():
    silence = CONTRACT["silence"]
    assert {409, 429, 500, 502, 503, 504} == set(silence["statuses"]) and silence["outcome"] == "pass"
    assert silence["timeout_s"] > CONTRACT["limits"]["timeout_s"]          # R7: never cut a reply Lumi still makes
    assert {e["status"] for e in CONTRACT["errors"]} >= {401, 403, 404, 409, 422, 429, 502, 504}
    assert CONTRACT["limits"]["observe_batch_max"] >= 1 and CONTRACT["limits"]["max_turns_per_hour"] >= 1


def test_lumi_310_says_what_a_line_must_be_speaker_and_ts():
    """Lumi v3.1.0 (CR3, still API v1): a speaker of 1–64 characters with no ':', a ts with its offset — else a 422."""
    about = CONTRACT["endpoints"]["observe"]["about"]
    assert "no ':'" in about and "offset" in about and "422" in about
    malformed = next(e for e in CONTRACT["errors"] if e["status"] == 422)["when"]
    assert "speaker" in malformed and "offset" in malformed



def test_v2_her_initiative_is_an_offer_the_bridge_polls_and_acks_never_a_post():
    """v8.3 (sync step 11, Lumi a9937b1): API v2 adds `GET /v1/initiative` — `say` with an offer or `none`, a poll never
    calls the model — and `POST /v1/initiative/{id}/posted {event_id}` → `{stored}`, always 200; nothing is remembered
    until acked; the v1 routes are unchanged; an initiative never names the owner or carries «Ich»."""
    ep = CONTRACT["endpoints"]
    say, none, posted = ep["initiative"], ep["initiative_none"], ep["initiative_posted"]
    assert (say["request"]["method"], say["request"]["path"]) == ("GET", "/v1/initiative")
    assert say["response"]["body"]["outcome"] == "say" and {"initiative_id", "text", "stats"} <= set(say["response"]["body"])
    assert "thinking" not in say["response"]["body"] and "Ich" not in say["response"]["body"]["text"]
    assert none["response"]["body"] == {"outcome": "none"}
    assert posted["request"]["method"] == "POST" and posted["request"]["path"] == "/v1/initiative/{initiative_id}/posted"
    assert posted["response"]["status"] == 200 and set(posted["response"]["body"]) == {"stored"}
    limits = CONTRACT["limits"]
    # Lumi v3.4.1 (63df6be, the owner 2026-11-17: «так зміни на боці lumi на 10 хв»): the compose gap 1800 → 600
    assert (limits["initiative_fresh_s"], limits["initiative_compose_gap_s"], limits["initiative_kept_s"]) == (1800, 600, 86400)
    assert not any("she only answers" in n for n in CONTRACT["never"])          # the `never` changed, contract first
    assert any("Ich" in n for n in CONTRACT["never"])
    assert set(ep) >= {"health", "observe", "turn", "turn_pass", "retract"}      # v1's routes unchanged
