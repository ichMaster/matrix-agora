"""v8.1 (AGORA-265) — the bridge's Lumi client against the fake Lumi server built from the contract; the pure helpers.
Made-up lines and a made-up token only; no network."""

import asyncio
from pathlib import Path

import pytest

from agents.lumi_api import (
    BATCH_MAX,
    AiohttpTransport,
    LumiClient,
    classify,
    health_ok,
    kept,
    line_ts,
    observed_line,
    plain_body,
    speaker_ok,
)
from agents.roster import RosterError, load_member, parse_member
from agents.turns import named
from tests.fake_lumi import BASE, CONTRACT, EP, TOKEN, FakeLumi


def client(fake: FakeLumi, timeout_s: float = 60.0) -> LumiClient:
    return LumiClient(BASE, TOKEN, fake, timeout_s=timeout_s)


def run(coro):
    return asyncio.run(coro)


# --- the roster: the bridge type and Лілі's TOML -------------------------------------------------------------------
def test_lili_is_a_mention_only_bridge_on_lumi_http_with_nothing_of_ours():
    m = load_member(Path("agents/lili.toml"))
    assert (m.user_id, m.name, m.type, m.engine, m.mode, m.weight) == (
        "@lili:agora.lan", "Лілі", "bridge", "lumi-http", "mention-only", 1.0)
    assert m.capabilities == frozenset() and m.panel["pronoun"] == "she"


@pytest.mark.parametrize("toml, why", [
    ('type = "bridge"\n', "lumi-http"),                                   # a bridge on Gemini
    ('engine = "lumi-http"\n', "lumi-http"),                              # Lumi's API for a persona
    ('type = "bridge"\nengine = "lumi-http"\n[turns]\nmode = "ranked"\n', "mention-only"),  # v8.2's, not yet
    ('type = "bridge"\nengine = "lumi-http"\n[capabilities]\nvoice = true\n', "no capability"),
])
def test_a_bridge_off_its_shape_is_refused(toml, why):
    import tomllib
    data = tomllib.loads('name = "Лілі"\nuser_id = "@lili:agora.lan"\n' + toml)
    with pytest.raises(RosterError, match=why):
        parse_member("lili", data)


def test_she_is_named_by_both_her_names_and_her_id():
    lili = load_member(Path("agents/lili.toml"))
    for text in ("Лілі, як ти?", "а ти що скажеш, Стхіро?", "поговоримо зі Стхірою", "@lili:agora.lan привіт"):
        assert named(text, [lili]) == [lili], text
    assert named("ліліпут і стхіранець", [lili]) == []  # whole words only


def test_no_name_form_of_hers_belongs_to_another_member():
    import tomllib
    sims = tomllib.loads(Path("simulations.toml").read_text(encoding="utf-8"))
    others = [load_member(Path(f"agents/{n}.toml")) for n in sims["agora"]["agents"] if n != "lili"]
    assert "lili" in sims["agora"]["agents"]                                    # v8.1 (AGORA-268): in the room
    theirs = {f for m in others for f in m.name_forms}
    assert not theirs & set(load_member(Path("agents/lili.toml")).name_forms)


# --- the client: every request as the contract writes it -----------------------------------------------------------
def test_a_turn_sends_the_trigger_alone_with_the_header_and_the_token():
    fake = FakeLumi()
    want = EP["turn"]["request"]["body"]
    got = run(client(fake).turn(want["speaker"], want["turn_id"], want["text"]))
    call = fake.turns()[0]
    assert call["body"] == want                                    # exactly the contract's body, R1
    assert call["headers"]["X-Lumi-Client"] == "agora" and call["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert got.outcome == "reply" and got.reply == EP["turn"]["response"]["body"]["reply"]
    assert got.stats == EP["turn"]["response"]["body"]["stats"] and got.wall_ms is not None


def test_her_thinking_emotion_and_state_never_survive_the_parse():
    fake = FakeLumi()
    fake.turn_bodies = [{"outcome": "reply", "reply": "Так.", "thinking": "SECRET", "emotion": "calm",
                         "intensity": 0.4, "state": {"mood": "x"}, "stats": {"model": "m", "mood": "y"}}]
    got = run(client(fake).turn("Ich", "$t1", "Лілі?"))
    assert got.reply == "Так." and got.stats == {"model": "m"}
    assert "SECRET" not in repr(got) and "Так" not in repr(got)
    assert set(kept({"outcome": "pass", "thinking": "x", "emotion": "y"})) == {"outcome", "stats"}


def test_a_pass_and_an_empty_reply_are_both_a_pass():
    fake = FakeLumi()
    fake.turn_bodies = [EP["turn_pass"]["response"]["body"], {"outcome": "reply", "reply": "  ", "stats": {}}]
    c = client(fake)
    assert run(c.turn("Ада", "$p1", "Лілі?")).outcome == "pass"
    assert run(c.turn("Ада", "$p2", "Лілі?")).outcome == "pass"


@pytest.mark.parametrize("status, outcome", [
    (409, "silence:409"), (429, "silence:429"), (500, "silence:500"), (502, "silence:502"), (503, "silence:503"),
    (504, "silence:504"), (401, "refused:wrong token"), (403, "refused:token not allowed"), (404, "refused:space off"),
    (422, "refused:malformed request"), (418, "bad"),
])
def test_every_status_maps_to_its_outcome(status, outcome):
    fake = FakeLumi()
    fake.turn_status = [status]
    got = run(client(fake).turn("Ich", "$s", "Лілі?"))
    assert got.outcome == outcome and got.reply == "" and got.status == status
    assert set(CONTRACT["silence"]["statuses"]) <= {s for s in range(400, 600) if classify(s, None).startswith("silence")}


def test_our_own_timeout_and_an_unreachable_lumi():
    fake = FakeLumi()
    fake.delay_s = 99
    assert run(client(fake, timeout_s=60).turn("Ich", "$x", "Лілі?")).outcome == "timeout"
    fake = FakeLumi()
    fake.unreachable = True
    assert run(client(fake).turn("Ich", "$x", "Лілі?")).outcome == "unreachable"
    assert classify(200, {"outcome": "dance"}) == "bad" and classify(200, None) == "bad"


def test_observe_carries_the_contracts_shape_and_is_idempotent_by_id():
    fake = FakeLumi()
    lines = EP["observe"]["request"]["body"]["lines"]
    c = client(fake)
    assert run(c.observe(lines)) == (200, EP["observe"]["response"]["body"])
    assert run(c.observe(lines)) == (200, {"stored": 0, "known": 2})
    assert fake.observes()[0]["body"] == EP["observe"]["request"]["body"]
    many = [{**lines[0], "id": f"$m{i}"} for i in range(BATCH_MAX + 50)]
    run(c.observe(many))
    assert len(fake.observes()[-1]["body"]["lines"]) == BATCH_MAX


def test_a_retract_is_url_encoded_and_reads_true_or_false():
    fake = FakeLumi()
    c = client(fake)
    turn_id = EP["turn"]["request"]["body"]["turn_id"]
    run(c.turn("Бруно", turn_id, "Лілі?"))
    assert run(c.retract(turn_id)) is True
    assert fake.calls[-1]["path"] == EP["retract"]["request"]["example_path"]
    assert run(c.retract(turn_id)) is False                       # R8: idempotent, nothing stored
    fake.unreachable = True
    assert run(c.retract(turn_id)) is None                        # best effort, never retried


def test_health_reads_the_api_version_and_names_what_is_wrong():
    fake = FakeLumi()
    assert run(client(fake).health()) == (True, None, 1)
    fake.health_body = {"ok": True, "env": "dev", "version": "3.0.0"}
    assert run(client(fake).health()) == (False, "space off", None)
    fake.health_body = {"ok": True, "agora": 0}
    assert run(client(fake).health()) == (False, "too old", 0)
    fake.unreachable = True
    assert run(client(fake).health()) == (False, "unreachable", None)
    assert health_ok(503, None) == (False, "health 503", None)
    assert all("Authorization" not in c["headers"] for c in fake.calls)  # health is open: no token sent


def test_the_token_is_in_no_repr():
    assert TOKEN not in repr(client(FakeLumi()))


# --- the line helpers ------------------------------------------------------------------------------------------------
def test_the_reply_fallback_is_stripped_and_anything_else_kept():
    assert plain_body("> <@ada:agora.lan> туман\n> ще рядок\n\nА я бачив.") == "А я бачив."
    assert plain_body("> цитата без порожнього рядка\nтекст") == "текст"
    assert plain_body("звичайний рядок\n> не на початку") == "звичайний рядок\n> не на початку"
    assert plain_body("") == ""


def test_ts_is_iso_to_the_second_with_the_rooms_offset():
    ms = 1_794_808_872_345  # 2026-11-16 06:01:12.345 UTC
    assert line_ts(ms, "Europe/Kyiv") == "2026-11-16T08:01:12+02:00"
    line = observed_line("$e1", "Ich", "> q\n\nвідповідь", ms, "Europe/Kyiv")
    assert line == {"id": "$e1", "speaker": "Ich", "text": "відповідь", "ts": "2026-11-16T08:01:12+02:00"}


def test_a_speaker_is_one_line_up_to_64_characters_without_a_colon():
    assert all(speaker_ok(n) for n in ("Ich", "Ада", "Кіт", "Клод", "Устина"))
    assert not any(speaker_ok(n) for n in ("", "a:b", "x" * 65, "два\nрядки"))


def test_the_real_transport_turns_a_client_error_into_no_url_and_no_token(monkeypatch):
    import aiohttp

    class Boom:
        def request(self, *a, **k):
            raise aiohttp.ClientError(f"cannot reach {BASE} with Bearer {TOKEN}")

        async def close(self):
            pass

    t = AiohttpTransport()
    t._session = Boom()
    with pytest.raises(ConnectionError) as exc:
        run(t("POST", BASE + "/v1/turn", {}, {"Authorization": f"Bearer {TOKEN}"}, 5))
    assert TOKEN not in str(exc.value) and BASE not in str(exc.value)
    run(t.close())
