"""v5.15.1 — how she says it this time (the owner, 2026-10-30): a line of her private brief drawn anew for each answer,
so her talk stops sounding the same and stops reading like prose.

The owner's four points: the same words came back again and again (a few words of live speech are offered, and not
every time; the words she kept repeating are named, to be left out); a voice tag always opened the reply (where a tag
may go is drawn too, and the start is rare); the language was literary (one turn of a real chat — a thought breaking
off, a doubt, something left unsaid — is drawn); and every message ended neatly (an open ending is drawn).
v5.15.2 (the owner, 2026-10-31): the endings then broke off too often and too hard — an open ending is now rare and
soft (no summary, a question left hanging), never a cut; otherwise she finishes the thought, plainly, and a turn that
breaks a thought off happens mid-message.

Pure: the randomness is a callable passed in (`random.random` in the agent), her lines are plain strings.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence

from agents.emotion import TAG_RE

# words of live speech — a pick of one or two is offered, never the whole list, and many answers get none
FILLERS = ("ну", "типу", "короче", "слухай", "знаєш", "чесно", "в сенсі", "ну тобто", "якось так", "от", "ммм",
           "е-е", "ну таке", "загалом", "блін", "мабуть", "наче", "ніби", "щось типу", "як би це сказати",
           "ну ти зрозумів", "і от", "а взагалі", "коротше", "до речі", "уяви", "ой", "хм", "ага", "ну да")
FILLERS_P = 0.6
MANNERS = (
    "посеред повідомлення обірви одну думку й перейди до іншої",
    "засумнівайся вголос у тому, що сама щойно сказала",
    "почни з одного, перескоч на інше, а тоді ледь повернись",
    "посередині щось недоскажи — пауза «…», і далі вже про інше",
    "переправ себе посеред речення («тобто… ні, не так»)",
    "скажи коротко і просто, без жодного образу",
    "плутано поясни те, що сама ще не до кінця зрозуміла",
)
MANNER_P = 0.7
OPEN_ENDINGS = (
    "лиши кінець відкритим — без висновку й без підсумку",
    "закінчи питанням, яке лишиться висіти",
    "закінчи ніби між іншим, коротко, без крапки над «і»",
)
OPEN_ENDING_P = 0.2
FINISHED = "Думку договори до кінця — просто, без підсумку й без обриву."
TAG_PLACES = ("посеред репліки, між реченнями", "посеред речення, там, де змінюється тон", "наприкінці")
TAG_NONE_P = 0.35   # no tag this time
TAG_START_P = 0.1   # … the very start, rarely
RECENT = 8          # her last lines read for repeats
REPEAT_LINES = 3    # a word in this many of them is a repeat
REPEAT_MAX = 6
OPENING_LINES = 4   # … and an opening twice in her last four
WORD_RE = re.compile(r"[a-zа-яіїєґ'’]+(?:-[a-zа-яіїєґ'’]+)*", re.IGNORECASE)
# function words of four letters and more: never worth naming as a repeat
STOP = frozenset((
    "коли", "тому", "якщо", "тільки", "лише", "щоби", "може", "можна", "треба", "також", "якби", "поки", "хоча",
    "після", "перед", "через", "навіть", "зараз", "тепер", "його", "мене", "тебе", "мені", "тобі", "себе", "собі",
    "вона", "воно", "вони", "ними", "нами", "вами", "наша", "наше", "наші", "твій", "твоя", "твоє", "твої", "мій",
    "моя", "моє", "мої", "свій", "своя", "своє", "свої", "було", "буде", "були", "була", "бути", "цей", "цього",
    "цієї", "того", "такий", "така", "таке", "такі", "який", "яка", "яке", "які", "щось", "десь", "нема", "немає",
    "цьому", "цим", "тим", "тієї", "тими", "нього", "неї", "них", "всіх", "весь", "вся", "усе", "усі", "коли-небудь",
))


def _pick(rng: Callable[[], float], items: Sequence[str]) -> str:
    return items[min(int(rng() * len(items)), len(items) - 1)]


def _words(line: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in WORD_RE.findall(TAG_RE.sub(" ", line))]


def repeats(her_lines: Sequence[str]) -> tuple[list[str], list[str]]:
    """(the words in `REPEAT_LINES` or more of her last `RECENT` lines, the openings twice in her last
    `OPENING_LINES`) — what she should leave out this time. Names and function words never count."""
    recent = list(her_lines)[-RECENT:]
    per_line = Counter(w for line in recent for w in {w for w in _words(line) if len(w) >= 4 and w not in STOP
                                                       and w != "ich"})
    words = [w for w, n in per_line.most_common() if n >= REPEAT_LINES][:REPEAT_MAX]
    starts = Counter(ws[0] for line in recent[-OPENING_LINES:] if (ws := _words(line)))
    openings = [w for w, n in starts.most_common() if n >= 2]
    return words, openings


def style_line(rng: Callable[[], float], her_lines: Sequence[str], tags: bool) -> str:
    """The line for this answer: «Як сказати цього разу: …» — the words of live speech or none, maybe one turn of a
    real chat, maybe an open ending, where a voice tag may go (`tags`: she has a palette), and her repeats."""
    parts = []
    if rng() < FILLERS_P:
        first = _pick(rng, FILLERS)
        rest = [f for f in FILLERS if f != first]
        picks = [first, _pick(rng, rest)] if rng() < 0.4 else [first]
        parts.append("можеш (але не мусиш) вплести " + " чи ".join(f"«{p}»" for p in picks) + ".")
    else:
        parts.append("без слів-паразитів.")
    if rng() < MANNER_P:
        parts.append(_pick(rng, MANNERS).capitalize() + ".")
    if rng() < OPEN_ENDING_P:
        parts.append(_pick(rng, OPEN_ENDINGS).capitalize() + ".")
    else:
        parts.append(FINISHED)
    if tags:
        r = rng()
        if r < TAG_NONE_P:
            parts.append("Позначки голосу цього разу не треба.")
        elif r < TAG_NONE_P + TAG_START_P:
            parts.append("Позначку голосу можна й на самому початку.")
        else:
            parts.append(f"Позначку голосу, якщо вона є, — {_pick(rng, TAG_PLACES)}, не на початку; "
                         "сміх — не з першого слова.")
    words, openings = repeats(her_lines)
    if words:
        parts.append("Ти вже кілька разів казала " + ", ".join(f"«{w}»" for w in words) + " — цього разу без них.")
    if openings:
        parts.append("Не починай з " + " чи ".join(f"«{w}»" for w in openings) + ".")
    return "Як сказати цього разу: " + " ".join(parts)
