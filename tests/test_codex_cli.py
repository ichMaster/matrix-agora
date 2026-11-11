"""v7.4 (AGORA-252) — a companion's answer on GPT-6.1 Sol through the Codex CLI on the owner's ChatGPT plan: the run's
argv and environment (no text, no secret, no tool), its JSON events, the login it must have (ChatGPT, else blocked; none,
then looked at again), its limit (her Gemini meanwhile), a tool or a refusal, a timeout, its usage line, and the agent
building it where the CLI is (a fake process; no real CLI, nothing reaches the network; made-up lines only)."""

import asyncio
import json
import logging
import os
import stat
from pathlib import Path

from agents.claude_sdk import LAST_SERVED
from agents.codex_cli import FEATURES_OFF, MODEL, CodexAnswers, clean_env, parse_events, run_args
from agents.llm import LAST_BLOCK
from agents.usage import api_usage_line, parse_lines
from tests.test_private_route import her

SYSTEM = "Ти — Кіра. Канон."
OK_EVENTS = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
             {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": ""}},
             {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "Привіт, сонце."}},
             {"type": "turn.completed", "usage": {"input_tokens": 9000, "cached_input_tokens": 8000,
                                                   "output_tokens": 300}}]
LIMIT_EVENTS = [{"type": "turn.started"},
                {"type": "turn.failed", "error": {"message": "You've hit your usage limit. Try again later."}}]


def jsonl(events):
    return ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode("utf-8")


class Proc:
    def __init__(self, out=b"", code=0, delay=0.0):
        self.out, self.returncode_after, self.delay = out, code, delay
        self.returncode, self.stdin, self.killed = None, None, False

    async def communicate(self, data=None):
        self.stdin = data
        if self.delay:
            await asyncio.sleep(self.delay)
        self.returncode = self.returncode_after
        return self.out, b""

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


class Spawn:
    """`asyncio.create_subprocess_exec`, faked: `login status` says `status`; `exec` runs `events` (or hangs)."""

    def __init__(self, status=b"Logged in using ChatGPT\n", status_code=0, events=OK_EVENTS, delay=0.0):
        self.status, self.status_code, self.events, self.delay = status, status_code, events, delay
        self.runs, self.instructions = [], []

    async def __call__(self, *args, **kwargs):
        self.runs.append({"args": list(args), "env": kwargs.get("env"), "cwd": kwargs.get("cwd")})
        if args[1:3] == ("login", "status"):
            return Proc(self.status, self.status_code)
        path = next(a.split("=", 1)[1].strip('"') for a in args if str(a).startswith("model_instructions_file="))
        file = Path(path)
        self.instructions.append((path, file.read_text(encoding="utf-8"), stat.S_IMODE(file.stat().st_mode)))
        proc = Proc(jsonl(self.events), 0, self.delay)
        self.last = proc
        return proc

    def execs(self):
        return [r for r in self.runs if r["args"][1] == "exec"]


class Gemini:
    def __init__(self):
        self.calls = []

    async def reply(self, transcript, system, cap, kind):
        self.calls.append(kind)
        return "Від Gemini.", "stop"


class Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, kind, model, usage, ok, blocked=None, latency_ms=None):
        self.calls.append({"kind": kind, "model": model, "usage": usage, "ok": ok, "blocked": blocked})


def codex(tmp_path, spawn, **kw):
    clock = kw.pop("clock", [0.0])
    return CodexAnswers(home=tmp_path / "kira.codex", work=tmp_path / "work", sink=kw.pop("sink", Sink()),
                        spawn=spawn, mono=lambda: clock[0], **kw)


def run(coro):
    async def inside():
        out = await coro
        return out, LAST_BLOCK.get(), LAST_SERVED.get()
    return asyncio.run(inside())


# --- pure ----------------------------------------------------------------------------------------------------------
def test_the_events_give_the_answer_its_usage_a_tool_and_a_limit():
    got = parse_events([json.dumps(e) for e in OK_EVENTS] + ["not json"])
    assert (got.text, got.usage, got.tools, got.failed) == (
        "Привіт, сонце.", {"input_tokens": 9000, "cached_tokens": 8000, "output_tokens": 300}, [], None)
    tool = parse_events([json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
                         json.dumps({"type": "item.completed", "item": {"type": "error", "message": "x"}})])
    assert tool.tools == ["command_execution"]
    limit = parse_events([json.dumps(e) for e in LIMIT_EVENTS])
    assert limit.limit and limit.failed == "limit"
    other = parse_events([json.dumps({"type": "turn.failed", "error": {"message": "stream disconnected"}})])
    assert other.failed == "error" and not other.limit


def test_the_run_carries_no_text_and_no_tool_and_its_environment_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-never")
    monkeypatch.setenv("GEMINI_API_KEY", "g-never")
    args = run_args("codex", tmp_path / "work", "medium", tmp_path / "p.md")
    assert args[:3] == ["codex", "exec", "--json"] and args[-1] == "-" and MODEL in args
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "forced_login_method=chatgpt",
                 "approval_policy=never", "web_search=disabled", "history.persistence=none", "project_doc_max_bytes=0",
                 "model_reasoning_effort=medium"):
        assert flag in args
    assert args[args.index("-s") + 1] == "read-only"
    assert all(f in args for f in FEATURES_OFF) and "shell_tool" in FEATURES_OFF
    env = clean_env(tmp_path / "home", tmp_path / "work")
    assert set(env) == {"CODEX_HOME", "HOME", "PATH", "LANG"} and "sk-never" not in json.dumps(env)


# --- the answer ----------------------------------------------------------------------------------------------------
def test_an_answer_her_instruction_by_a_0600_file_removed_after_the_transcript_by_stdin(tmp_path):
    spawn, sink = Spawn(), Sink()
    client = codex(tmp_path, spawn, sink=sink)
    out, block, _ = run(client.reply("Ich: Привіт", SYSTEM, 4096, "private"))
    assert out == ("Привіт, сонце.", "stop") and block is None
    path, text, mode = spawn.instructions[0]
    assert text == SYSTEM and mode == 0o600 and not os.path.exists(path)
    assert spawn.last.stdin == "Ich: Привіт".encode()
    assert "Привіт" not in " ".join(spawn.execs()[0]["args"])               # never a text on argv
    assert sink.calls == [{"kind": "private", "model": MODEL, "usage": {"input_tokens": 9000, "cached_tokens": 8000,
                                                                          "output_tokens": 300}, "ok": True,
                           "blocked": None}]
    assert stat.S_IMODE(os.stat(tmp_path / "kira.codex").st_mode) == 0o700


def test_not_signed_in_is_silence_looked_at_again_later_and_a_sign_in_works_with_no_restart(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    clock = [0.0]
    spawn = Spawn(status=b"Not logged in\n", status_code=1)
    client = codex(tmp_path, spawn, clock=clock)
    assert run(client.reply("x", SYSTEM, 100, "private"))[0] is None and spawn.execs() == []
    assert run(client.reply("x", SYSTEM, 100, "private"))[0] is None and len(spawn.runs) == 1  # within the TTL
    spawn.status, spawn.status_code, clock[0] = b"Logged in using ChatGPT\n", 0, 301.0
    assert run(client.reply("x", SYSTEM, 100, "private"))[0] == ("Привіт, сонце.", "stop")
    assert "not signed in" in caplog.text


def test_any_other_login_blocks_it_for_good_and_its_words_are_never_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    spawn = Spawn(status=b"Logged in using an API key - sk-proj-***abcd\n")
    client = codex(tmp_path, spawn)
    assert run(client.reply("x", SYSTEM, 100, "private"))[0] is None and client.blocked and spawn.execs() == []
    assert run(client.reply("x", SYSTEM, 100, "private"))[0] is None and len(spawn.runs) == 1
    assert "sk-proj" not in caplog.text and "blocked" in caplog.text


def test_at_its_limit_her_gemini_answers_until_the_mute_ends(tmp_path):
    clock, gemini = [0.0], Gemini()
    spawn = Spawn(events=LIMIT_EVENTS)
    client = codex(tmp_path, spawn, clock=clock, gemini=gemini)
    out, _, served = run(client.reply("x", SYSTEM, 4096, "private"))
    assert out == ("Від Gemini.", "stop") and served == "gemini" and len(spawn.execs()) == 1
    clock[0] = 1800.0                                                      # still muted: Codex never asked
    assert run(client.reply("x", SYSTEM, 4096, "reply"))[0] == ("Від Gemini.", "stop") and len(spawn.execs()) == 1
    spawn.events, clock[0] = OK_EVENTS, 3601.0
    assert run(client.reply("x", SYSTEM, 4096, "private"))[0] == ("Привіт, сонце.", "stop")
    assert gemini.calls == ["private", "reply"]


def test_a_tool_a_refusal_and_a_timeout_are_no_answer(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    tool = Spawn(events=[{"type": "item.started", "item": {"type": "command_execution"}}, *OK_EVENTS])
    assert run(codex(tmp_path, tool).reply("x", SYSTEM, 100, "private"))[0] is None and "used a tool" in caplog.text
    refused = Spawn(events=[{"type": "item.completed", "item": {"type": "agent_message",
                                                               "text": "Я не можу виконати цей запит."}}])
    out, block, _ = run(codex(tmp_path, refused).reply("x", SYSTEM, 100, "private"))
    assert out is None and block[0] == "refusal"
    slow = Spawn(delay=1.0)
    assert run(codex(tmp_path, slow, timeout_s=0.01).reply("x", SYSTEM, 100, "private"))[0] is None
    assert slow.last.killed and "timed out" in caplog.text


def test_its_usage_line_is_the_chatgpt_plans_never_priced():
    line = api_usage_line("2026-11-11T18:00:00+02:00", "kira", "private", MODEL, "codex",
                          {"input_tokens": 9000, "cached_tokens": 8000, "output_tokens": 300}, True)
    assert (line["engine"], line["billing"]) == ("codex", "subscription")
    assert parse_lines([json.dumps(line)]) == ([line], 0)


# --- the agent -----------------------------------------------------------------------------------------------------
def test_the_agent_builds_codex_where_its_cli_is_with_her_home_in_her_state(tmp_path, monkeypatch):
    cli = tmp_path / "bin" / "codex"
    cli.parent.mkdir()
    cli.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setenv("CODEX_BIN", str(cli))
    agent = her(tmp_path, monkeypatch)
    assert "codex-gpt-6.1sol" in agent.switch.available()
    client = agent.switch.responders["codex-gpt-6.1sol"].llm
    assert client.home == tmp_path / "kira.codex" and client.gemini is agent.llm and client.binary == str(cli)
