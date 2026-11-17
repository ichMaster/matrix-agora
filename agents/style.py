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
a repeat counts by the word's stem, so «звіти» and «звітів» are one word. v5.25 (the owner, the same day: «2-4
підтверджую»): about one answer in three also brings something of her own, from her day, not from their talk.

Pure: the randomness is a callable passed in (`random.random` in the agent), her lines are plain strings.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence

from agents.emotion import TAG_RE

# words of live speech — a pick of one or two is offered, never the whole list, and many answers get none;
# v5.25: no word that opens another topic («до речі», «уяви»); her Donetsk surzhyk here (AGORA-211) was taken back
# by the owner the same day: «вишло занадто вже не реалістично, раніше було ліпше»
FILLERS = ("ну", "типу", "короче", "слухай", "знаєш", "чесно", "в сенсі", "ну тобто", "якось так", "от", "ммм",
           "е-е", "ну таке", "загалом", "блін", "мабуть", "наче", "ніби", "щось типу", "як би це сказати",
           "ну ти зрозумів", "і от", "а взагалі", "коротше", "ой", "хм", "ага", "ну да")
FILLERS_P = 0.6
# v8.3.1 (the owner, 2026-11-17, of Устина: «мову Устини зробити ще більше не формальну, вона зараз літературна»; her
# canon alone changed little — «нема змін особливих»: «речення і описи», «слова»): with her TOML's `fillers_each` every
# answer asks her to weave in at least that many of a few words offered, and to keep her talk spoken, never bookish
SPOKEN = ("Мова в тебе розмовна, не книжна: прості короткі речення, без описів і гарних образів, без «адже», «втім», "
          "«проте», «зрештою».")
FILLERS_EACH_MAX = 5
COUNTS = ("", "одне", "два", "три", "чотири", "п'ять")
# v8.3.3 (the owner, 2026-11-17, of Устина's last two lines: «збільшити кількість не літературних слів», «додай більше
# зумерського сленгу», «всі слова що можна замінити на сленг міняй на сленг», «трохи айтішного сленгу в перемішку з
# зумерським»): with her TOML's `slang` every answer asks every word that has slang said in slang and feelings said
# plainly; her draws leave out the turns that correct herself and the ending on what she sees or does (`SLANG_MANNERS`,
# `SLANG_ENDINGS`) — they gave her «хоча нє» and a paper cup turned in her fingers
SLANG = ("Усе, що можна сказати сленгом, кажи сленгом — зумерським упереміш з айтішним: не «класно», а «топ» чи «імба»; "
         "не «смішно», а «рофл» чи «ору»; не «справді», а «рілі»; не «легко», а «ізі»; не «проблема», а «трабл» чи "
         "«баг»; не «незручно», а «крінж»; не «відпочити», а «почілити»; не «розумію», а «шарю»; не «швидко», а "
         "«асап»; не «виправити», а «пофіксити». Почуття кажи прямо, без образів: не «щоки горять», «розплавилась» чи "
         "«серце завмерло», а «мені кайф», «я в шоці», «скучила». Не описуй, що навколо тебе і що ти робиш руками, і "
         "без книжного: «маю надію», «відчуваю, що», «страшенно».")
# v5.25 (the owner, 2026-11-05: «вона далі стрибає по темам»): a turn never takes her to another topic — three of
# them did («перейди до іншої», «перескоч на інше», «далі вже про інше»)
MANNERS = (
    "посеред повідомлення обірви думку й скажи її інакше",
    "засумнівайся вголос у тому, що сама щойно сказала",
    "почни з дрібниці, а тоді дійди до головного — у тій самій темі",
    "посередині щось недоскажи — пауза «…», і далі про те саме, але інакше",
    "переправ себе посеред речення («тобто… ні, не так»)",
    "скажи коротко і просто, без жодного образу",
    "плутано поясни те, що сама ще не до кінця зрозуміла",
)
MANNER_P = 0.7
# v8.3.3: with `slang`, none of the turns that correct herself or ramble — one plain turn of these instead
SLANG_MANNERS = (
    "скажи коротко і просто, без жодного образу",
    "одна думка — одне коротке речення",
    "скажи так, як сказала б це вголос, а не як написала б",
)
OPEN_ENDINGS = (
    "лиши кінець відкритим — без висновку й без підсумку",
    "закінчи питанням, яке лишиться висіти",
    "закінчи ніби між іншим, коротко, без крапки над «і»",
)
OPEN_ENDING_P = 0.2
FINISHED = "Думку договори до кінця — просто, без підсумку й без обриву."
# v5.24: how a finished thought ends, drawn — and, most of the time, no send-off unless he says goodbye himself
DETAIL_ENDING = "Закінчи деталлю того, що ти зараз робиш, бачиш чи чуєш."
ENDINGS = (
    "Закінчи на самій думці — там, де вона скінчилась.",
    DETAIL_ENDING,
    "Закінчи питанням до нього — про те, що він щойно сказав.",
    "Закінчи короткою реакцією чи жартом.",
)
SLANG_ENDINGS = tuple(e for e in ENDINGS if e != DETAIL_ENDING)  # v8.3.3: never on what she sees or does
NO_SENDOFF = ("Якщо він сам не прощається — без прощання, без «до зустрічі», без нагадувань про те, що ви "
              "запланували, і без порад йому, що робити.")
NO_SENDOFF_P = 0.75
# v5.25: something of her own, from her day — the sections her prompt holds (`own`), never from their talk today;
# the owner, 2026-11-05: never tacked on after her answer — a whole message, once his words need nothing more, and
# never while they flirt or are close
OWN = ("Якщо ви зараз не фліртуєте й не в ніжності, він ні про що тебе не питає і на його слова тобі вже нема чого "
       "додати, розкажи щось своє — цілим повідомленням, не з вашої сьогоднішньої розмови: що з тобою сталося "
       "сьогодні або що ти")
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
FILLER_LINES = 4    # v8.3.3 (v8.3.1 review #2): her last four lines read for her own words of live speech …
FILLER_REPEATS = 2  # … one in two of them is a repeat, however short («топ», «лол»)
FILLER_MAX = 4
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


def _says(line: str, word: str) -> bool:
    """Whether a line says a word or phrase whole — «топ» never in «топити», «та ну» never in «та нуль»."""
    text = TAG_RE.sub(" ", line).lower().replace("’", "'")
    return re.search(rf"(?<![\w'-]){re.escape(word.lower())}(?![\w'-])", text) is not None


def filler_repeats(her_lines: Sequence[str], fillers: Sequence[str]) -> list[str]:
    """v8.3.3 (v8.3.1 review #2): her own words of live speech in `FILLER_REPEATS` or more of her last `FILLER_LINES`
    lines, matched whole — so a short one («топ», «лол») is named too, never one of two letters («шо», «ну»)."""
    recent = list(her_lines)[-FILLER_LINES:]
    return [f for f in fillers if len(f) > 2 and sum(_says(x, f) for x in recent) >= FILLER_REPEATS][:FILLER_MAX]


def woven(rng: Callable[[], float], fillers: Sequence[str], each: int, her_lines: Sequence[str]) -> str:
    """v8.3.1 — the words of live speech she weaves into this answer: `each` + 1 offered (fewer when her list is
    short), at least `each` of them asked for, never one she is told she keeps repeating (v8.3.3: her own short ones
    too, `filler_repeats`); then `SPOKEN`."""
    left_out = {stem(w) for w in repeats(her_lines)[0]}
    said = set(filler_repeats(her_lines, fillers))
    pool = [f for f in fillers if stem(f) not in left_out and f not in said] or list(fillers)
    picks: list[str] = []
    while pool and len(picks) < each + 1:
        pick = _pick(rng, pool)
        picks.append(pick)
        pool = [f for f in pool if f != pick]
    need = COUNTS[min(each, len(picks))]
    return f"вплети щонайменше {need} з цих слів: " + ", ".join(f"«{p}»" for p in picks) + f". {SPOKEN}"


def style_line(rng: Callable[[], float], her_lines: Sequence[str], tags: bool, own: str = "",
               fillers: Sequence[str] = FILLERS, each: int = 0, slang: bool = False) -> str:
    """The line for this answer: «Як сказати цього разу: …» — the words of live speech or none, maybe one turn of a
    real chat, maybe an open ending, else how the finished thought ends (v5.24), most often no send-off, where a voice
    tag may go (`tags`: she has a palette), what her last endings shared (v5.24), and her repeats. `own` (v5.25): the
    titles of her prompt's sections of her day («Сьогодні», «Що ти сьогодні думала»); with them, now and then
    something of her own. `fillers` (v6.5.1): her own words of live speech, from her TOML; empty, `FILLERS`. `each`
    (v8.3.1, her TOML's `fillers_each`): above 0, every answer weaves in at least that many (`woven`), and her own
    words she said twice lately are named (v8.3.3); 0, as before. `slang` (v8.3.3, her TOML): `SLANG` in every answer,
    and her turn and ending drawn from `SLANG_MANNERS` and `SLANG_ENDINGS` — as many draws, so off it is as before."""
    fillers = tuple(fillers) or FILLERS
    parts = []
    if each > 0:
        parts.append(woven(rng, fillers, each, her_lines))
    elif rng() < FILLERS_P:
        first = _pick(rng, fillers)
        rest = [f for f in fillers if f != first]
        picks = [first, _pick(rng, rest)] if rest and rng() < 0.4 else [first]
        parts.append("можеш (але не мусиш) вплести " + " чи ".join(f"«{p}»" for p in picks) + ".")
    else:
        parts.append("без слів-паразитів.")
    if slang:
        parts.append(SLANG)
    if rng() < MANNER_P:
        parts.append(_pick(rng, SLANG_MANNERS if slang else MANNERS).capitalize() + ".")
    if rng() < OPEN_ENDING_P:
        parts.append(_pick(rng, OPEN_ENDINGS).capitalize() + ".")
    else:
        parts.append(f"{FINISHED} {_pick(rng, SLANG_ENDINGS if slang else ENDINGS)}")
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
    if each > 0:  # v8.3.3: her own short words too, once said in two of her last four lines
        named = {stem(w) for w in words} | ended
        words += [f for f in filler_repeats(her_lines, fillers) if stem(f) not in named]
    if words:
        parts.append("Ти вже кілька разів казала " + ", ".join(f"«{w}»" for w in words) + " — цього разу без них.")
    if openings:
        parts.append("Не починай з " + " чи ".join(f"«{w}»" for w in openings) + ".")
    return "Як сказати цього разу: " + " ".join(parts)
