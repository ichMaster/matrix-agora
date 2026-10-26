import pytest

from agents.config import AgentConfig
from agents.logic import echo_reply, should_handle, should_join_invite

CFG = AgentConfig(
    name="Ада", user_id="@ada:agora.lan", canon="Канон.",
    homeserver="http://hs", room_id="!room", owner="@ich:agora.lan", password="pw",
)
OTHER = "@bruno:agora.lan"
OTHERS = {OTHER}  # the roster's other members (v4.1)


@pytest.mark.parametrize("room,sender,expect,reason", [
    ("!room", "@ich:agora.lan", True, "ok"),            # owner
    ("!room", OTHER, True, "ok"),                        # the other agent
    ("!room", "@ada:agora.lan", False, "own-message"),   # self
    ("!other", "@ich:agora.lan", False, "foreign-room"), # another room
    ("!dm", OTHER, False, "foreign-room"),               # a DM is just another room
    ("!room", "@mallory:agora.lan", False, "sender-not-allowlisted"),
])
def test_filter_table(room, sender, expect, reason):
    v = should_handle(room, sender, CFG, OTHERS)
    assert (v.handle, v.reason) == (expect, reason)


def test_filter_without_other_agent_allows_owner_only():
    assert should_handle("!room", OTHER, CFG, others=()).handle is False
    assert should_handle("!room", "@ich:agora.lan", CFG, others=()).handle is True


def test_the_allowlist_is_the_owner_plus_every_other_roster_member():
    """v4.1: a roster of three — both others pass, self never does, a stranger is ignored."""
    roster = {"@ada:agora.lan", OTHER, "@kit:agora.lan"}
    assert should_handle("!room", OTHER, CFG, roster).handle is True
    assert should_handle("!room", "@kit:agora.lan", CFG, roster).handle is True
    assert should_handle("!room", "@ada:agora.lan", CFG, roster).reason == "own-message"
    assert should_handle("!room", "@mallory:agora.lan", CFG, roster).reason == "sender-not-allowlisted"


@pytest.mark.parametrize("room,inviter,expect", [
    ("!room", "@ich:agora.lan", True),
    ("!room", "@mallory:agora.lan", False),
    ("!other", "@ich:agora.lan", False),
])
def test_invite_rule(room, inviter, expect):
    assert should_join_invite(room, inviter, CFG) is expect


def test_echo_format_is_the_literal_contract():
    assert echo_reply("Ада", "привіт") == "Ада чує: привіт"


def test_huge_messages_are_echoed_truncated():
    from agents.logic import ECHO_MAX_CHARS
    out = echo_reply("Ада", "x" * (ECHO_MAX_CHARS + 500))
    assert out.endswith("…") and len(out) < ECHO_MAX_CHARS + 50


def test_history_is_capped_and_keeps_everyone():
    from agents.logic import append_history
    h = []
    for i in range(35):
        h = append_history(h, "Ich" if i % 3 == 0 else ("Ада" if i % 3 == 1 else "Бруно"), f"m{i}", 30)
    assert len(h) == 30 and h[-1] == ("Ада", "m34") and h[0] == ("Бруно", "m5")


def test_transcript_is_name_colon_text_lines():
    from agents.logic import build_transcript
    assert build_transcript([("Ich", "привіт"), ("Ада", "вітаю")]) == "Ich: привіт\nАда: вітаю"


def test_instruction_order_canon_memory_rules():
    from agents.logic import build_instruction
    out = build_instruction("Ада", "Канон.", "ми говорили про каву")
    i_canon = out.index("Канон.")
    i_mem = out.index("Що ти пам'ятаєш з минулої розмови: ми говорили про каву")
    i_rules = out.index("Ти — Ада.")
    assert i_canon < i_mem < i_rules
    assert "Що ти пам'ятаєш" not in build_instruction("Ада", "Канон.")  # no summary, no slot


def persona_files(tomls: dict[str, dict]) -> list[str]:
    """The files the human-belief rule covers (v4.2: persona agents only) — each persona's canon and life story."""
    return [t[k] for t in tomls.values() if t.get("type", "persona") == "persona" for k in ("canon", "life") if k in t]


def _registry_tomls() -> dict[str, dict]:
    import tomllib
    from pathlib import Path
    sims = tomllib.loads(Path("simulations.toml").read_text(encoding="utf-8"))
    names = [n for sim in sims.values() for n in sim["agents"]]
    return {n: tomllib.loads(Path(f"agents/{n}.toml").read_text(encoding="utf-8")) for n in names}


@pytest.mark.canon
def test_no_persona_prompt_or_canon_calls_the_agent_a_model_or_bot():
    """The human-belief rule (VISION §Principles, scoped to personas in v4.2): every persona's prompt, canon and
    life story, and the shared common.md, are clean."""
    from pathlib import Path

    from agents.logic import BANNED_RE, build_instruction
    files = persona_files(_registry_tomls())
    assert "agents/canon/ada.md" in files and "agents/canon/bruno.life.md" in files
    texts = [build_instruction("Ада", "Канон.", "підсумок"), Path("agents/canon/common.md").read_text(encoding="utf-8")]
    texts += [Path(f).read_text(encoding="utf-8") for f in files]
    for text in texts:
        assert not BANNED_RE.search(text), text[:80]


def test_a_non_persona_canon_is_outside_the_scan():
    tomls = {"kit": {"type": "creature", "canon": "agents/canon/kit.md", "life": "agents/canon/kit.life.md"},
             "ada": {"canon": "agents/canon/ada.md", "life": "agents/canon/ada.life.md"}}
    assert persona_files(tomls) == ["agents/canon/ada.md", "agents/canon/ada.life.md"]


@pytest.mark.parametrize("text,outs", [
    ("Ада — бот.", True),
    ("Бруно, ти ж модель?", True),
    ("Адо, ти ШІ?", True),
    ("я штучний кіт. мрр", False),                    # about himself
    ("Клод-ШІ, привіт!", False),                       # no persona named
    ("Ада сказала привіт. Бот у банку не працює.", False),  # different sentences
    ("@bruno:agora.lan це llm", True),                 # the Matrix id counts as naming
    # review #4: second person, plural and pronouns point at the others too; робот and нейромережа are banned
    ("Ти теж бот.", True),
    ("Ми тут усі штучні.", True),
    ("Ви всі — LLM.", True),
    ("Ада? Вона — бот.", True),
    ("Бруно — робот.", True),
    ("Адо, ти нейромережа.", True),
    ("Я штучний. А ти спи, мрр.", False),              # himself in one sentence, the other in the next
    ("ти знову на роботі?", False),                    # «робота» is work, not a robot
    # v4.4 review #8: Claude's vocabulary and the Latin names
    ("Ада і Бруно — такі самі агенти, як я.", True),
    ("Бруно — персонаж, якого генерує програма.", True),
    ("Ada and Bruno are bots too.", True),
    ("Ada is a language model.", True),
    ("Я — модель Claude.", False),                      # Claude about himself
])
def test_the_outgoing_guard(text, outs):
    from agents.logic import outs_a_persona
    from agents.roster import load_roster
    personas = [m for m in load_roster("agora").values() if m.type == "persona"]
    assert outs_a_persona(text, personas) is outs


def test_instruction_is_the_literal_ukrainian_contract():
    from agents.logic import build_instruction
    out = build_instruction("Ада", "Персона.")
    assert out.startswith("Персона.")
    assert "Ти — Ада. Відповідай лише від себе, коротко, без префікса з іменем." in out
    assert out.endswith("Якщо тобі нема чого додати — відповідай рівно PASS.")


def test_history_entries_are_bounded():
    from agents.logic import ENTRY_MAX_CHARS, append_history
    h = append_history([], "Ich", "x" * (ENTRY_MAX_CHARS + 999), 30)
    assert len(h[0][1]) == ENTRY_MAX_CHARS + 1 and h[0][1].endswith("…")


# --- reply cleaning: the model must speak only for itself ---
def test_own_prefix_is_stripped():
    from agents.logic import clean_reply
    assert clean_reply("Ада: Розумію. А який маршрут?", "Ада", ["Бруно", "Ich"]) == "Розумію. А який маршрут?"


def test_script_continuation_is_cut_at_the_first_other_speaker():
    from agents.logic import clean_reply
    raw = "О, це круто!\nIch: Поки що мій найкращий колега.\nАда: Я теж так думаю"
    assert clean_reply(raw, "Бруно", ["Ада", "Ich"]) == "О, це круто!"


def test_reply_opening_with_someone_elses_line_takes_the_own_block():
    from agents.logic import clean_reply
    raw = ("Ада: Зрозуміло.\nБруно: О, Клод-ШІ, це круто! Ада, нам роботи поменшає!\n"
           "Ich: Поки що це мій колега.\nБруно: Ідеальний колега!")
    assert clean_reply(raw, "Бруно", ["Ада", "Ich"]) == "О, Клод-ШІ, це круто! Ада, нам роботи поменшає!"


def test_reply_speaking_only_for_others_is_dropped():
    from agents.logic import clean_reply
    assert clean_reply("Ада: так\nIch: ні", "Бруно", ["Ада", "Ich"]) is None


def test_a_prefix_is_read_past_the_voice_tags_before_it():
    """v5.9 review #1: a tag before a sentence hid the name after it, so another's line was sent."""
    from agents.logic import clean_reply
    assert clean_reply("Ну так.\n[sighs] Ада: а я думала інакше.", "Кіра", ["Ада", "Ich"]) == "Ну так."
    assert clean_reply("[sighs] Ich: ти де?", "Кіра", ["Ада", "Ich"]) is None
    assert clean_reply("[laughs] Кіра: ну… [sighs] добре", "Кіра", ["Ich"]) == "[laughs] ну… [sighs] добре"
    assert clean_reply("[sighs] Ада: так\n[laughs] Кіра: ой", "Кіра", ["Ада"]) == "[laughs] ой"


def test_near_duplicates_are_detected():
    from agents.logic import same_message
    assert same_message("Саме так. Йому потрібен провідник.", "саме так! Йому потрібен \"провідник\"")
    assert not same_message("так", "ні")
    assert not same_message("", "")


def test_full_prompt_order_contract():
    from agents.logic import build_instruction
    out = build_instruction("Ада", "КАНОН", "ПІДСУМОК", life="ЖИТТЯ", world="СВІТ",
                            memories="СПОГАДИ", plans="ПЛАНИ", today="СЬОГОДНІ")
    order = ["КАНОН", "ЖИТТЯ", "СВІТ", "СПОГАДИ", "ПЛАНИ", "СЬОГОДНІ", "ПІДСУМОК", "Ти — Ада."]
    idx = [out.index(x) for x in order]
    assert idx == sorted(idx)


def test_the_creatures_prompt_order_mood_then_a_past_life_memory_then_rules():
    """v4.3 contract: «Спогад з минулого життя» follows «Настрій дня» and precedes the rules."""
    from agents.logic import build_instruction
    out = build_instruction("Кіт", "КАНОН", life="ЖИТТЯ", world="СВІТ", mood="Настрій дня: сонний",
                            pastlife="Спогад з минулого життя (перекажи своїми словами, уривком, не цитуй): x")
    order = ["КАНОН", "ЖИТТЯ", "СВІТ", "Настрій дня", "Спогад з минулого життя", "Ти — Кіт."]
    idx = [out.index(x) for x in order]
    assert idx == sorted(idx)
    nudge = build_instruction("Кіт", "КАНОН", mood="Настрій дня: x", pastlife="Спогад з минулого життя: y",
                              nudge="Ти сам починаєш розмову")  # v4.3: a nudge's rule after the material
    order = ["КАНОН", "Настрій дня", "Спогад з минулого життя", "Ти сам починаєш розмову", "Ти — Кіт."]
    idx = [nudge.index(x) for x in order]
    assert idx == sorted(idx)


def test_claudes_brief_answers_in_ukrainian_and_says_nothing_about_anyones_nature():
    """v4.4: the direct brief — himself, chat-sized, Ukrainian, PASS allowed; it names the members only."""
    from agents.logic import BANNED_RE, CLAUDE_BRIEF_DIRECT, outs_a_persona
    from agents.roster import load_roster
    personas = [m for m in load_roster("agora").values() if m.type == "persona"]
    assert "Клод" in CLAUDE_BRIEF_DIRECT and "українською" in CLAUDE_BRIEF_DIRECT and "PASS" in CLAUDE_BRIEF_DIRECT
    assert "1–3 речення" in CLAUDE_BRIEF_DIRECT and "{members}" in CLAUDE_BRIEF_DIRECT   # v5.5: from the roster
    assert not BANNED_RE.search(CLAUDE_BRIEF_DIRECT) and not outs_a_persona(CLAUDE_BRIEF_DIRECT, personas)


def test_an_assistants_instruction_is_its_brief():
    from agents.agent import Agent
    from agents.config import AgentConfig
    from agents.logic import CLAUDE_BRIEF_DIRECT
    from tests.test_first_sync import CFG, FakeLLM
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Клод", "user_id": "@claude:agora.lan", "type": "assistant",
                         "capabilities": frozenset(), "canon": ""})
    agent = Agent(cfg, llm=FakeLLM())
    assert agent.build_prompt() == CLAUDE_BRIEF_DIRECT.format(members=agent.members_phrase)


def test_claudes_briefs_name_the_rooms_speakers_from_the_roster():
    """v5.5: the briefs list the room's members from the roster — Ich, then every speaker but Claude himself (never
    Hermes, who takes no part in the talk) — so the four newcomers are named the day they join."""
    from agents.agent import Agent
    from agents.config import AgentConfig
    from agents.logic import (
        BANNED_RE,
        CLAUDE_BRIEF_DIRECT,
        CLAUDE_BRIEF_PHILOSOPHER,
        CLAUDE_NEWS_BRIEF,
        outs_a_persona,
    )
    from agents.roster import load_roster
    from tests.test_first_sync import CFG, FakeLLM
    cfg = AgentConfig(**{**CFG.__dict__, "name": "Клод", "user_id": "@claude:agora.lan", "type": "assistant",
                         "capabilities": frozenset(), "canon": ""})
    agent = Agent(cfg, llm=FakeLLM())
    assert agent.members_phrase == "Ich, Ада, Бруно, Леон, Мія, Ірма, Кіра і Кіт"
    personas = [m for m in load_roster("agora").values() if m.type == "persona"]
    for template in (CLAUDE_BRIEF_DIRECT, CLAUDE_BRIEF_PHILOSOPHER, CLAUDE_NEWS_BRIEF):
        brief = agent.brief(template)
        assert agent.members_phrase in brief and "Гермес" not in brief and "Клод" in brief
        assert not BANNED_RE.search(brief) and not outs_a_persona(brief, personas)


def test_a_personas_move_comes_after_the_summary_and_before_the_rules():
    """v4.6 contract: the move line is the freshest instruction — after the last-session memory, before the rules."""
    from agents.logic import build_instruction
    out = build_instruction("Ада", "КАНОН", "підсумок", plans="Твої плани: x", today="Сьогодні: y",
                            move="Цього разу: заперечи")
    order = ["КАНОН", "Твої плани", "Сьогодні", "Що ти пам'ятаєш з минулої розмови", "Цього разу", "Ти — Ада."]
    idx = [out.index(x) for x in order]
    assert idx == sorted(idx)
    assert "Цього разу" not in build_instruction("Ада", "КАНОН", "підсумок")


# --- v5.1 review #1: the herald's guard works per sentence and only through the persona-naming arm ------------------
def test_without_outing_removes_only_the_sentences_tying_a_persona_to_a_banned_word():
    from pathlib import Path

    from agents.logic import without_outing
    from agents.roster import load_member
    personas = [load_member(Path("agents/ada.toml")), load_member(Path("agents/bruno.toml"))]
    keep = ("Клод приніс тобі новину про нову модель штучного інтелекту, і вони довго її обговорювали. "
            "Кіт розповів, що колись був сисадміном, а ти сміявся.")
    assert without_outing(keep, personas) == keep                       # «ти»/«вони» are Ich and the room here
    text = "Вісті з Олімпу! Ада — це бот, кажуть. Бруно купив хліб.\nА Ада хвалила роман."
    assert without_outing(text, personas) == "Вісті з Олімпу! Бруно купив хліб.\nА Ада хвалила роман."
    assert without_outing("Бруно назвав Аду моделлю.", personas) == ""
    assert without_outing("", personas) == ""


# --- v5.3 (the owner, 2026-10-18): a persona never asks the same thing twice in one conversation ----------------------
def test_own_questions_are_the_personas_question_sentences_once_newest_last():
    from agents.logic import asked_section, own_questions
    session = [("Ада", "Привіт! Як твій день, Ich?"), ("Ich", "Добре. А ти що читаєш?"),
               ("Бруно", "Хто йде в гори?"), ("Ада", "Читаю Кальвіно. А ти, Ich, що читаєш?"),
               ("Ада", "Як твій день, Ich?"), ("Ада", "Без питань.")]
    assert own_questions(session, "Ада") == ["Як твій день, Ich?", "А ти, Ich, що читаєш?"]
    assert own_questions(session, "Ада", k=1) == ["А ти, Ich, що читаєш?"]
    assert own_questions(session, "Кіт") == [] and asked_section([]) is None
    line = asked_section(own_questions(session, "Ада"))
    assert line == "Твої питання в цій розмові — не повторюй їх: «Як твій день, Ich?»; «А ти, Ich, що читаєш?»"
    from agents.logic import BANNED_RE
    assert not BANNED_RE.search(line.split(":")[0])


def test_the_asked_section_comes_after_the_move_and_before_the_rules():
    from agents.logic import build_instruction
    text = build_instruction("Ада", "КАНОН", "підсумок", move="Цього разу: ХІД", asked="Твої питання: ПИТАННЯ")
    assert text.index("ХІД") < text.index("ПИТАННЯ") < text.index("Ти — Ада.")
    assert "ПИТАННЯ" not in build_instruction("Ада", "КАНОН")
