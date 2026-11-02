"""v5.22 (the owner, 2026-11-02: «аналіз структури промпта … і динаміка»): an answer call's usage line holds its
prompt's parts — each layer's size in characters, the rules, and the history — never a text; a call that is no answer
holds none (nio and the model mocked; no network)."""
import asyncio
import json

from agents.responder import Reply
from tests.test_answers import agora


class Teller:
    """A responder that reports its call the way a model client does — through the agent's usage sink, during the
    call — and answers."""

    def __init__(self, agent):
        self.agent, self.prompts = agent, []

    async def respond(self, turn):
        self.prompts.append(turn.instruction)
        self.agent.record_usage(turn.kind, "m", None, True, latency_ms=1200)
        return Reply("Звісно.", "stop")


def usage_lines(agent) -> list[dict]:
    return [json.loads(x) for x in agent.usage_file.read_text(encoding="utf-8").splitlines()]


def test_an_answers_usage_line_holds_its_prompts_parts_and_the_history(tmp_path):
    agent = agora(tmp_path)
    agent.responder = teller = Teller(agent)
    agent.history = [("Ich", "Привіт, як ти?"), ("Бруно", "Добре.")]
    assert asyncio.run(agent.reply("!room")) is True
    [line] = usage_lines(agent)
    parts = line["prompt_parts"]
    assert {"canon", "rules", "history"} <= set(parts) and all(isinstance(v, int) for v in parts.values())
    assert sum(v for k, v in parts.items() if k != "history") == len(teller.prompts[0])   # the instruction, whole
    assert parts["history"] == len("Ich: Привіт, як ти?\nБруно: Добре.")
    assert "Привіт" not in json.dumps(line, ensure_ascii=False)                          # sizes only, never a text


def test_a_call_that_is_no_answer_holds_no_parts(tmp_path):
    agent = agora(tmp_path)
    agent.record_usage("reflection", "m", None, True)
    assert usage_lines(agent)[0]["prompt_parts"] is None
