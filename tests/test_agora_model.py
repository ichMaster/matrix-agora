"""7.6 (the owner, 2026-11-15: «зробити щоб Кіра і Устина відповідали в Агорі на 2.5 флеш … зі мною на іншій
моделі») — a companion's Agora replies on a Gemini model of their own (`AGORA_REPLY_MODEL`), whatever her answer
switch; her answers to him stay on hers (the SDK and the responders faked; made-up lines only)."""

import asyncio
from types import SimpleNamespace

from agents.answers import SwitchedResponder
from agents.responder import Reply, Turn
from agents.settings import BY_NAME, concerns
from agents.usage import PROMPT_SLOW
from tests.test_gemini_cache import START, TAIL, gemini, history
from tests.test_settings import ROOM


class Models:
    def __init__(self):
        self.models = []

    async def generate_content(self, model, contents, config):
        self.models.append(model)
        return SimpleNamespace(text="Привіт!", usage_metadata=None, prompt_feedback=None, candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[SimpleNamespace(text="Привіт!", thought=False)]), finish_reason="STOP",
            safety_ratings=None)])


def ask(g, kind):
    async def go():
        token = PROMPT_SLOW.set(START)
        try:
            return await g.reply("\n".join(history(4)), f"{START}\n\n{TAIL}", 4096, kind)
        finally:
            PROMPT_SLOW.reset(token)
    return asyncio.run(go())


def test_her_agora_replies_go_on_her_agora_model_and_her_answers_to_him_on_hers():
    models = Models()
    g = gemini(models=models)
    g.agora_model = "gemini-2.5-flash"
    assert ask(g, "reply")[0] == "Привіт!" and ask(g, "private")[0] == "Привіт!"
    assert models.models == ["gemini-2.5-flash", "gemini-3.1-pro-preview"]
    g.agora_model = None
    ask(g, "reply")
    assert models.models[-1] == "gemini-3.1-pro-preview"                            # unset: as hers


class Says:
    def __init__(self, name):
        self.name, self.kinds = name, []

    async def respond(self, turn):
        self.kinds.append(turn.kind)
        return Reply(self.name, "stop")


def test_the_switch_sends_agora_to_gemini_whatever_her_choice_when_her_agora_model_is_set():
    base, sonnet = Says("gemini"), Says("sonnet")
    on = [True]
    switch = SwitchedResponder(lambda: "api-sonnet", {"api-sonnet": sonnet}, base, agora_on_base=lambda: on[0])
    turn = lambda kind: Turn([], "Інструкція.", 400, kind)
    assert asyncio.run(switch.respond(turn("reply"))).text == "gemini"
    assert asyncio.run(switch.respond(turn("private"))).text == "sonnet"
    on[0] = False
    assert asyncio.run(switch.respond(turn("reply"))).text == "sonnet"               # unset: the switch's


def test_the_setting_is_a_companions_own():
    s = BY_NAME["AGORA_REPLY_MODEL"]
    assert s.default == "" and "gemini-2.5-flash" in s.choices
    assert {n for n, m in ROOM.items() if concerns(s, m)} == {n for n, m in ROOM.items() if m.can("private")}
