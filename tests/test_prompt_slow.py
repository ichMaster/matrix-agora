"""v7.2 (AGORA-242) — the slow part of an answer's prompt: the canon and the life section, the prefix of the instruction,
set for the call (`PROMPT_SLOW`) beside the whole, so that `ClaudeClient` can give it to a CLI started ahead; Hermes's
brief is his whole slow part; Gemini's calls get the whole, as before (nio and the model mocked; no network)."""
import asyncio
from types import SimpleNamespace

from agents.claude_sdk import split_prompt
from agents.logic import build_instruction, slow_part
from agents.responder import Reply
from agents.usage import PROMPT_SLOW
from tests.test_answers import agora


# --- the pure parts -------------------------------------------------------------------------------------------------
def test_split_prompt_gives_the_slow_part_and_the_rest_or_nothing():
    assert split_prompt("КАНОН\n\nЖИТТЯ\n\nМісце і час", "КАНОН\n\nЖИТТЯ") == ("КАНОН\n\nЖИТТЯ", "Місце і час")
    assert split_prompt("КАНОН\n\nМісце", "ІНШИЙ КАНОН") is None          # not its prefix
    assert split_prompt("КАНОН", None) is None and split_prompt("КАНОН", "") is None
    assert split_prompt(None, "КАНОН") is None
    assert split_prompt("КАНОН", "КАНОН") == ("КАНОН", "")                 # all of it slow (Hermes's brief)


def test_the_slow_part_is_the_canon_then_the_life_the_prompts_own_prefix():
    with_life = build_instruction(name="Ада", canon="КАНОН", life="ЖИТТЯ", world="Зараз 17:02")
    assert slow_part(with_life, "КАНОН", "ЖИТТЯ") == "КАНОН\n\nЖИТТЯ"
    slow, rest = split_prompt(with_life, slow_part(with_life, "КАНОН", "ЖИТТЯ"))
    assert f"{slow}\n\n{rest}" == with_life and rest.startswith("Зараз 17:02")   # nothing lost
    no_life = build_instruction(name="Ада", canon="КАНОН", world="Зараз 17:02")
    assert slow_part(no_life, "КАНОН", None) == "КАНОН"
    assert slow_part(no_life, "", None) is None and slow_part("ІНШЕ", "КАНОН", None) is None


# --- an answer's call carries it ------------------------------------------------------------------------------------
class Watcher:
    """A responder that notes the slow part its call sees, and the instruction."""

    def __init__(self):
        self.seen = []

    async def respond(self, turn):
        self.seen.append((PROMPT_SLOW.get(), turn.instruction))
        return Reply("Звісно.", "stop")


def test_an_answers_call_carries_the_slow_part_of_its_own_prompt_and_only_during_it(tmp_path):
    agent = agora(tmp_path)
    agent.responder = watcher = Watcher()
    agent.history = [("Ich", "Привіт, як ти?")]
    assert asyncio.run(agent.reply("!room")) is True
    [(slow, instruction)] = watcher.seen
    assert slow and slow.startswith(agent.cfg.canon) and instruction.startswith(slow)
    got = split_prompt(instruction, slow)
    assert got is not None and f"{got[0]}\n\n{got[1]}" == instruction           # the whole, in two parts
    assert PROMPT_SLOW.get() is None                                             # never outside the call


def test_a_call_with_a_prompt_not_built_last_carries_none(tmp_path):
    agent = agora(tmp_path)
    agent.responder = watcher = Watcher()
    agent.build_prompt()                                  # built, but another prompt is sent
    asyncio.run(agent._compose("Інша інструкція.", lines=[("Ich", "Привіт")]))
    assert watcher.seen == [(None, "Інша інструкція.")]


# --- Hermes: his brief is his slow part ------------------------------------------------------------------------------
def test_hermess_think_call_carries_his_whole_brief_as_its_slow_part(tmp_path):
    from agents.herald import Herald
    from tests.test_herald import CFG, ROSTER
    seen = []

    class LLM:
        async def think(self, contents, system, model=None, kind="", level=None, **kw):
            seen.append((PROMPT_SLOW.get(), system))
            return "Сьогодні в кімнаті говорили про гори."

    h = Herald(CFG, roster=ROSTER, client=SimpleNamespace(), state_dir=tmp_path, llm=LLM())

    async def no_typing(on):
        return None
    h._typing = no_typing
    out, _ = asyncio.run(h._think("розмова", "БРИФ ГЕРМЕСА", "digest_voice", 1500))
    assert out and seen == [("БРИФ ГЕРМЕСА", "БРИФ ГЕРМЕСА")] and PROMPT_SLOW.get() is None
