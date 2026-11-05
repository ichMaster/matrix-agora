"""v5.25 — her topics (ROADMAP §v5.25, ARCHITECTURE §Prompt assembly).

The owner, 2026-11-04: «давай ліпше вона буде читати мої меседжі і свої меседжі, бачити які там теми і сама вибирати
на яку говорити»; «зроби 2 і додай меседж що вона має вибрати сама тему для продовження». After each of her private
answers one Flash call lists what their last `TOPICS_LINES` messages are about and how many of hers and of his touch
each topic; her next prompt holds the list and the line that she picks herself which to go on with — never a ban.

Pure: plain data in, text out; the agent reads the archive and calls Gemini.
"""

from __future__ import annotations

import json
import re

from agents.logic import BANNED_RE

TOPICS_MAX = 6
TOPIC_MAX_CHARS = 60
TOPICS_LINES = 20  # the owner: «я пропоную 20»

TOPICS_SYSTEM = (
    "Перед тобою кінець переписки двох людей, {name} та Ich, наодинці. Визнач, про що вони говорять: не більше "
    "{most} тем, кожна — кількома словами, так, як сказала б про це сама {name} («його звіти й дедлайни», «вечір на "
    "Замку», «мій сценарій»). Для кожної теми порахуй, скільки повідомлень {name} її торкаються (her) і скільки "
    "повідомлень Ich (his). Їхню близькість, ніжність і пестощі темою не називай. Відповідай лише JSON: "
    '{{"topics": [{{"topic": "…", "her": 0, "his": 0}}]}}.'
)
TOPICS_TITLE = "Про що ваша розмова (з останніх {n} повідомлень):"
# v5.25 (the owner, 2026-11-05: «фікс по темам занадто сильно заставляє її стрибати між темами в середині одного
# меседжа»): one topic a message — a new one only once his is done, and then the whole message
TOPICS_CHOOSE = ("Тему для продовження вибери сама. Одне повідомлення — одна тема: не перескакуй з теми на тему "
                 "посеред повідомлення. Зазвичай лишайся в тому, що він щойно написав; на те, що тобі самій зараз "
                 "цікаве, переходь, лише коли його тема вичерпалась, — і тоді все повідомлення про нове. До того, про "
                 "що ти вже сказала багато, сама не повертайся.")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def topics_request(name: str, lines: list[tuple[str, str]]) -> tuple[str, str]:
    """(system instruction, contents) for the list: their last lines (speaker, text), both sides, oldest first."""
    return (TOPICS_SYSTEM.format(name=name, most=TOPICS_MAX),
            "Переписка:\n" + "\n".join(f"{who}: {text}" for who, text in lines))


def _count(value, n: int) -> int | None:
    """A whole count from 0, at most `n` (a count past the lines read is cut to them); None for anything else."""
    return min(value, n) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def parse_topics(raw: str, n: int) -> list[tuple[str, int, int]] | None:
    """The answer as (topic, her, his), at most `TOPICS_MAX`: a topic of at most `TOPIC_MAX_CHARS`, the counts whole
    numbers from 0, cut to `n` (the lines read); a topic both left untouched, one with a bad count, or one that names
    what she is (`BANNED_RE`) is dropped. None for a malformed answer."""
    match = _JSON_RE.search(raw or "")
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        return None
    items = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[tuple[str, int, int]] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("topic"), str):
            continue
        topic = " ".join(item["topic"].split()).strip(" .;—-")
        her, his = _count(item.get("her"), n), _count(item.get("his"), n)
        if (not topic or len(topic) > TOPIC_MAX_CHARS or her is None or his is None or her + his == 0
                or BANNED_RE.search(topic)):
            continue
        out.append((topic, her, his))
        if len(out) == TOPICS_MAX:
            break
    return out


def _times(k: int) -> str:
    """«1 раз», «3 рази», «7 разів» — the Ukrainian plural."""
    if k % 10 == 1 and k % 100 != 11:
        return f"{k} раз"
    if 2 <= k % 10 <= 4 and not 12 <= k % 100 <= 14:
        return f"{k} рази"
    return f"{k} разів"


def topics_section(topics: list[tuple[str, int, int]], n: int) -> str | None:
    """Her prompt's list and the line that she picks; None with no topic."""
    if not topics:
        return None
    lines = [f"- {topic} — ти {_times(her)}, він {_times(his)};" for topic, her, his in topics]
    return TOPICS_TITLE.format(n=n) + "\n" + "\n".join(lines) + "\n\n" + TOPICS_CHOOSE
