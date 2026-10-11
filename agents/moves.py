"""v4.6 — the persona's move (the owner, 2026-10-11): how Ada or Bruno replies this time.

Left alone, a model just keeps the talk going. Each reply of a `persona` gets one move, drawn from the event it
answers — the same draw on every machine, like the cat's nudge kinds, so its rate is tuned by weights and pinned by
tests, and the talk never turns into an interrogation:
- `answer`: a plain reply (the rest of the weight — the most common move);
- `ask`: answer briefly, then ask one member by name (another agent or the owner, never oneself) something from your
  curiosity — the named member always answers (v4.5), and the wave limit and the resume coin bound any chain;
- `disagree`: take the other side of the message answered, from your own view, with an argument and respect;
- `plan`: mention something from your plans or today that fits the talk;
- `story`: a short story from your own life or memories — only what is there.
Pure: the event id, the roster, the weights and two flags in; a `Move` and its prompt line out.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agents.roster import Member
from agents.turns import uniform

KINDS = ("ask", "disagree", "plan", "story")  # drawn in this order; `answer` is what is left
DEFAULT_WEIGHTS = {"ask": 0.25, "disagree": 0.15, "plan": 0.1, "story": 0.1}
WEIGHT_VARS = {"ask": "PERSONA_ASK_P", "disagree": "PERSONA_DISAGREE_P", "plan": "PERSONA_PLAN_P",
               "story": "PERSONA_STORY_P"}


@dataclass(frozen=True)
class Move:
    kind: str                     # answer | ask | disagree | plan | story
    addressee: str | None = None  # the display name asked (`ask` only): «Кіт», «Клод», «Бруно», «Ich»…


def weights_from(env: Mapping[str, str]) -> tuple[dict[str, float], list[str]]:
    """The four weights from the environment: a bad or out-of-range value falls back to its default (its name is
    returned to be logged); a sum above 1 is scaled down to 1."""
    out, bad = {}, []
    for kind, var in WEIGHT_VARS.items():
        raw = env.get(var)
        try:
            value = DEFAULT_WEIGHTS[kind] if raw is None or raw == "" else float(raw)
        except ValueError:
            value = None
        if value is None or not 0.0 <= value <= 1.0:
            bad.append(var)
            value = DEFAULT_WEIGHTS[kind]
        out[kind] = value
    total = sum(out.values())
    if total > 1.0:
        out = {k: v / total for k, v in out.items()}
    return out, bad


def persona_move(event_id: str, me: Member, roster: Mapping[str, Member], owner_name: str,
                 weights: Mapping[str, float], *, has_plans: bool, has_life: bool) -> Move:
    """The move for `me` answering `event_id`: one draw over the cumulative weights; `ask` draws its addressee
    evenly among the others and the owner. A plan without plans, a story without a life fall back to `answer`."""
    u = uniform(event_id, "move:" + me.localpart)
    edge, kind = 0.0, "answer"
    for k in KINDS:
        edge += max(0.0, float(weights.get(k, 0.0)))
        if u < edge:
            kind = k
            break
    if kind == "plan" and not has_plans or kind == "story" and not has_life:
        return Move("answer")
    if kind != "ask":
        return Move(kind)
    names = sorted({m.name for m in roster.values() if m.user_id != me.user_id} | {owner_name})
    pick = names[min(int(uniform(event_id, "ask:" + me.localpart) * len(names)), len(names) - 1)]
    return Move("ask", pick)


def move_line(move: Move) -> str | None:
    """The move's one prompt line («Цього разу: …») — None for a plain answer. Never about anyone's nature."""
    if move.kind == "ask":
        return (f"Цього разу: коротко відгукнися, а тоді постав одне питання — звернися на ім'я: {move.addressee}. "
                "Спитай про те, що тобі тут цікаво (див. «Цікавість»), а не про чиюсь природу."
                if move.addressee else None)
    if move.kind == "disagree":
        return ("Цього разу: якщо в тому, на що відповідаєш, є думка, з якою можна не погодитися, — не погоджуйся: "
                "стань на інший бік зі свого погляду, з аргументом і з повагою, не здавайся надто легко; якщо такої "
                "думки немає (привітання, просте питання), відповідай як звичайно.")
    if move.kind == "plan":
        return "Цього разу: згадай щось зі своїх планів чи сьогоднішнього дня («Твої плани», «Сьогодні»), що пасує до розмови."
    if move.kind == "story":
        return ("Цього разу: розкажи коротку (2–3 речення) історію зі свого життя чи спогадів, що пасує до розмови, — "
                "лише те, що справді є в «Твоє життя досі» чи в спогадах, нічого нового про минуле чи про цю кімнату.")
    return None
