"""v7.6 (AGORA-260) — her memory as Lumi's (`MEMORY_MODE = lumi`): the live window of `n` to `n + batch` lines after
the last one folded, the oldest whole batches of her day folded into a running digest (checked as a talk summary,
written gentler when it blocks), an earlier day's lines passed over, the digest in the prompt's tail, empty again at
her midnight; the switch read at each use; the cache's start alone in `lumi`, and v7.5 code review #9 (the model
faked; an injected clock; made-up lines only)."""

import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agents.agent import Agent
from agents.gemini_cache import START_ONLY_S, CachePlanner
from agents.logic import instruction_and_start
from agents.lumi import (
    DIGEST_TITLE,
    Digest,
    batches_due,
    load_digest,
    lumi_window_start,
    rolled,
    save_digest,
    talk_digest_request,
    talk_digest_section,
)
from agents.memory import HUMAN_MEMORY
from agents.settings import OVERRIDES_FILE, save_json
from agents.talk import TALK_GENTLE
from tests.test_archive import EmbedLLM, kira

KYIV = ZoneInfo("Europe/Kyiv")
SECRET = "заборонене-760"  # what the fake model's check blocks, in a made-up line


def ms(*a, tz=KYIV):
    return int(datetime(*a, tzinfo=tz).timestamp() * 1000)


NOW = ms(2026, 11, 14, 18, 0)


# --- the window and the batches (pure) ------------------------------------------------------------------------------
def test_the_live_window_is_n_to_n_plus_a_batch_after_the_last_line_folded():
    times = list(range(100))
    assert lumi_window_start(times, -1, 40, 20) == 40                     # nothing folded: the last n + batch
    assert lumi_window_start(times, 49, 40, 20) == 50                     # after the fold point: 50 lines
    assert lumi_window_start(times, 79, 40, 20) == 60                     # never fewer than n
    assert lumi_window_start(times, 49, 40, 20, keep_from=30) == 30       # his unanswered lines always
    assert lumi_window_start(times[:25], -1, 40, 20) == 0                 # fewer than n: all of them
    assert lumi_window_start([], 0, 40, 20) == 0


def test_whole_batches_fold_once_n_plus_a_batch_wait():
    assert batches_due(59, 40, 20) == 0 and batches_due(60, 40, 20) == 1 and batches_due(79, 40, 20) == 1
    assert batches_due(300, 40, 20) == 13                                 # the first switch: a backlog
    assert batches_due(300, 40, 0) == 0


# --- the digest's file and text (pure) ------------------------------------------------------------------------------
def test_the_digest_rolls_at_her_midnight_keeping_the_last_day_and_the_fold_point(tmp_path):
    d = Digest("2026-11-13", 500, "Учора ми говорили про зорі.")
    assert rolled(d, "2026-11-13") is d
    new = rolled(d, "2026-11-14")
    assert (new.day, new.upto_ms, new.text, new.previous_day, new.previous_text) == \
        ("2026-11-14", 500, "", "2026-11-13", "Учора ми говорили про зорі.")
    assert rolled(rolled(new, "2026-11-15"), "2026-11-15").previous_text == "Учора ми говорили про зорі."  # empty day
    path = tmp_path / "kira.digest.json"
    save_digest(path, new)
    assert load_digest(path) == new and oct(os.stat(path).st_mode & 0o777) == "0o600"
    path.write_text("{не json", encoding="utf-8")
    assert load_digest(path) == Digest() and load_digest(tmp_path / "немає.json") == Digest()


def test_the_section_is_todays_digest_only_and_the_request_her_own_memory_gentler_each_time():
    d = Digest("2026-11-14", 0, "Ми говорили про Атакаму.")
    assert talk_digest_section(d, "2026-11-14") == f"{DIGEST_TITLE}\nМи говорили про Атакаму."
    assert talk_digest_section(d, "2026-11-15") is None and talk_digest_section(Digest("2026-11-14"), "2026-11-14") is None
    system, contents = talk_digest_request("Кіра", "Канон.", "Раніше — про зорі.", [("Ich", "Привіт"), ("Кіра", "Хай!")],
                                           120, strict=2)
    assert system.startswith("Канон.") and HUMAN_MEMORY in system and TALK_GENTLE[2] in system and "120" in system
    assert "Раніше — про зорі." in contents and contents.endswith("Ich: Привіт\nКіра: Хай!")
    assert "модел" not in system.lower() and "бот" not in system.lower()


def test_the_digest_stands_in_the_tail_after_today_and_never_in_the_start():
    prompt, start = instruction_and_start(name="Кіра", canon="КАНОН", memories="СПОГАДИ", talk="РОЗМОВИ",
                                          world="Зараз 18:00", today="СЬОГОДНІ", digest="ДАЙДЖЕСТ", thoughts="ДУМКИ")
    assert start == "КАНОН\n\nСПОГАДИ\n\nРОЗМОВИ" and "ДАЙДЖЕСТ" not in start
    assert prompt.index("СЬОГОДНІ") < prompt.index("ДАЙДЖЕСТ") < prompt.index("ДУМКИ")
    assert instruction_and_start(name="Кіра", canon="КАНОН", today="СЬОГОДНІ") == \
        instruction_and_start(name="Кіра", canon="КАНОН", today="СЬОГОДНІ", digest=None)


# --- the agent ------------------------------------------------------------------------------------------------------
class Folder(EmbedLLM):
    """The digest's model (`complete`) and the check (`probe`): blocks a digest holding `SECRET` the first `blocking`
    times (or always), fails when `down`; records each call."""

    model = "gemini-2.5-flash"
    reply_model = "gemini-3.1-pro-preview"

    def __init__(self, blocking=0, down=False, check_down=False):
        super().__init__()
        self.folds, self.checks, self.blocking, self.down, self.check_down = [], [], blocking, down, check_down

    async def complete(self, transcript, system_instruction, max_output_tokens=400, kind="reply", model=None,
                       refusal=False):
        self.folds.append({"contents": transcript, "system": system_instruction, "kind": kind, "model": model})
        if self.down:
            return None
        return f"Пам'ятаю {transcript.count(chr(10)) + 1} рядків" + (f" {SECRET}" if self.blocking else "") + ".", "stop"

    async def probe(self, transcript, system_instruction, kind="probe"):
        self.checks.append(kind)
        if self.check_down:
            return None
        if SECRET in transcript and self.blocking:
            self.blocking -= 1
            return True
        return False


def lumi(tmp_path, monkeypatch, llm=None, n=4, batch=2):
    agent = kira(tmp_path, monkeypatch, llm or Folder())
    monkeypatch.setenv("MEMORY_MODE", "lumi")
    agent.live_window_n, agent.live_window_batch = n, batch
    agent.clock = lambda: NOW
    return agent


def say(agent, key, when, who, text, mark=None):
    agent.archive.append(key, when, "private", "telegram", who, text)
    if mark:
        agent.archive.mark([key], mark)


def seeded(agent):
    for i, h in enumerate((20, 21, 22)):                                   # yesterday evening
        say(agent, f"y{i}", ms(2026, 11, 13, h), "Ich" if i % 2 == 0 else "Кіра", f"учора {i}")
    for i in range(8):                                                     # today, one closed
        say(agent, f"t{i}", ms(2026, 11, 14, 9, i), "Ich" if i % 2 == 0 else "Кіра", f"сьогодні {i}",
            mark="blocked" if i == 3 else None)


def tick(agent):
    agent._digest_check_ms = 0
    asyncio.run(agent.ensure_talk_digest())


def test_her_days_oldest_batches_are_folded_an_earlier_days_passed_over_and_never_a_closed_line(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    seeded(agent)
    assert agent.talk_digest_is_due()
    tick(agent)  # 10 open lines, n 4, batch 2: three batches — [y0 y1] passed over, [y2 t0], [t1 t2] folded
    folds = agent.llm.folds
    assert len(folds) == 2 and {f["kind"] for f in folds} == {"talk_digest"} and folds[0]["model"] == "gemini-2.5-flash"
    sent = "".join(f["contents"] for f in folds)
    assert "сьогодні 0" in sent and "сьогодні 2" in sent and "учора" not in sent and "сьогодні 3" not in sent
    assert "Пам'ятаю" in folds[1]["contents"]                               # the digest so far, then the batch
    digest = load_digest(agent.digest_file)
    assert digest.day == "2026-11-14" and digest.upto_ms == ms(2026, 11, 14, 9, 2) and digest.text.startswith("Пам'ятаю")
    assert [x.text for x in agent._gemini_lines()] == ["сьогодні 4", "сьогодні 5", "сьогодні 6", "сьогодні 7"]
    layers = agent.prompt_layers(private="Бриф.", talk=True)
    assert layers["digest"].startswith(DIGEST_TITLE) and digest.text in layers["digest"]
    tick(agent)
    assert len(agent.llm.folds) == 2                                        # nothing more is due


def test_a_fold_that_blocks_is_written_gentler_and_when_it_always_blocks_the_digest_stays(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch, Folder(blocking=1))
    seeded(agent)
    tick(agent)
    assert TALK_GENTLE[1] in agent.llm.folds[1]["system"]                   # the second write, one step stricter
    assert SECRET not in load_digest(agent.digest_file).text and "lumi_check" in agent.llm.checks


def test_a_fold_that_always_blocks_leaves_the_batch_out_of_the_digest_and_moves_on(tmp_path, monkeypatch):
    stuck = lumi(tmp_path, monkeypatch, Folder(blocking=99))
    seeded(stuck)
    tick(stuck)
    digest = load_digest(stuck.digest_file)
    assert digest.text == "" and digest.upto_ms == ms(2026, 11, 14, 9, 2)
    assert len(stuck.llm.folds) == 2 * len(TALK_GENTLE)                     # each batch written three times


@pytest.mark.parametrize("llm", [Folder(down=True), Folder(check_down=True)], ids=["model down", "check down"])
def test_a_failed_fold_leaves_the_batch_waiting_and_backs_off(tmp_path, monkeypatch, llm):
    agent = lumi(tmp_path, monkeypatch, llm)
    seeded(agent)
    tick(agent)
    digest = load_digest(agent.digest_file)
    assert digest.text == "" and digest.upto_ms == ms(2026, 11, 13, 21)       # the passed-over batch alone
    assert agent._digest_retry_ms > NOW and not agent.talk_digest_is_due()


def test_at_her_midnight_the_digest_starts_empty_and_the_last_day_is_kept(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    save_digest(agent.digest_file, Digest("2026-11-13", ms(2026, 11, 13, 22), "Учора про зорі."))
    seeded(agent)
    tick(agent)
    digest = load_digest(agent.digest_file)
    assert digest.day == "2026-11-14" and digest.previous_text == "Учора про зорі." and "Учора" not in digest.text


def test_her_midnight_is_her_own_clocks_far_away(tmp_path, monkeypatch):
    south = lumi(tmp_path, monkeypatch)
    monkeypatch.setattr(Agent, "tz", property(lambda self: "America/Santiago"))  # her nights in Chile (v5.27)
    south.clock = lambda: ms(2026, 11, 14, 23, 30, tz=ZoneInfo("America/Santiago"))
    say(south, "c0", ms(2026, 11, 14, 22, tz=ZoneInfo("America/Santiago")), "Ich", "у Чилі ще 14-те")
    assert south.talk_digest_now(datetime.fromtimestamp(south.clock() / 1000, ZoneInfo("America/Santiago"))) is None
    tick(south)
    assert load_digest(south.digest_file).day == "2026-11-14"               # her day, not Kyiv's 15th


def test_layered_is_as_before_and_the_switch_is_read_at_each_use(tmp_path, monkeypatch):
    agent = lumi(tmp_path, monkeypatch)
    seeded(agent)
    monkeypatch.delenv("MEMORY_MODE")
    assert agent.memory_mode() == "layered" and not agent.talk_digest_is_due()
    assert agent.prompt_layers(private="Бриф.", talk=True)["digest"] is None
    save_json(agent.memory_file.parent / OVERRIDES_FILE, {"services": {}, "agents": {"kira": {"MEMORY_MODE": "lumi"}}})
    assert agent.memory_mode() == "lumi"                                    # the panel's, at once
    save_json(agent.memory_file.parent / OVERRIDES_FILE, {"services": {}, "agents": {"kira": {"MEMORY_MODE": "x"}}})
    assert agent.memory_mode() == "layered"


# --- the cache ------------------------------------------------------------------------------------------------------
def test_in_lumi_the_cache_holds_the_start_alone_and_a_slid_historys_start_only_cache_ends_v75_review_9():
    p = CachePlanner(ttl_s=3600, rebuild_lines=40)
    lines = [f"l{i}" for i in range(50)]
    p.plan("private", "m", "S", lines, 0, start_only=True)
    made = p.plan("private", "m", "S", lines, 10, start_only=True)
    assert (made.action, made.lines) == ("make", 0)
    p.made("private", "c1", "m", "S", [], 11)
    assert p.plan("private", "m", "S", [f"x{i}" for i in range(9)], 20, start_only=True).action == "use"  # any history
    back = p.plan("private", "m", "S", lines, 30)                          # `layered` again: the history back in
    assert (back.action, back.why, back.lines) == ("make", "grew", 48)
    p.made("private", "c2", "m", "S", lines[:48], 31)
    assert p.plan("private", "m", "S", lines, 40, start_only=True).why == "mode"
    # v7.5 #9: after a slide the start alone, for START_ONLY_S only — then a full cache again
    q = CachePlanner(ttl_s=20_000, rebuild_lines=400)
    q.plan("private", "m", "S", lines, 0)
    q.made("private", "c1", "m", "S", lines[:48], 1)
    slid = lines[1:] + ["n"]
    assert q.plan("private", "m", "S", slid, 2).why == "history"
    q.made("private", "c2", "m", "S", [], 3)
    assert q.plan("private", "m", "S", slid + ["a"], 100).action == "use"
    late = q.plan("private", "m", "S", slid + ["a", "b"], 3 + START_ONLY_S)
    assert (late.action, late.why, late.lines) == ("make", "grew", len(slid))


def test_a_batch_that_keeps_failing_is_passed_over_after_three_tries(tmp_path, monkeypatch):
    """Code review v7.6 #2: a batch the model kept refusing was tried until her midnight, no later batch folded."""
    agent = lumi(tmp_path, monkeypatch, Folder(down=True))
    seeded(agent)
    for _ in range(3):
        agent._digest_retry_ms = 0
        tick(agent)
    digest = load_digest(agent.digest_file)
    assert digest.upto_ms == ms(2026, 11, 14, 9, 0) and digest.text == ""         # [y2 t0] passed over, as it was
    agent.llm.down = False
    agent._digest_retry_ms = 0
    tick(agent)
    assert load_digest(agent.digest_file).text.startswith("Пам'ятаю")             # the next batch folds


def test_the_fold_and_the_window_never_leave_a_line_between_them_whatever_history_n_or_her_cap(tmp_path, monkeypatch):
    """Code review v7.6 #3: with `HISTORY_N` below the window nothing folded, and `PRIVATE_HISTORY_N` cut the window."""
    agent = lumi(tmp_path, monkeypatch, n=4, batch=2)
    agent.history_n, agent.private_history_n = 3, 2                               # both below the window
    seeded(agent)
    tick(agent)
    folded = load_digest(agent.digest_file).upto_ms
    assert folded == ms(2026, 11, 14, 9, 2) and len(agent.llm.folds) == 2
    window = agent._gemini_lines()
    assert [x.text for x in window] == ["сьогодні 4", "сьогодні 5", "сьогодні 6", "сьогодні 7"]
    assert window[0].ts_ms > folded                                                # nothing between them


def test_a_batch_never_ends_inside_one_seconds_lines(tmp_path, monkeypatch):
    """Code review v7.6 #4: his Telegram lines carry a time to the second — a batch ending on the first of two left
    the second in neither her window nor her digest."""
    agent = lumi(tmp_path, monkeypatch, n=2, batch=2)
    for i, t in enumerate([0, 1, 1, 2, 3, 4, 5]):                              # the 2nd and 3rd in one second
        say(agent, f"s{i}", ms(2026, 11, 14, 9, 0, t), "Ich", f"рядок {i}")
    tick(agent)
    sent = "".join(f["contents"] for f in agent.llm.folds)
    assert "Ich: рядок 1" in agent.llm.folds[0]["contents"] and "Ich: рядок 2" in agent.llm.folds[0]["contents"]
    window = [x.text for x in agent._gemini_lines()]
    assert all(f"рядок {i}" in sent or f"рядок {i}" in window for i in range(7))  # nothing lost between them

