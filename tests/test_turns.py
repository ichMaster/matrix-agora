import random
import subprocess
import sys
from collections import Counter

import pytest

from agents.config import AgentConfig
from agents.roster import Member, load_roster
from agents.turns import (
    addresses_everyone,
    decide_reply,
    fallback_due,
    fallback_replier,
    is_pass,
    mentions,
    next_speaker,
    owner_repliers,
    pending_answers,
    rank,
    still_current,
    strip_pass,
    wave_count,
    wave_frees_at,
)
from tests.test_logic import CFG

ROSTER = load_roster("agora")  # the real registry + TOMLs: forms come from agents/<name>.toml (v4.1)
ME, BRUNO = ROSTER["ada"], ROSTER["bruno"]
OTHERS = {BRUNO.user_id: BRUNO}

KW = {"owner_repliers_k": 2, "max_bot_turns": 3, "bot_reply_p": 0.5, "reply_delay_s": 4.0}


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
    assert mentions(text, ME.name_forms, "@ada:agora.lan") is expect


# --- the roster of four for N-agent tests (Ada and Bruno are real; two more are fakes) ----------------------------

OWNER = CFG.owner
C = Member("cee", "@cee:agora.lan", "Сі", ("сі",))
D = Member("dee", "@dee:agora.lan", "Ді", ("ді",))
FOUR = {"ada": ME, "bruno": BRUNO, "cee": C, "dee": D}
W = 600_000


def cfg_for(m: Member) -> AgentConfig:
    return AgentConfig(name=m.name, user_id=m.user_id, canon="", homeserver="", room_id="!room", owner=OWNER,
                       password="")


def decide(sender, text, me, roster=None, *, wave=1, eid="$e", r=0.0, **kw):
    roster = roster if roster is not None else {"ada": ME, "bruno": BRUNO}
    return decide_reply(sender, text, eid, wave, cfg_for(me), me, roster, rng=rng(r), **{**KW, **kw})


# --- rank: weighted rendezvous hashing ------------------------------------------------------------------------
def test_rank_is_deterministic_and_independent_of_roster_order():
    members = list(FOUR.values())
    assert rank("$abc", members) == rank("$abc", list(reversed(members)))
    assert sorted(rank("$abc", members)) == sorted(FOUR)
    assert any(rank(f"$e{i}", members) != rank("$abc", members) for i in range(20))  # events reshuffle


def test_rank_is_the_same_in_another_process_with_another_hash_seed():
    code = ("from agents.roster import Member; from agents.turns import rank; "
            "m=[Member(n, '@'+n+':a', n, (n,)) for n in ('ada','bruno','cee','dee')]; "
            "print(' '.join(rank('$event-42', m)))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={"PYTHONHASHSEED": "12345", "PATH": ""}, cwd=".").stdout.split()
    members = [Member(n, f"@{n}:a", n, (n,)) for n in ("ada", "bruno", "cee", "dee")]
    assert out == rank("$event-42", members)


def test_rank_first_places_follow_the_weights():
    heavy = Member("cee", "@cee:a", "Сі", ("сі",), weight=3.0)
    firsts = Counter(rank(f"$e{i}", [ME, BRUNO, heavy])[0] for i in range(6000))
    assert 0.55 < firsts["cee"] / 6000 < 0.65            # 3 / (1 + 1 + 3) = 0.6
    assert abs(firsts["ada"] - firsts["bruno"]) < 400


# --- R1: the owner's message ------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expect", [
    ("всі сюди", True), ("Всім привіт!", True), ("ви всі мовчите", True), ("кожен скаже", True),
    ("усі тут?", True), ("всіх обійняв", False), ("кожний день", False), ("привіт", False),
])
def test_group_address(text, expect):
    assert addresses_everyone(text) is expect


def test_r1_named_group_and_unnamed():
    assert owner_repliers("$e", "Адо, привіт", FOUR, 2) == ["ada"]
    assert sorted(owner_repliers("$e", "Адо і Сі, привіт", FOUR, 2)) == ["ada", "cee"]
    assert sorted(owner_repliers("$e", "всім привіт", FOUR, 2)) == sorted(FOUR)
    chosen = owner_repliers("$e", "як справи?", FOUR, 2)
    assert len(chosen) == 2 and chosen == rank("$e", FOUR.values())[:2]


def test_r1_every_agent_computes_the_same_repliers():
    for i in range(50):
        eid = f"$owner{i}"
        yes = [m.localpart for m in FOUR.values() if decide(OWNER, "як справи?", m, FOUR, eid=eid, wave=0).reply]
        assert sorted(yes) == sorted(owner_repliers(eid, "як справи?", FOUR, 2))


def test_owner_mentioning_me_replies_now_and_the_other_stays_silent():
    d = decide(OWNER, "Адо, як ти?", ME, r=0.9)
    assert d.reply and d.delay_s == 0.0
    d = decide(OWNER, "Бруно, як ти?", ME)
    assert not d.reply and d.reason == "owner-chose-others"


def test_owner_unnamed_with_two_agents_both_reply_with_delay_in_bounds():
    for v in (0.0, 0.5, 0.999):
        d = decide(OWNER, "як справи?", ME, r=v, wave=0)
        assert d.reply and 1.0 <= d.delay_s <= 4.0


def test_mention_only_members_answer_only_when_named_or_all_are_addressed():
    quiet = Member("dee", "@dee:a", "Ді", ("ді",), mode="mention-only")
    roster = {"ada": ME, "bruno": BRUNO, "dee": quiet}
    assert all("dee" not in owner_repliers(f"$e{i}", "як справи?", roster, 3) for i in range(30))
    assert "dee" in owner_repliers("$e", "Ді, а ти?", roster, 2)
    assert "dee" in owner_repliers("$e", "всім привіт", roster, 2)


# --- R2: an agent's message ---------------------------------------------------------------------------------------
def test_r2_one_candidate_never_the_sender_names_restrict():
    for i in range(50):
        nxt = next_speaker(f"$m{i}", C.user_id, "думка", FOUR)
        assert nxt in ("ada", "bruno", "dee")
    assert next_speaker("$m", C.user_id, "Ді, а ти?", FOUR) == "dee"
    assert next_speaker("$m", C.user_id, "Сі сам із собою", FOUR) != "cee"  # naming the sender doesn't count


def test_r2_only_the_next_speaker_replies():
    eid = "$m7"
    nxt = next_speaker(eid, C.user_id, "думка", FOUR)
    for m in FOUR.values():
        if m is C:
            continue
        d = decide(C.user_id, "думка", m, FOUR, eid=eid, r=0.0)
        assert d.reply is (m.localpart == nxt)


def test_r2_wave_limit_and_probability_also_when_named():
    assert decide(BRUNO.user_id, "думка", ME, wave=3).reason == "wave-limit"
    assert not decide(BRUNO.user_id, "думка", ME, r=0.6).reply
    assert decide(BRUNO.user_id, "думка", ME, r=0.4).reply
    # naming decides who, not whether: the coin still applies
    assert not decide(BRUNO.user_id, "Адо, а ти?", ME, r=0.99).reply
    assert decide(BRUNO.user_id, "Адо, а ти?", ME, wave=3).reason == "wave-limit"


def test_unknown_sender_is_silent():
    assert not decide("@mallory:agora.lan", "hi", ME).reply


# --- the wave: counts the answered message, a rate over BOT_WINDOW_S ------------------------------------------------
def test_wave_counts_the_answered_message_and_resets_on_owner():
    h = [("Ich", 0, "$a"), ("Ада", 1, "$b"), ("Бруно", 2, "$c")]
    assert wave_count(h, "Ich") == 2
    assert wave_count([*h, ("Ich", 3, "$d")], "Ich") == 0
    assert wave_count([], "Ich") == 0


def test_window_drops_old_agent_messages_from_the_wave():
    tl = [("Ich", 0, "$o"), ("Ада", 1_000, "$1"), ("Бруно", 2_000, "$2"), ("Ада", 700_000, "$3")]
    assert wave_count(tl, "Ich") == 3
    assert wave_count(tl, "Ich", now_ms=701_000, window_ms=W) == 1


def test_migration_new_limit_is_old_limit_plus_one():
    """v1.2's bot_streak excluded the answered message: `streak < old` ⇔ `wave_count < old + 1`."""
    rnd = random.Random(7)
    for _ in range(500):
        tl = [(rnd.choice(["Ich", "Ада", "Бруно"]), i * 1_000, f"$e{i}") for i in range(rnd.randint(1, 12))]
        tl.append(("Бруно", len(tl) * 1_000, "$m"))  # the answered agent message M
        old_streak = wave_count(tl[:-1], "Ich")
        for old in (1, 2, 3, 4):
            assert (old_streak < old) is (wave_count(tl, "Ich") < old + 1)


def test_wave_frees_at_the_moment_the_window_allows_another_turn():
    tl = [("Ich", 0, "$o"), ("Бруно", 10_000, "$1"), ("Ада", 20_000, "$2")]
    assert wave_frees_at(tl, "Ich", 30_000, W, 2) == 10_000 + W + 1
    assert wave_frees_at(tl, "Ich", 30_000, W, 3) is None
    assert wave_frees_at([*tl, ("Ich", 40_000, "$3")], "Ich", 50_000, W, 2) is None


# --- R3 and the fallback ------------------------------------------------------------------------------------------
def test_r3_still_current_only_while_the_trigger_is_latest_and_below_the_limit():
    tl = [("Ich", 0, "$o"), ("Бруно", 1_000, "$m")]
    assert still_current(tl, "$m", "Ich", 2_000, W, 3)
    assert not still_current([*tl, ("Сі", 1_500, "$n")], "$m", "Ich", 2_000, W, 3)  # moved on
    full = [("Ich", 0, "$o"), ("Сі", 1, "$1"), ("Ді", 2, "$2"), ("Бруно", 3, "$m")]
    assert not still_current(full, "$m", "Ich", 4, W, 3)  # the wave is full


def test_fallback_only_when_nobody_answered_and_only_the_top_unchosen():
    tl = [("Ich", 0, "$o")]
    assert fallback_due(tl, "$o")
    assert not fallback_due([*tl, ("Ада", 1, "$a")], "$o")
    assert not fallback_due([*tl, ("Ich", 1, "$o2")], "$o")
    chosen = owner_repliers("$o", "як справи?", FOUR, 2)
    fb = fallback_replier("$o", "як справи?", FOUR, 2)
    assert fb not in chosen and fb == rank("$o", [m for m in FOUR.values() if m.localpart not in chosen])[0]
    assert fallback_replier("$o", "Адо, як ти?", FOUR, 2) is None   # named: no fallback
    assert fallback_replier("$o", "всім привіт", FOUR, 2) is None    # everyone already answers
    assert fallback_replier("$o", "як справи?", {"ada": ME, "bruno": BRUNO}, 2) is None  # nobody left


def test_answers_still_on_their_way_are_reserved_in_the_wave():
    tl = [("Ich", 0, "$o"), ("Бруно", 1_000, "$b")]
    assert pending_answers(tl, "$o", {"Ада", "Бруно", "Сі"}, "Ich") == 2
    assert pending_answers([*tl, ("Ада", 2_000, "$a")], "$o", {"Ада", "Бруно"}, "Ich") == 0
    assert pending_answers(tl, "$o", {"Ада"}, "Ich", now_ms=W + 1_000, window_ms=W) == 0  # lapses with the window
    assert pending_answers(tl, None, {"Ада"}, "Ich") == 0


# --- the multi-agent simulation: no wave beyond the limit, one candidate per message ---------------------------------
def simulate(roster, owner_text, seed, *, k=2, max_turns=3, p=0.5):
    rnd = random.Random(seed)
    timeline = [("Ich", 0, "$owner")]
    kw = {"owner_repliers_k": k, "max_bot_turns": max_turns, "bot_reply_p": p, "reply_delay_s": 4.0}
    pending = []  # (fire_ms, localpart, trigger)
    for m in roster.values():
        d = decide_reply(OWNER, owner_text, "$owner", 0, cfg_for(m), m, roster, rng=rnd.random, **kw)
        if d.reply:
            pending.append((int(d.delay_s * 1000) + 1, m.localpart, None))
    n_owner, sent, followers = len(pending), [], []
    chosen = {roster[n].name for n in owner_repliers("$owner", owner_text, roster, k)}

    def reserved(at):
        return pending_answers(timeline, "$owner", chosen, "Ich", at, W)
    while pending:
        pending.sort()
        ts, who, trigger = pending.pop(0)
        if trigger and not still_current(timeline, trigger, "Ich", ts, W, max_turns, reserved(ts)):
            continue
        eid = f"${who}-{ts}"
        timeline.append((roster[who].name, ts, eid))
        sent.append(who)
        chosen_here = 0
        for m in roster.values():
            if m.localpart == who or any(x[1] == m.localpart for x in pending):
                continue
            d = decide_reply(roster[who].user_id, "думка", eid, wave_count(timeline, "Ich", ts, W) + reserved(ts),
                             cfg_for(m), m, roster, rng=rnd.random, **kw)
            if d.reply:
                chosen_here += 1
                pending.append((ts + int(d.delay_s * 1000) + 1, m.localpart, eid))
        followers.append(chosen_here)
    return n_owner, sent, followers


@pytest.mark.parametrize("text", ["як справи?", "всім привіт", "Адо, як ти?"])
def test_simulated_waves_never_exceed_the_limit(text):
    for seed in range(300):
        n_owner, sent, followers = simulate(FOUR, text, seed)
        assert len(sent) <= max(3, n_owner), (seed, sent)
        assert all(f <= 1 for f in followers)  # one candidate per agent message
        assert n_owner == len(owner_repliers("$owner", text, FOUR, 2))


# --- PASS ---
@pytest.mark.parametrize("text,expect", [
    ("PASS", True), ("  PASS  ", True), ("PASS.", True), ("\nPASS!\n", True),
    ("PASS, але додам", False), ("я пас", False), ("pass", False),
])
def test_pass_detection(text, expect):
    assert is_pass(text) is expect


# the 2026-10-04 chat: text + PASS reached the room four times
@pytest.mark.parametrize("reply,sent", [
    ("PASS", None), ("  PASS. ", None), ("\nPASS!\n", None), ("…\nPASS", None),
    ("Гаразд, я пас. Це якась безглузда гра.\n\nPASS", "Гаразд, я пас. Це якась безглузда гра."),
    ("Ну гаразд, раз ти так, то я теж.\nPASS", "Ну гаразд, раз ти так, то я теж."),
    ("Типу, ти хочеш, щоб ми тебе розгадали? PASS", "Типу, ти хочеш, щоб ми тебе розгадали?"),
    ("Перший рядок.\nPASS\nДругий рядок.", "Перший рядок.\nДругий рядок."),
    ("PASS, але додам", "PASS, але додам"), ("я пас", "я пас"), ("pass", "pass"),
    ("Слово PASSWORD лишається", "Слово PASSWORD лишається"),
])
def test_strip_pass_never_lets_the_sentinel_reach_the_room(reply, sent):
    assert strip_pass(reply) == sent


