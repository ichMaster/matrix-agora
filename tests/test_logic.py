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
