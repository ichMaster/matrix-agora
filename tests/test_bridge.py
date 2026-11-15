"""v8.1 (AGORA-266) — the bridge against the fake Lumi server built from the contract: she hears every room line once,
answers only when named with the trigger alone, posts only what Lumi returned, stays silent on every silence status and
retracts what the room never saw. nio mocked, the clock injected, made-up lines and a made-up token; no network."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nio import RoomMessage

from agents.bridge import BACKOFF_S, OBSERVE_LINES, Bridge, load_state, lumi_settings
from agents.config import AgentConfig
from agents.roster import load_member
from tests.fake_lumi import BASE, EP, TOKEN, FakeLumi

ROOM = "!room"
OWNER = "@ich:agora.lan"
ADA, BRUNO, HERMES = "@ada:agora.lan", "@bruno:agora.lan", "@hermes:agora.lan"
LILI = "@lili:agora.lan"
T0 = 1_794_808_872_000  # 2026-11-16 08:01:12 in Kyiv

CFG = AgentConfig(name="Лілі", user_id=LILI, canon="", homeserver="http://hs", room_id=ROOM, owner=OWNER,
                  password="pw", type="bridge", engine="lumi-http", capabilities=frozenset())


def roster(lili_mode=None):
    names = ("ada", "bruno", "hermes")
    lili = load_member(Path("agents/lili.toml"))
    if lili_mode:  # v8.2: she is ranked; a test of v8.1's mention-only behaviour pins that mode
        lili = replace(lili, mode=lili_mode)
    return {**{n: load_member(Path(f"agents/{n}.toml")) for n in names}, "lili": lili}


def ev(sender, body, ts, eid=None, msgtype="m.text", content=None):
    return RoomMessage.parse_event({
        "event_id": eid or f"$e{ts}", "sender": sender, "origin_server_ts": ts, "type": "m.room.message",
        "content": content or {"msgtype": msgtype, "body": body},
    })


class Clock:
    def __init__(self, ms=T0):
        self.ms = ms

    def __call__(self):
        return self.ms


def make(fake=None, env=None, healthy=True, lili_mode=None):
    fake = fake or FakeLumi()
    env = {"LUMI_URL": BASE, "LUMI_ROOM_TOKEN": TOKEN} if env is None else env
    b = Bridge(CFG, roster=roster(lili_mode), transport=fake, env=env)
    b.client = SimpleNamespace(room_send=AsyncMock(return_value=SimpleNamespace(event_id="$mine")),
                               room_typing=AsyncMock(), join=AsyncMock(), room_leave=AsyncMock())
    b.clock = Clock()
    b.rng = lambda: 0.0
    b.started = True
    b.healthy, b.health_why = healthy, None if healthy else "not checked yet"
    return b, fake


def room():
    return SimpleNamespace(room_id=ROOM)


async def hear(b, *events):
    for e in events:
        await b.on_message(room(), e)


def sent(b) -> list[str]:
    return [c.kwargs["content"]["body"] for c in b.client.room_send.await_args_list]


# --- she hears ---------------------------------------------------------------------------------------------------------
def test_every_allowlisted_line_is_heard_once_with_the_contracts_shape():
    async def go():
        b, fake = make()
        await hear(b, ev(OWNER, "Доброго ранку!", T0, "$o1"), ev(ADA, "Хто бачив туман?", T0 + 1000, "$a1"),
                   ev(LILI, "моє", T0 + 2000, "$l1"), ev("@stranger:x", "чужий", T0 + 3000, "$s1"),
                   ev(OWNER, "* правка", T0 + 4000, "$o2", content={
                       "msgtype": "m.text", "body": "* правка",
                       "m.relates_to": {"rel_type": "m.replace", "event_id": "$o1"}}),
                   ev(OWNER, "notice", T0 + 5000, "$n1", msgtype="m.notice"))
        await b.on_message(SimpleNamespace(room_id="!other"), ev(OWNER, "інша кімната", T0 + 6000, "$x1"))
        assert [line["id"] for line, _ in b.queue] == ["$o1", "$a1"]
        assert await b.flush() is True
        body = fake.observes()[0]["body"]
        assert body == {"channel": "agora", "lines": [
            {"id": "$o1", "speaker": "Ich", "text": "Доброго ранку!", "ts": "2026-11-16T08:01:12+02:00"},
            {"id": "$a1", "speaker": "Ада", "text": "Хто бачив туман?", "ts": "2026-11-16T08:01:13+02:00"}]}
        assert b.queue == [] and load_state(b.state_file)["observed"]["count"] == 2
        assert set(fake.observed) == {"$o1", "$a1"}
    asyncio.run(go())


def test_the_reply_fallback_is_stripped_and_the_owners_voice_is_his_line():
    async def go():
        b, fake = make()
        await hear(b, ev(OWNER, "> <@ada:agora.lan> туман\n\nЯ бачив.", T0, "$o1"))
        b.owner_voices = ["$voice"]  # Hermes's transcript of the owner's voice reads as his line (v5.2)
        transcript = ev(HERMES, "🎙 Ich: сказав голосом", T0 + 1000, "$h1", content={
            "msgtype": "m.text", "body": "🎙 Ich: сказав голосом",
            "m.relates_to": {"m.in_reply_to": {"event_id": "$voice"}}})
        await hear(b, transcript)
        await b.flush()
        lines = fake.observes()[0]["body"]["lines"]
        assert [(x["speaker"], x["text"]) for x in lines] == [("Ich", "Я бачив."), ("Ich", "сказав голосом")]
    asyncio.run(go())


def test_a_members_voiced_caption_is_not_heard_twice():
    async def go():
        b, _ = make()
        caption = SimpleNamespace(sender=ADA, body="слова", event_id="$audio", server_timestamp=T0, source={})
        await b.on_message(room(), caption)  # what on_audio hands on for a voiced line (v5.3)
        assert b.queue == []
    asyncio.run(go())


def test_the_queue_goes_on_quiet_at_twenty_lines_and_in_batches_of_two_hundred():
    async def go():
        b, fake = make()
        for i in range(OBSERVE_LINES - 1):
            await hear(b, ev(ADA, f"рядок {i}", T0 + i, f"$q{i}"))
        await asyncio.sleep(0)
        assert fake.observes() == []                       # 19 lines wait for quiet
        await hear(b, ev(ADA, "двадцятий", T0 + 50, "$q19"))
        await asyncio.sleep(0.01)
        assert len(fake.observes()) == 1 and b.queue == []  # the 20th sends at once
        for i in range(450):
            b._queue(ADA, f"x{i}", f"$big{i}", T0 + 100 + i)
        await b.flush()
        assert [len(c["body"]["lines"]) for c in fake.observes()[1:]] == [200, 200, 50]
    asyncio.run(go())


def test_a_failed_batch_is_sent_again_whole_on_the_backoff_and_idempotent():
    async def go():
        b, fake = make()
        await hear(b, ev(ADA, "раз", T0, "$1"), ev(BRUNO, "два", T0 + 1, "$2"))
        fake.observe_status = [503, 503]
        assert await b.flush() is False and len(b.queue) == 2
        assert b._retry_at == b.clock() + BACKOFF_S[0] * 1000
        assert await b.flush() is False                   # inside the backoff: no call
        assert len(fake.observes()) == 1
        b.clock.ms = b._retry_at
        assert await b.flush() is False and b._retry_at == b.clock() + BACKOFF_S[1] * 1000
        b.clock.ms = b._retry_at
        assert await b.flush() is True and b.queue == []
        assert fake.observes()[0]["body"]["lines"] == fake.observes()[-1]["body"]["lines"]  # whole
        b._queue(ADA, "раз", "$1", T0)
        await b.flush()
        assert fake.calls[-1]["path"] == "/v1/observe" and len(fake.observed) == 2  # known, never stored twice
    asyncio.run(go())


def test_422_drops_the_batch_401_stops_every_call_404_waits_for_the_space():
    async def go():
        b, fake = make()
        await hear(b, ev(ADA, "раз", T0, "$1"))
        fake.observe_status = [422]
        assert await b.flush() is True and b.queue == []
        await hear(b, ev(ADA, "два", T0 + 1, "$2"))
        fake.observe_status = [404]
        assert await b.flush() is False and not b.healthy and b.health_why == "space off"
        b.healthy = True
        fake.token = "another"                             # a wrong token → 401
        assert await b.flush() is False and b.refused == "wrong token"
        n = len(fake.calls)
        assert await b.flush(force=True) is False and len(fake.calls) == n  # no more calls until a restart
        assert load_state(b.state_file)["refused"] == "wrong token"
    asyncio.run(go())


def test_after_a_restart_she_catches_up_on_todays_lines_since_the_last_she_heard():
    b, _ = make()
    b.state["observed"] = {"day": "2026-11-16", "count": 5, "last_ts_ms": T0 + 2000, "last_id": "$2"}
    yesterday = T0 - 24 * 3600 * 1000
    newest_first = [ev(BRUNO, "четвертий", T0 + 4000, "$4"), ev(LILI, "мій", T0 + 3500, "$m"),
                    ev(ADA, "третій", T0 + 3000, "$3"), ev(ADA, "другий", T0 + 2000, "$2"),
                    ev(OWNER, "перший", T0 + 1000, "$1"), ev(OWNER, "вчорашній", yesterday, "$y")]
    b.seed_context(newest_first)
    assert [line["id"] for line, _ in b.queue] == ["$3", "$4"]   # oldest first, never her own, never yesterday's
    b.state = {}
    b.queue = []
    b.seed_context(newest_first)
    assert [line["id"] for line, _ in b.queue] == ["$1", "$2", "$3", "$4"]  # the first start: today's


# --- she answers -------------------------------------------------------------------------------------------------------
def test_named_by_the_owner_she_answers_with_the_trigger_alone_exactly_as_lumi_returned():
    async def go():
        b, fake = make()
        await hear(b, ev(ADA, "Туман сідає на дахи.", T0, "$a1"), ev(OWNER, "Лілі, що скажеш?", T0 + 1000, "$o1"))
        assert b._reply_pending
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        turn = fake.turns()[0]
        assert turn["body"] == {"channel": "agora", "speaker": "Ich", "register": "voice", "turn_id": "$o1",
                                "text": "Лілі, що скажеш?"}
        assert turn["headers"]["X-Lumi-Client"] == "agora"
        assert fake.paths().index("/v1/observe") < fake.paths().index("/v1/turn")  # Q6: heard first
        assert sent(b) == [EP["turn"]["response"]["body"]["reply"]]               # byte for byte
        state = load_state(b.state_file)
        assert state["last_turn"]["outcome"] == "reply"
        usage = [json.loads(x) for x in b.usage_file.read_text().splitlines()]
        assert (usage[0]["engine"], usage[0]["billing"], usage[0]["prompt_tokens"], usage[0]["ok"]) == (
            "lumi", "external", 6420, True)
        answers = [json.loads(x) for x in b.answers_file.read_text().splitlines()]
        assert answers[0]["by"] == "lumi" and answers[0]["answered"] == "owner"
    asyncio.run(go())


def test_unnamed_she_stays_silent_and_named_by_an_agent_she_answers_it():
    """v8.1's mention-only rule (v8.2 ranks her — pinned here as mention-only)."""
    async def go():
        b, fake = make(lili_mode="mention-only")
        await hear(b, ev(OWNER, "Як там погода?", T0, "$o1"), ev(ADA, "Сонячно.", T0 + 1000, "$a1"))
        await asyncio.sleep(0.01)
        assert fake.turns() == [] and not b._reply_pending
        await hear(b, ev(BRUNO, "Стхіро, а ти любиш туман?", T0 + 2000, "$b1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert [t["body"]["speaker"] for t in fake.turns()] == ["Бруно"]
        assert fake.turns()[0]["body"]["turn_id"] == "$b1"
    asyncio.run(go())


@pytest.mark.parametrize("status", [409, 429, 500, 502, 503, 504, 401, 403, 404, 422])
def test_every_silence_status_and_every_named_refusal_is_silence_never_retried(status):
    async def go():
        b, fake = make()
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        fake.turn_status = [status]
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert len(fake.turns()) == 1 and sent(b) == []
        assert not any("/retract" in p for p in fake.paths())
        line = json.loads(b.usage_file.read_text().splitlines()[0])
        assert line["ok"] is False and line["prompt_tokens"] is None
    asyncio.run(go())


def test_a_pass_is_silence_and_writes_her_stats():
    async def go():
        b, fake = make()
        fake.turn_bodies = [EP["turn_pass"]["response"]["body"]]
        await hear(b, ev(OWNER, "Лілі, з ким ти говориш наодинці?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert sent(b) == [] and load_state(b.state_file)["last_turn"]["outcome"] == "pass"
        assert json.loads(b.usage_file.read_text())["output_tokens"] == 3
    asyncio.run(go())


def test_her_own_timeout_is_silence_and_a_retract():
    async def go():
        b, fake = make()
        b.lumi.timeout_s = 1
        fake.delay_s = 5
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert sent(b) == [] and fake.paths()[-1] == "/v1/turn/%24o1/retract"
    asyncio.run(go())


def test_a_reply_that_would_out_a_persona_is_never_posted_and_is_retracted():
    async def go():
        b, fake = make()
        fake.turn_bodies = [{"outcome": "reply", "reply": "Ада, ти ж просто бот.", "stats": {}}]
        await hear(b, ev(OWNER, "Лілі, що думаєш про Аду?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert sent(b) == [] and fake.paths()[-1] == "/v1/turn/%24o1/retract"
        assert fake.stored_turns == set()                 # she will not remember saying it
    asyncio.run(go())


def test_her_thinking_never_reaches_the_room_the_state_or_a_usage_line():
    async def go():
        b, fake = make()
        fake.turn_bodies = [{"outcome": "reply", "reply": "Так.", "thinking": "SECRET-THOUGHT", "stats": {}}]
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert sent(b) == ["Так."]
        for path in (b.state_file, b.usage_file, b.answers_file):
            assert "SECRET" not in path.read_text()
    asyncio.run(go())


def test_without_health_or_an_address_she_neither_hears_nor_answers_and_says_why():
    async def go():
        b, fake = make(healthy=False)
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert await b.flush() is False and fake.calls == [] and len(b.queue) == 1
        fake.health_body = {"ok": True, "env": "dev"}
        assert await b.check_health() is False and b.health_why == "space off"
        fake.health_body = {"ok": True, "agora": 1}
        assert await b.check_health() is True and await b.flush() is True
        b2, fake2 = make(env={})
        assert b2.lumi is None and b2.missing == "no LUMI_URL"
        assert await b2.reply(ROOM) is False and fake2.calls == []
    asyncio.run(go())


def test_she_never_posts_without_a_trigger():
    async def go():
        b, fake = make()
        assert await b.reply(ROOM) is False                # no owner line yet, no trigger
        assert fake.turns() == [] and sent(b) == []
    asyncio.run(go())


# --- the address and the token -----------------------------------------------------------------------------------------
def test_the_address_and_token_leave_the_environment_and_the_dev_file_is_read_in_process(tmp_path):
    env = {"LUMI_URL": "http://prod", "LUMI_ROOM_TOKEN": "prod-token", "OTHER": "x"}
    assert lumi_settings(env) == ("http://prod", "prod-token") and env == {"OTHER": "x"}
    dev = tmp_path / "lili.dev.env"
    dev.write_text(f"LUMI_URL={BASE}\nLUMI_ROOM_TOKEN={TOKEN}\n")
    env = {"LUMI_ENV_FILE": str(dev)}
    assert lumi_settings(env) == (BASE, TOKEN) and env == {}


def test_the_token_is_in_no_log_line(caplog):
    async def go():
        b, fake = make()
        fake.turn_status = [401]
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
    caplog.set_level("DEBUG")
    asyncio.run(go())
    assert TOKEN not in caplog.text and "Лілі?" not in caplog.text


def test_an_edit_enters_her_timeline_as_every_agents_but_is_neither_heard_nor_answered():
    """Code review v8.1 #2: the room's agents keep an edit in their timeline (R3, the wave); so does she — never heard,
    never answered."""
    async def go():
        b, fake = make()
        edit = ev(OWNER, "* Лілі, а ти?", T0 + 2000, "$edit", content={
            "msgtype": "m.text", "body": "* Лілі, а ти?", "m.relates_to": {"rel_type": "m.replace", "event_id": "$o1"}})
        await hear(b, ev(OWNER, "Привіт усім", T0, "$o1"), ev(BRUNO, "Привіт!", T0 + 1000, "$b1"), edit)
        await asyncio.sleep(0.01)
        assert [e[2] for e in b.timeline] == ["$o1", "$b1", "$edit"]       # the same timeline as Ада's
        assert "$edit" not in [line["id"] for line, _ in b.queue]           # never heard
        assert not any(c["path"] == "/v1/turn" and c["body"]["turn_id"] == "$edit" for c in fake.calls)
        assert b.decide(OWNER, "Лілі?", "$new", T0 + 3000).reply is True     # a new line is decided as ever
    asyncio.run(go())


@pytest.mark.parametrize("case", ["send-refused", "send-raises", "bad", "unreachable"])
def test_a_reply_the_room_never_saw_is_retracted(case):
    """Code review v8.1 #4 (Q2): what Lumi remembers is what the room saw — a refused or failed send, a body off the
    contract and a reset after Lumi answered are all retracted, and never recorded as answered."""
    async def go():
        b, fake = make()
        if case == "send-refused":
            b.client.room_send = AsyncMock(return_value=SimpleNamespace(message="M_FORBIDDEN"))  # a RoomSendError
        elif case == "send-raises":
            b.client.room_send = AsyncMock(side_effect=OSError("reset"))
        elif case == "bad":
            fake.turn_bodies = [{"outcome": "dance", "reply": "x"}]
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"))
        if case == "unreachable":
            orig = fake._turn

            async def stored_then_reset(body, timeout_s):
                await orig(body, timeout_s)             # Lumi stored her reply …
                raise ConnectionError("reset")          # … and the answer never arrived
            fake._turn = stored_then_reset
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert fake.paths()[-1] == "/v1/turn/%24o1/retract"
        assert not b.answers_file.exists()
    asyncio.run(go())


def test_flushes_never_pile_up_past_the_backoff_and_the_turn_waits_for_them_no_longer_than_its_bound(monkeypatch):
    """Code review v8.1 #5: from 20 lines every line spawned a flush that called Lumi past the backoff, and the
    pre-turn flush waited on them without a bound."""
    import agents.bridge as bridge_mod
    monkeypatch.setattr(bridge_mod, "PRE_TURN_FLUSH_S", 0.2)

    async def go():
        b, fake = make(lili_mode="mention-only")  # Ada's lines never choose her: the queue alone is under test
        fake.observe_status = [503] * 50
        for i in range(26):
            await hear(b, ev(ADA, f"рядок {i}", T0 + i, f"$q{i}"))
        await asyncio.sleep(0.05)
        assert len(fake.observes()) == 1                       # one call, then the backoff holds the rest
        orig = fake.__call__

        async def held(method, url, body, headers, timeout_s):
            if url.endswith("/v1/observe"):
                await asyncio.sleep(10)                         # Lumi hangs on observe
            return await orig(method, url, body, headers, timeout_s)
        b.transport = b.lumi._transport = held
        await hear(b, ev(OWNER, "Лілі?", T0 + 100, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 3)   # the turn went within the bound
        assert any(c["path"] == "/v1/turn" for c in fake.calls)
    asyncio.run(go())


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_refusal_on_the_pre_turn_flush_stops_the_turn(status):
    """Code review v8.1 #6: a 401/403 means no more calls until a restart, a 404 the space off — the turn never follows."""
    async def go():
        b, fake = make()
        await hear(b, ev(ADA, "туман", T0, "$a1"))
        if status == 401:
            fake.token = "another"
        else:
            fake.observe_status = [status]
        await hear(b, ev(OWNER, "Лілі?", T0 + 1000, "$o1"))
        await asyncio.wait_for(asyncio.gather(*b._tasks), 5)
        assert fake.paths() == ["/v1/observe"] and sent(b) == []
    asyncio.run(go())


def test_without_an_address_the_card_says_why_and_nothing_is_queued():
    """Code review v8.1 #8: the reason is said by name on her card, and lines with nowhere to go are never queued."""
    async def go():
        b, _ = make(env={"LUMI_URL": BASE})
        assert load_state(b.state_file)["health"]["why"] == "no LUMI_ROOM_TOKEN"
        await hear(b, ev(OWNER, "Лілі?", T0, "$o1"), ev(ADA, "туман", T0 + 1, "$a1"))
        assert b.queue == []
    asyncio.run(go())


def test_ranked_she_answers_an_unnamed_owner_line_when_r1_chose_her_and_a_fallback_turn_answers_its_line():
    """v8.2 (AGORA-270): ranked with weight 1 — R1 picks her for some unnamed owner lines (by the event's hash), and a
    fallback turn answers the owner line it stands in for, never a newer one."""
    from agents.turns import owner_repliers

    async def go():
        b, fake = make()
        assert b.me.mode == "ranked"
        b.fallback_s, b.reply_delay_s = 3600, 1.0          # a stand-in's wait never fires inside this test
        text = "Як вам сьогоднішній вечір?"
        ids = [f"$u{i}" for i in range(60)]
        mine = next(e for e in ids if "lili" in owner_repliers(e, text, b.roster, b.owner_repliers))
        theirs = next(e for e in ids if "lili" not in owner_repliers(e, text, b.roster, b.owner_repliers))
        await hear(b, ev(OWNER, text, T0, theirs))
        await asyncio.sleep(0.01)
        assert fake.turns() == []                          # not chosen: silent
        await hear(b, ev(OWNER, text, T0 + 60_000, mine))
        for _ in range(100):
            if fake.turns():
                break
            await asyncio.sleep(0.05)
        assert [t["body"]["turn_id"] for t in fake.turns()] == [mine]
        await hear(b, ev(OWNER, "ще одне", T0 + 120_000, "$newer"))
        await asyncio.sleep(0.01)
        n = len(fake.turns())
        assert await b.reply(ROOM, fallback_for=mine) is True   # the stand-in answers its own line
        assert fake.turns()[n]["body"]["turn_id"] == mine
        for t in list(b._tasks):
            t.cancel()
    asyncio.run(go())
