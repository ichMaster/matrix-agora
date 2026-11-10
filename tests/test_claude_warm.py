"""v7.2 (AGORA-243) — the answer from a CLI started ahead: one `ClaudeSDKClient` a call, its system prompt the call's
slow part, the rest of the prompt before the transcript in the message; a mismatch goes cold and starts the next; a
failed or hung one goes cold once; every check of v7.1 kept (a fake SDK client and a fake `query()`; no CLI, no
network)."""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import agents.claude_sdk as sdk_mod
from agents.claude_sdk import THINK_HEADROOM, ClaudeClient, WarmCli
from agents.usage import PROMPT_SLOW, analyze_detail, sdk_usage_line
from tests.test_claude_client import (
    INIT_OK,
    AssistantMessage,
    FakeGemini,
    FakeSDK,
    RateLimitEvent,
    ResultError,
    SystemMessage,
    TextBlock,
    result,
)

SLOW = "КАНОН АДИ\n\nТвоє життя досі: …"
SYSTEM = f"{SLOW}\n\nЗараз 17:02, вівторок.\n\nПРАВИЛА"


class FakeClient:
    """The SDK's `ClaudeSDKClient`: reads its system prompt file at connect, as the CLI does at its start."""

    def __init__(self, options, script, connect):
        self.options, self.script, self.connect_how = options, script, connect
        self.system, self.prompts, self.closed = None, [], False

    async def connect(self):
        if self.connect_how == "fail":
            raise RuntimeError("no CLI")
        if self.connect_how == "hang":
            await asyncio.sleep(3600)
        self.system = Path(self.options.system_prompt["path"]).read_text(encoding="utf-8")

    async def query(self, prompt):
        self.prompts.append(prompt)

    async def receive_response(self):
        if self.script == "hang":
            await asyncio.sleep(3600)
        for m in self.script:
            if isinstance(m, BaseException):
                raise m
            yield m

    async def disconnect(self):
        self.closed = True


class Clients:
    """Makes each new client with the next script (the last repeats)."""

    def __init__(self, *scripts, connect="ok"):
        self.scripts, self.connect, self.made = list(scripts) or [[INIT_OK, result("Тепло.")]], connect, []

    def __call__(self, *, options):
        script = self.scripts.pop(0) if len(self.scripts) > 1 else self.scripts[0]
        made = FakeClient(options, script, self.connect)
        self.made.append(made)
        return made


def claude(tmp_path, sdk, clients, **kw):
    usage = []
    c = ClaudeClient(reply_model="haiku", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                     status_file=tmp_path / "ada.ratelimit.json", sink=lambda *a, **k: usage.append((a, k)),
                     clock=lambda: 1_000_000_000, query=sdk.query, options=lambda **o: SimpleNamespace(**o),
                     sdk_client=clients, **kw)
    return c, usage


async def voice(c, system=SYSTEM, slow=SLOW, transcript="Ich: привіт", kind="reply", cap=200):
    token = PROMPT_SLOW.set(slow)
    try:
        return await c.complete(transcript, system, cap, kind=kind)
    finally:
        PROMPT_SLOW.reset(token)


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


def prompts_left(tmp_path):
    folder = tmp_path / "cfg" / "prompts"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


# --- warm on its key, cold otherwise --------------------------------------------------------------------------------
def test_the_first_answer_is_cold_and_the_next_goes_warm_with_its_slow_part_as_the_system(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients([INIT_OK, result("Тепло.")])
    c, usage = claude(tmp_path, sdk, clients)

    async def go():
        first = await voice(c)
        await settle()
        second = await voice(c, transcript="Ich: як ти?")
        await settle()
        await c.close()
        await settle()
        return first, second
    first, second = asyncio.run(go())
    assert first == ("Холодно.", "stop") and second == ("Тепло.", "stop")
    warm = clients.made[0]
    assert warm.system == SLOW                                              # the canon and the life, its system
    assert warm.prompts == ["Зараз 17:02, вівторок.\n\nПРАВИЛА\n\nIch: як ти?"]  # the rest, then the transcript
    assert warm.closed and len(clients.made) == 2                           # one call, then the next started
    assert warm.options.model == "haiku" and warm.options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == str(200 + THINK_HEADROOM)
    assert [k.get("warm") for _, k in usage] == [False, True]
    assert "claude reply cold" in caplog.text and "claude reply warm" in caplog.text
    assert "привіт" not in caplog.text and "як ти" not in caplog.text and "Тепло" not in caplog.text
    assert prompts_left(tmp_path) == []                                     # every prompt file removed


@pytest.mark.parametrize("change", ["slow", "cap", "kind"])
def test_a_call_that_does_not_match_the_waiting_cli_goes_cold_and_starts_the_next(tmp_path, change):
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients()
    c, usage = claude(tmp_path, sdk, clients)
    other = {"slow": {"system": "ІНШИЙ КАНОН\n\nПРАВИЛА", "slow": "ІНШИЙ КАНОН"}, "cap": {"cap": 400},
             "kind": {"kind": "summary"}}[change]

    async def go():
        await voice(c)
        await settle()
        out = await voice(c, **other)
        await settle()
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("Холодно.", "stop") and len(sdk.calls) == 2
    assert clients.made[0].prompts == [] and clients.made[0].closed     # never used: closed
    if change == "kind":                                                # the background never warms one
        assert len(clients.made) == 1 and usage[-1][1].get("warm") is None
    else:
        assert len(clients.made) == 2 and usage[-1][1].get("warm") is False


def test_without_a_slow_part_nothing_is_started_ahead(tmp_path):
    sdk, clients = FakeSDK(), Clients()
    c, usage = claude(tmp_path, sdk, clients)

    async def go():
        await voice(c, slow=None)
        await settle()
    asyncio.run(go())
    assert clients.made == [] and usage[-1][1].get("warm") is None


# --- bounded: a failed or hung one goes cold once --------------------------------------------------------------------
@pytest.mark.parametrize("connect", ["fail", "hang"])
def test_a_cli_that_cannot_start_leaves_the_call_cold(tmp_path, connect):
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients(connect=connect)
    c, _ = claude(tmp_path, sdk, clients)

    async def go():
        await voice(c)
        await settle()
        out = await voice(c)
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("Холодно.", "stop") and len(sdk.calls) == 2


@pytest.mark.parametrize("script", ["hang", [INIT_OK, RuntimeError("CLI gone")]])
def test_a_warm_call_that_hangs_or_fails_goes_cold_once(tmp_path, monkeypatch, script):
    monkeypatch.setattr(sdk_mod, "REPLY_TIMEOUT_S", 0.2)
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients(script, [INIT_OK, result("Тепло.")])
    c, usage = claude(tmp_path, sdk, clients)

    async def go():
        await voice(c)
        await settle()
        out = await voice(c)
        await settle()
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("Холодно.", "stop") and len(sdk.calls) == 2
    assert clients.made[0].closed and [k.get("warm") for _, k in usage] == [False, True, False]


# --- every check kept ------------------------------------------------------------------------------------------------
def test_a_bad_api_key_source_on_a_warm_call_blocks_and_goes_to_gemini(tmp_path):
    bad = SystemMessage(subtype="init", data={"apiKeySource": "ANTHROPIC_API_KEY", "tools": []})
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients([bad, result("Тепло.")])
    c, _ = claude(tmp_path, sdk, clients, fallback=FakeGemini())

    async def go():
        await voice(c)
        await settle()
        out = await voice(c)
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("gemini", "stop") and c.blocked


def test_a_refusal_on_a_warm_call_is_a_decline_and_overage_mutes(tmp_path):
    over = RateLimitEvent(rate_limit_info=SimpleNamespace(status="allowed", resets_at=None, utilization=1.0,
                                                          rate_limit_type="five_hour", raw={"isUsingOverage": True}))
    refusal = [INIT_OK, result("API Error: … Details: `[bio]`", is_error=True, stop_reason="refusal"),
               ResultError("exit 1")]
    sdk = FakeSDK([INIT_OK, result("Холодно.")])
    clients = Clients(refusal, [INIT_OK, over, result("Платно.")])
    c, usage = claude(tmp_path, sdk, clients, limit_fallback="silent")

    async def go():
        await voice(c)
        await settle()
        declined = await voice(c, kind="reply")
        await settle()
        paid = await voice(c)
        await c.close()
        await settle()
        return declined, paid
    declined, paid = asyncio.run(go())
    assert declined is None and usage[1][1].get("blocked") == "refusal" and usage[1][1].get("warm") is True
    assert paid is None and c.muted()


def test_a_warm_cli_answer_is_joined_from_its_parts_and_its_file_is_removed(tmp_path):
    parts = [INIT_OK, AssistantMessage(content=[TextBlock(text="- 09:00 кава\n- 12:00 ")]),
             AssistantMessage(content=[TextBlock(text="ринок")]), result("ринок")]
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients(parts)
    c, _ = claude(tmp_path, sdk, clients)

    async def go():
        await voice(c)
        await settle()
        out = await voice(c)
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("- 09:00 кава\n- 12:00 ринок", "stop") and prompts_left(tmp_path) == []


def test_a_waiting_cli_past_its_life_is_closed_and_the_call_goes_cold(tmp_path, monkeypatch):
    sdk, clients = FakeSDK([INIT_OK, result("Холодно.")]), Clients()
    c, _ = claude(tmp_path, sdk, clients)

    async def go():
        await voice(c)
        await settle()
        c._warm.born -= sdk_mod.WARM_IDLE_S + 1                 # an hour unused
        out = await voice(c)
        await c.close()
        await settle()
        return out
    assert asyncio.run(go()) == ("Холодно.", "stop") and clients.made[0].closed and clients.made[0].prompts == []


def test_a_faked_query_with_no_client_never_starts_a_real_cli(tmp_path):
    c = ClaudeClient(reply_model="haiku", background_model="haiku", config_dir=str(tmp_path / "cfg"),
                     status_file=tmp_path / "s.json", sink=None, query=FakeSDK().query,
                     options=lambda **o: SimpleNamespace(**o))

    async def go():
        await voice(c)
        await settle()
    asyncio.run(go())
    assert c._warm is None


def test_one_call_per_cli_never_two(tmp_path):
    clients = Clients()

    async def go():
        made = WarmCli(("k",), SimpleNamespace(system_prompt={"path": str(tmp_path / "s.md")}), None, clients,
                       lambda: 0.0)
        (tmp_path / "s.md").write_text("КАНОН", encoding="utf-8")
        await settle()
        answer = [m async for m in made.query(prompt="одне")]
        await settle()
        with pytest.raises(RuntimeError, match="one call"):
            made.query(prompt="друге")
        return answer
    assert len(asyncio.run(go())) == 2 and clients.made[0].closed and clients.made[0].prompts == ["одне"]


# --- the numbers -----------------------------------------------------------------------------------------------------
def test_the_usage_line_marks_a_warm_call_and_speed_shows_warm_and_cold_apart():
    warm = sdk_usage_line("2026-11-11T10:00:00+02:00", "ada", "reply", "claude-haiku-5-5", {}, True, None, 900,
                          warm=True)
    cold = sdk_usage_line("2026-11-11T10:05:00+02:00", "ada", "reply", "claude-haiku-5-5", {}, True, None, 2300,
                          warm=False)
    himself = sdk_usage_line("2026-11-11T10:06:00+02:00", "claude", "reply", "claude-opus-5-5", {}, True, None, 5000)
    assert (warm["warm"], cold["warm"], himself["warm"]) == (True, False, None)
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    detail = analyze_detail([warm, cold, himself], [], date(2026, 11, 11), date(2026, 11, 11), None, now)
    names = {m["model"] for s in detail["speed"]["services"] for m in s["models"]}
    assert {"claude-haiku-5-5 · warm", "claude-haiku-5-5 · cold", "claude-opus-5-5"} <= names
