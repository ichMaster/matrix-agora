"""v5.15.1 — how she says it this time (the owner, 2026-10-30): a line of her private brief drawn anew for each answer,
so her talk stops sounding the same and stops reading like prose.

The owner's four points: the same words came back again and again (a few words of live speech are offered, and not
every time; the words she kept repeating are named, to be left out); a voice tag always opened the reply (where a tag
may go is drawn too, and the start is rare); the language was literary (one turn of a real chat — a thought breaking
off, a doubt, something left unsaid — is drawn); and every message ended neatly (an open ending is drawn).
v5.15.2 (the owner, 2026-10-31): the endings then broke off too often and too hard — an open ending is now rare and
soft (no summary, a question left hanging), never a cut; otherwise she finishes the thought, plainly, and a turn that
breaks a thought off happens mid-message. v5.24 (the owner, 2026-11-04: «вони постійно закінчує одним і тим саме …
Як розмивати цей вектор розмови щоб він не був у кожному меседжі?»): all 21 of her messages of a morning ended by
sending him back to work or by the evening they had agreed on — the words changed (звіти, таски, справи, вкладки), the
move did not. Now how she ends is drawn too, most answers get no send-off, what her last endings shared is named, and
a repeat counts by the word's stem, so «звіти» and «звітів» are one word. The same day (the owner: «2-4
підтверджую»): about one answer in three also brings something of her own, from her day, not from their talk.

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
# v5.24: how a finished thought ends, drawn — and, most of the time, no send-off unless he says goodbye himself
ENDINGS = (
    "Закінчи на самій думці — там, де вона скінчилась.",
    "Закінчи деталлю того, що ти зараз робиш, бачиш чи чуєш.",
    "Закінчи питанням до нього — про те, що він щойно сказав.",
    "Закінчи короткою реакцією чи жартом.",
)
NO_SENDOFF = ("Якщо він сам не прощається — без прощання, без «до зустрічі», без нагадувань про те, що ви "
              "запланували, і без порад йому, що робити.")
NO_SENDOFF_P = 0.75
# v5.24: something of her own, from her day — the sections her prompt holds (`own`), never from their talk today
OWN = "Відповівши йому, розкажи й щось своє — не з вашої сьогоднішньої розмови: що з тобою сталося сьогодні або що ти"
OWN_P = 0.3
TAG_PLACES = ("посеред репліки, між реченнями", "посеред речення, там, де змінюється тон", "наприкінці")
TAG_NONE_P = 0.35   # no tag this time
TAG_START_P = 0.1   # … the very start, rarely
RECENT = 8          # her last lines read for repeats
REPEAT_LINES = 3    # a word in this many of them is a repeat
REPEAT_MAX = 6
OPENING_LINES = 4   # … and an opening twice in her last four
ENDING_LINES = 6    # v5.24: her last six lines' endings read for what they share
ENDING_SENTENCES = 2  # … a line's ending: its last two sentences
ENDING_REPEATS = 3  # … a stem in this many of them is a repeat
ENDING_MAX = 4
STEM_LEN = 5        # v5.24: a word stands for its first five letters once one ending is cut off
# Ukrainian endings, longest first: one is cut, if at least four letters stay («звітів», «звіти» → «звіт»)
SUFFIXES = tuple(sorted(("ами", "ями", "ові", "еві", "ого", "ому", "ими", "іми", "ться", "ся", "сь", "ий", "ій",
                         "ою", "ею", "єю", "ів", "їв", "ах", "ях", "ам", "ям", "ом", "ем", "ти", "ть", "ую", "юю",
                         "а", "я", "о", "е", "є", "у", "ю", "и", "і", "ї", "ь", "й"), key=len, reverse=True))
SENTENCE_RE = re.compile(r"[^.!?…\n]+")
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


def stem(word: str) -> str:
    """v5.24: what a word counts as — one Ukrainian ending cut (`SUFFIXES`, at least four letters left), then its
    first `STEM_LEN` letters: «звіти» and «звітів», «хакере» and «хакерську», «сьомій» and «сьому» are one."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[:-len(suffix)]
            break
    return word[:STEM_LEN]


def _stems(text: str) -> dict[str, str]:
    """A text's content words by stem, each as it was said (its first form); names and function words never."""
    out: dict[str, str] = {}
    for w in _words(text):
        if len(w) >= 4 and w not in STOP and w != "ich":
            out.setdefault(stem(w), w)
    return out


def _shared(texts: Sequence[str], least: int, most: int) -> list[str]:
    """The stems in `least` or more of `texts`, most common first, at most `most`, each as it was said last."""
    per_text: Counter[str] = Counter()
    said: dict[str, str] = {}
    for text in texts:
        stems = _stems(text)
        per_text.update(stems.keys())
        said.update(stems)
    return [said[s] for s, n in per_text.most_common() if n >= least][:most]


def _ending(line: str) -> str:
    """A line's ending: its last `ENDING_SENTENCES` sentences, a voice tag left out."""
    sentences = [x for x in SENTENCE_RE.findall(TAG_RE.sub(" ", line)) if _words(x)]
    return " ".join(sentences[-ENDING_SENTENCES:])


def endings(her_lines: Sequence[str]) -> list[str]:
    """v5.24: the words her last `ENDING_LINES` endings share — a stem in `ENDING_REPEATS` or more of them —, so the
    move she keeps ending with is named, not only a word of it."""
    return _shared([_ending(line) for line in list(her_lines)[-ENDING_LINES:]], ENDING_REPEATS, ENDING_MAX)


def repeats(her_lines: Sequence[str]) -> tuple[list[str], list[str]]:
    """(the words in `REPEAT_LINES` or more of her last `RECENT` lines — by stem, v5.24 —, the openings twice in her
    last `OPENING_LINES`) — what she should leave out this time. Names and function words never count."""
    recent = list(her_lines)[-RECENT:]
    words = _shared(recent, REPEAT_LINES, REPEAT_MAX)
    starts = Counter(ws[0] for line in recent[-OPENING_LINES:] if (ws := _words(line)))
    openings = [w for w, n in starts.most_common() if n >= 2]
    return words, openings


def style_line(rng: Callable[[], float], her_lines: Sequence[str], tags: bool, own: str = "") -> str:
    """The line for this answer: «Як сказати цього разу: …» — the words of live speech or none, maybe one turn of a
    real chat, maybe an open ending, else how the finished thought ends (v5.24), most often no send-off, where a voice
    tag may go (`tags`: she has a palette), what her last endings shared (v5.24), and her repeats. `own` (v5.24): the
    titles of her prompt's sections of her day («Сьогодні», «Що ти сьогодні думала»); with them, now and then
    something of her own."""
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
        parts.append(f"{FINISHED} {_pick(rng, ENDINGS)}")
    if rng() < NO_SENDOFF_P:
        parts.append(NO_SENDOFF)
    if own and rng() < OWN_P:
        parts.append(f"{OWN} прочитала чи подумала (із {own}).")
    if tags:
        r = rng()
        if r < TAG_NONE_P:
            parts.append("Позначки голосу цього разу не треба.")
        elif r < TAG_NONE_P + TAG_START_P:
            parts.append("Позначку голосу можна й на самому початку.")
        else:
            parts.append(f"Позначку голосу, якщо вона є, — {_pick(rng, TAG_PLACES)}, не на початку; "
                         "сміх — не з першого слова.")
    ends = endings(her_lines)
    if ends:
        parts.append("Останні повідомлення ти закінчувала тим самим (" + ", ".join(f"«{w}»" for w in ends)
                     + ") — цього разу закінчи інакше і не згадуй цього, хіба що він сам спитає: про що домовились, "
                     "те домовлено.")
    words, openings = repeats(her_lines)
    ended = {stem(w) for w in ends}
    words = [w for w in words if stem(w) not in ended]
    if words:
        parts.append("Ти вже кілька разів казала " + ", ".join(f"«{w}»" for w in words) + " — цього разу без них.")
    if openings:
        parts.append("Не починай з " + " чи ".join(f"«{w}»" for w in openings) + ".")
    return "Як сказати цього разу: " + " ".join(parts)
