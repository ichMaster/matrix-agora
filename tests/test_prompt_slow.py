"""v7.2 (AGORA-242) — the slow part of an answer's prompt: the canon and the life section, the prefix of the instruction,
set for the call (`PROMPT_SLOW`) beside the whole, so that `ClaudeClient` can give it to a CLI started ahead; Hermes's
brief is his whole slow part; Gemini's calls get the whole, as before (nio and the model mocked; no network)."""
import asyncio
from types import SimpleNamespace

from agents.claude_sdk import split_prompt
from agents.logic import instruction_and_start, slow_part
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


def test_the_slow_part_is_the_whole_start_the_prompts_own_prefix():
    """v7.5 (AGORA-255): the start grew from the canon and the life (v7.2) to everything that changes at most hourly."""
    with_life, start = instruction_and_start(name="Ада", canon="КАНОН", life="ЖИТТЯ", world="Зараз 17:02",
                                             memories="СПОГАДИ", mood="НАСТРІЙ", recalled="ЗГАДКА")
    assert start == "КАНОН\n\nЖИТТЯ\n\nСПОГАДИ\n\nНАСТРІЙ" and slow_part(with_life, start) == start
    slow, rest = split_prompt(with_life, slow_part(with_life, start))
    assert f"{slow}\n\n{rest}" == with_life and rest.startswith("Зараз 17:02")   # nothing lost
    no_life, start = instruction_and_start(name="Ада", canon="КАНОН", world="Зараз 17:02")
    assert slow_part(no_life, start) == "КАНОН"
    assert slow_part(no_life, "") is None and slow_part("ІНШЕ", "КАНОН") is None


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
def test_hermess_slow_part_is_his_canon_the_same_for_every_digest(tmp_path):
    """Code review v7.2 #1: his brief names the period and the count — with the whole system as the slow part no
    digest ever went warm; his canon, the prefix of every digest's and answer's system, is the slow part."""
    from agents.digest import chat_request, digest_request
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
    first, _ = digest_request(CFG.canon, ["Ада: привіт"], "з 9:00 до 13:00", 1, 600, 1500, ["Ада"])
    second, _ = digest_request(CFG.canon, ["Бруно: так"], "з 13:00 до 17:00", 5, 900, 1500, ["Бруно"])
    for system in (first, second):
        out, _ = asyncio.run(h._think("розмова", system, "digest_voice", 1500))
        assert out
    assert first != second and [slow for slow, _ in seen] == [CFG.canon, CFG.canon]   # the same: the CLI waits
    assert all(split_prompt(system, slow) for slow, system in seen) and PROMPT_SLOW.get() is None
    asyncio.run(h._think("розмова", "ІНШИЙ БРИФ", "ask", 400))
    assert seen[-1][0] is None                                     # a system that is not his canon's: none
    assert chat_request  # his answers' system starts with his canon too (agents/digest.py)


# --- v7.5 (AGORA-255): the start and the tail -------------------------------------------------------------------------
ALL = {"life": "ЖИТТЯ", "world": "СВІТ", "memories": "СПОГАДИ", "plans": "ПЛАНИ", "today": "СЬОГОДНІ",
       "mood": "НАСТРІЙ", "thoughts": "ДУМКИ", "pastlife": "МИНУЛЕ", "nudge": "ПОШТОВХ", "move": "ХІД",
       "asked": "ПИТАННЯ", "private": "НАОДИНЦІ", "facts": "ФАКТИ", "agora_now": "АГОРА", "recalled": "ЗГАДКА",
       "talk": "РОЗМОВА", "voice": "ГОЛОС"}


def test_every_layer_appears_once_the_slow_ones_in_the_start_the_per_call_ones_in_the_tail():
    prompt, start = instruction_and_start("Кіра", "КАНОН", "ПІДСУМОК", **ALL)
    sections = prompt.split("\n\n")
    assert sorted(sections[:-1]) == sorted(["КАНОН", "Що ти пам'ятаєш з минулої розмови: ПІДСУМОК", *ALL.values()])
    assert sections[-1].startswith("Ти — Кіра.")                                # the rules close it, as ever
    assert start.split("\n\n") == ["КАНОН", "ЖИТТЯ", "СПОГАДИ", "ПЛАНИ", "НАСТРІЙ",
                                   "Що ти пам'ятаєш з минулої розмови: ПІДСУМОК", "ФАКТИ", "РОЗМОВА"]
    assert prompt.startswith(start + "\n\nСВІТ")                                # the tail opens with the time


def test_the_start_is_the_same_whatever_the_time_the_recall_the_move_or_the_style_line(tmp_path):
    agent = agora(tmp_path)
    first = agent.build_prompt(move="Цього разу: запитай", recalled="Тобі згадується: А.")
    from agents.agent import _LAST_PARTS
    start_a = _LAST_PARTS.get()[2]
    agent.clock = lambda: agent_clock_later
    second = agent.build_prompt(move="Цього разу: заперечи", recalled="Тобі згадується: Б.",
                                private="Як сказати цього разу: інакше")
    start_b = _LAST_PARTS.get()[2]
    assert start_a and start_a == start_b and first != second
    assert first.startswith(start_a) and second.startswith(start_b)


agent_clock_later = 1_794_600_000_000 + 37 * 60_000                             # 37 minutes on: a new «Зараз …»
