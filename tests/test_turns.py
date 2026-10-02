import pytest

from agents.turns import bot_streak, decide_reply, is_pass, mentions
from tests.test_logic import CFG, OTHER

KW = {"max_bot_turns": 2, "bot_reply_p": 0.5, "reply_delay_s": 4.0}


def rng(v):
    return lambda: v


# --- mentions: Ukrainian case forms + Matrix ids ---
@pytest.mark.parametrize("text,expect", [
    ("Адо, що думаєш?", True),        # vocative — the DoD case
    ("я згоден з Адою", True),        # instrumental
    ("спитай у Ади", True),           # genitive
    ("@ada:agora.lan привіт", True),  # Matrix id
    ("Бруно, а ти?", False),          # the other agent
    ("парада почалась", False),       # substring must not match
    ("ада!", True),                   # case-insensitive, punctuation boundary
])
def test_mentions_ada(text, expect):
    assert mentions(text, "Ада", "@ada:agora.lan") is expect


# --- who replies ---
def test_owner_mentioning_me_replies_now():
    d = decide_reply(CFG.owner, "Адо, як ти?", 0, CFG, OTHER, "Бруно", rng=rng(0.9), **KW)
    assert d.reply and d.delay_s == 0.0


def test_owner_mentioning_the_other_means_silence():
    d = decide_reply(CFG.owner, "Бруно, як ти?", 0, CFG, OTHER, "Бруно", rng=rng(0.0), **KW)
    assert not d.reply and d.reason == "owner-mentioned-other"


def test_owner_no_mention_replies_with_delay_in_bounds():
    for v in (0.0, 0.5, 0.999):
        d = decide_reply(CFG.owner, "всім привіт", 0, CFG, OTHER, "Бруно", rng=rng(v), **KW)
        assert d.reply and 1.0 <= d.delay_s <= 4.0


def test_agent_reply_gated_by_streak():
    d = decide_reply(OTHER, "думка", 2, CFG, OTHER, "Бруно", rng=rng(0.0), **KW)
    assert not d.reply and d.reason == "streak-limit"


def test_agent_reply_gated_by_probability():
    assert not decide_reply(OTHER, "думка", 0, CFG, OTHER, "Бруно", rng=rng(0.6), **KW).reply
    assert decide_reply(OTHER, "думка", 0, CFG, OTHER, "Бруно", rng=rng(0.4), **KW).reply


def test_agent_addressing_me_by_name_skips_the_coin_flip():
    # rng 0.99 would fail the BOT_REPLY_P=0.5 gate — the direct address wins
    d = decide_reply(OTHER, "Адо, а ти як думаєш?", 0, CFG, OTHER, "Бруно", rng=rng(0.99), **KW)
    assert d.reply and d.reason == "agent-mentioned-me"


def test_agent_addressing_me_is_still_bounded_by_the_streak():
    d = decide_reply(OTHER, "Адо, а ти?", 2, CFG, OTHER, "Бруно", rng=rng(0.0), **KW)
    assert not d.reply and d.reason == "streak-limit"


def test_unknown_sender_is_silent():
    assert not decide_reply("@mallory:agora.lan", "hi", 0, CFG, OTHER, "Бруно", rng=rng(0.0), **KW).reply


# --- bot_streak from the shared timeline ---
def test_streak_counts_and_resets_on_owner():
    h = [("Ich", "a"), ("Ада", "b"), ("Бруно", "c")]
    assert bot_streak(h, "Ich") == 2
    assert bot_streak([*h, ("Ich", "d")], "Ich") == 0
    assert bot_streak([], "Ich") == 0
    assert bot_streak([("Ада", "x")] * 5, "Ich") == 5


# --- PASS ---
@pytest.mark.parametrize("text,expect", [
    ("PASS", True), ("  PASS  ", True), ("PASS.", True), ("\nPASS!\n", True),
    ("PASS, але додам", False), ("я пас", False), ("pass", False),
])
def test_pass_detection(text, expect):
    assert is_pass(text) is expect


# --- the streak is a rate over BOT_WINDOW_S, not a lock until the owner speaks ---
def test_window_drops_old_agent_messages_from_the_streak():
    tl = [("Ich", 0), ("Ада", 1_000), ("Бруно", 2_000), ("Ада", 700_000)]
    assert bot_streak(tl, "Ich") == 3                                   # no window: lock semantics
    assert bot_streak(tl, "Ich", now_ms=701_000, window_ms=600_000) == 1  # only the recent one counts


def test_streak_frees_at_the_moment_the_window_allows_another_turn():
    from agents.turns import streak_frees_at
    tl = [("Ich", 0), ("Бруно", 10_000), ("Ада", 20_000)]
    # max 2 turns, both inside the window → frees when the older of the two leaves it
    assert streak_frees_at(tl, "Ich", 30_000, 600_000, 2) == 10_000 + 600_000 + 1
    # under the limit → not blocked
    assert streak_frees_at(tl, "Ich", 30_000, 600_000, 3) is None
    # after the owner speaks, nothing is blocked
    assert streak_frees_at([*tl, ("Ich", 40_000)], "Ich", 50_000, 600_000, 2) is None
