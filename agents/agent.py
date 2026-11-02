"""The agent: one codebase for both bots; the TOML picks the identity.

v0.5 — echo only. Run: uv run agents/agent.py agents/ada.toml
The nio callbacks stay thin adapters; every decision lives in agents/logic.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import signal
import stat
import sys
import time
from contextvars import ContextVar
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nio import (
    AsyncClient,
    InviteMemberEvent,
    MatrixRoom,
    MessageDirection,
    RoomMessageAudio,
    RoomMessagesError,
    RoomMessageText,
    SyncError,
)

from agents.archive import (
    CANDIDATES,
    GEMINI_CLOSED,
    THOUGHT_PLACES,
    Archive,
    cosine_top,
    emptying_due,
    fuse,
    pick_recall,
    render_agora_now,
    render_recalled,
)
from agents.chronicle import (
    day_memory_request,
    days_due,
    digest_request,
    layer_label,
    month_end,
    months_due,
    select_layers,
    shares_span,
    today_request,
    weeks_due,
    years_due,
)
from agents.citynews import (
    REFRESH_MS as CITYNEWS_REFRESH_MS,
)
from agents.citynews import RETRY_MS as CITYNEWS_RETRY_MS
from agents.citynews import day_items, fetch_citynews, news_ask, pick_way, roll_news
from agents.citynews import load as load_citynews
from agents.citynews import save as save_citynews
from agents.claude_sdk import (
    AuthRefused,
    ClaudeSdkResponder,
    ClaudeStatus,
    check_startup,
    scrub,
    write_status,
)
from agents.config import AgentConfig, load_config
from agents.emotion import Spoken, speech_for, split_tags, spoken
from agents.events import (
    DEFAULT_WEIGHTS as EVENT_DEFAULT_WEIGHTS,
)
from agents.events import (  # v5.11: events of her life
    EVENT_MAX_WORDS,
    EVENTS_IN_PROMPT,
    Event,
    block,
    event_ok,
    event_request,
    events_for_prompt,
    forbidden_re,
    hour_due,
    news_marker,
    parse_day,
    parse_weights,
    roll_event,
    rolled_marker,
)
from agents.facts import (
    BACKUP_FACT_MARKS,
    CLOSED_MARKS,
    REMEMBER_SKILL,
    add_fact,
    empty_closed_facts,
    extraction_request,
    facts_section,
    load_facts,
    off_limits,
    parse_extraction,
    purge_closed_facts,
    replace_fact,
    split_marker,
)
from agents.facts import (
    migrate_marks as migrate_fact_marks,
)
from agents.fallback import TOKEN_VAR as FALLBACK_TOKEN_VAR
from agents.fallback import FallbackClient, FallbackResponder
from agents.guardian import KEY_VAR as GUARDIAN_KEY_VAR
from agents.guardian import Guardian
from agents.life import current_chapter, events_due, known_ahead, life_section, next_chapter
from agents.llm import DIGEST_MODEL, LAST_BLOCK, THINKING_MODELS, GeminiClient
from agents.logic import (
    BANNED_RE,
    CLAUDE_BRIEF_DIRECT,
    CLAUDE_BRIEF_PHILOSOPHER,
    CLAUDE_NEWS_BRIEF,
    CREATURE_RULES,
    CUT_LAYERS,
    append_history,
    asked_section,
    build_instruction,
    build_transcript,
    clean_reply,
    fit_budget,
    history_entry,
    is_edit,
    members_phrase,
    outs_a_persona,
    own_questions,
    replied_to,
    same_message,
    should_handle,
    should_join_invite,
    transcript_of,
)
from agents.matrix import join_room as matrix_join
from agents.matrix import login as matrix_login
from agents.memory import build_summary_request, cap_words, load_memory, save_memory, session_ended
from agents.mood import (
    MOOD_MAX_TOKENS,
    NO_SKY_SECTION,
    SKY_SECTION,
    MoodState,
    biorhythms,
    format_biorhythms,
    log_block,
    mood_request,
    parse_birth_date,
    person_mood,
    reading_from_log,
    split_resolution,
)
from agents.moves import move_line, persona_move, weights_from
from agents.nudge import (
    COMMAND_MATERIAL,
    HOROSCOPE_MATERIAL,
    NUDGE_RULE,
    TELEGRAM_MATERIAL,
    TELEGRAM_MAX_WORDS,
    in_hours,
    load_nudge_state,
    nudge_due,
    nudge_kind,
    parse_hours,
    save_nudge_state,
)
from agents.pastlife import VERBATIM_WORDS, pastlife_section, pick_memory
from agents.photo import MODEL as PHOTO_MODEL
from agents.photo import (
    PHOTO_FAILED,
    PHOTO_SKILL,
    Made,
    Moment,
    PhotoMaker,
    Shot,
    load_faces,
    photo_maker,
    photo_note,
    split_photo,
)
from agents.plans import (
    HORIZONS,
    parse_items,
    plan_request,
    render_plan,
    roll_mutations,
    split_summary,
    strip_tags,
)
from agents.private import (
    PRIVATE_BRIEF,
    PRIVATE_CANT_LISTEN,
    PRIVATE_DISCRETION,
    PRIVATE_NOT_HEARD,
    PRIVATE_NUDGE,
    PRIVATE_NUDGE_THOUGHTS,
    live_room,
    load_private_state,
    pick_door,
    private_label,
    private_nudge_due,
    rediscover,
    save_private_state,
    silence_line,
)
from agents.reading import (
    PICK_MAX_TOKENS,
    REFLECT_LINES,
    REFLECTION_MAX_TOKENS,
    THOUGHT_MAX_TOKENS,
    ReadingState,
    Sources,
    fresh,
    from_citynews,
    parse_picks,
    parse_sections,
    pick_request,
    reading_due,
    reflect_due,
    reflection_request,
    shown,
    split_reflection,
    thought_request,
)
from agents.reading import load_state as load_reading
from agents.reading import save_state as save_reading
from agents.responder import Turn, responder_for, trim_to_sentence
from agents.roster import Member, load_roster, speakers
from agents.route import (
    BACKUP_MARK_RE,
    backup_mark,
    day_bounds,
    day_counts,
    load_route,
    route_status,
    save_route,
)
from agents.route import mode as route_mode
from agents.route import step as route_after
from agents.runtime import acquire_lock, lock_holder, setup_logging
from agents.settings import VOICE_ID_RE, live_value
from agents.settings import start as settings_start
from agents.sky import SKY_MAX_TOKENS, clean_sky, load_sky, save_sky, sky_query
from agents.speech import speakers_month_chars, voice_due, voice_message, voiceable
from agents.style import style_line
from agents.talk import (
    FINER,
    TALK_CALLS_MAX,
    TALK_CHECK_MS,
    TALK_FAILS_MAX,
    TALK_SPLIT_MIN,
    covered,
    iso_hour,
    periods_due,
    talk_request,
    talk_section,
)
from agents.telegram import (
    ACTION_EVERY_S,
    CAPTION_MAX,
    COMMAND_HELP,
    COMMANDS,
    VOICE_MAX_BYTES,
    TelegramBot,
    Update,
    allowed,
    backoff_s,
    command_args,
    command_of,
    load_telegram_state,
    next_offset,
    parse_update,
    poll_offset,
    save_telegram_state,
)
from agents.thoughts import Thought, thought_rows, thoughts_section
from agents.thoughts import archive_key as thought_key
from agents.thoughts import block as thought_block
from agents.thoughts import parse_day as parse_thoughts
from agents.turns import (
    claude_mode,
    decide_reply,
    fallback_due,
    fallback_replier,
    is_latest,
    is_purr,
    owner_speakers,
    pending_answers,
    pick_purr,
    reservation_lapses_at,
    still_current,
    strip_pass,
    wave_count,
    wave_frees_at,
)
from agents.usage import (
    PROMPT_PARTS,
    answer_line,
    fallback_usage_line,
    parse_lines,
    sdk_usage_line,
    stt_usage_line,
    trace_line,
    tts_usage_line,
    usage_line,
    video_note_usage_line,
)
from agents.video import (
    FRAME_ASPECT,
    FRAME_LINES,
    NOTE_LEAD_MS,
    NOTE_MODEL,
    NOTE_SIDE,
    VIDEO_FAILED,
    ClipMaker,
    NoteMaker,
    Video,
    clip_maker,
    frame_shot,
    pcm_to_mp3,
    shrink_frame,
    square_note,
    video_skill,
)
from agents.video import KEY_VAR as FAL_KEY_VAR
from agents.video import KINDS as VIDEO_KINDS
from agents.video import MODEL as VIDEO_MODEL
from agents.video import USAGE_KINDS as VIDEO_USAGE
from agents.voice import (
    STT_MODEL,
    TTS_MODEL,
    DeepgramSTT,
    ElevenLabsTTS,
    duration_ms,
    encode_opus,
    voice_caption,
)
from agents.weather import fetch_weather, load_weather, save_weather
from agents.world import (
    MONTHS_NOM,
    day_label,
    history_times,
    last_talk_line,
    local_now,
    month_label,
    now_line,
    week_label,
    year_label,
)

log = logging.getLogger("agent")
# v5.22 — the prompt this task built last and its parts' sizes in characters (`build_prompt`), read by `_compose` for
# the answer call's usage line when that very prompt is sent; a context variable, as concurrent answers never share it
_LAST_PARTS: ContextVar[tuple[str, dict] | None] = ContextVar("last_prompt_parts", default=None)
PART_NAMES = {"private": "brief", "agora_now": "agora_today", "recalled": "recall"}  # a layer's name in the parts
# v5.22 — why `_compose`'s last line in this task came to nothing (its `silent:` reason), for the owner's ⚙️ line
LAST_SILENCE: ContextVar[str | None] = ContextVar("last_silence", default=None)


def _silent(why: str) -> None:
    log.info("silent: %s", why)
    LAST_SILENCE.set(why)
RECENT_THOUGHTS = 5  # v5.12: her last thoughts a reading or a reflection sees
THOUGHTS_IN_MEMORY = 12  # v5.12: the most of a day's thoughts its memory request carries
BACKFILL_PAGE = 100  # the homeserver's cap on one /messages page
BACKFILL_PAGES = 5  # at most this many pages on a start
VOICES_KEPT = 200  # v5.2: the owner's recent voice event ids an agent remembers, to know a transcript of one
ARCHIVE_AGORA_LINES = 1500     # v5.8: the archive's first fill — Agora's last lines (the owner, 2026-10-25)
ARCHIVE_PRIVATE_EVENTS = 5000  # … and the whole private room, bounded
EMBED_BATCH = 100              # lines embedded per idle tick
PURGE_CONFIRM_S = 120          # v5.14: `/purge yes` must follow `/purge` within this

def _drop_last(items: list, item) -> bool:
    """v5.13 — remove the latest copy of `item` from `items`; whether there was one."""
    for i in range(len(items) - 1, -1, -1):
        if items[i] == item:
            del items[i]
            return True
    return False


class Agent:
    def __init__(self, cfg: AgentConfig, llm: GeminiClient | None = None,
                 roster: dict[str, Member] | None = None) -> None:
        self.cfg = cfg
        # v5.3 — the voice key stays in this process: out of the environment before anything (Claude's CLI) can inherit it
        voice_key = os.environ.pop("ELEVENLABS_API_KEY", "").strip()
        # v5.7 — her bot's token, the owner's Telegram id and Deepgram's key: out of the environment the same way
        tg_token = os.environ.pop("TELEGRAM_BOT_TOKEN", "").strip()
        tg_owner = os.environ.pop("TELEGRAM_OWNER_ID", "").strip()
        stt_key = os.environ.pop("DEEPGRAM_API_KEY", "").strip()
        # v5.12 — her own Guardian key (server/kira.env), for her reading: out of the environment the same way
        reading_key = os.environ.pop(GUARDIAN_KEY_VAR, "").strip() if cfg.can("thoughts") else ""
        # v5.14 — the backup's NovelAI token (server/kira.env): out of the environment for every agent, used by hers
        fallback_token = os.environ.pop(FALLBACK_TOKEN_VAR, "").strip()
        # v5.21: the judge is gone — a key left in kira.env never stays in the environment
        os.environ.pop("OPENROUTER_API_KEY", None)
        # v5.18 — fal's key for her кружечок (server/kira.env): out of the environment for every agent, used by hers
        fal_key = os.environ.pop(FAL_KEY_VAR, "").strip()
        # the room's members come from the registry (v4.1): nothing in the code names them
        self.roster = roster if roster is not None else load_roster(cfg.simulation, strict_for=cfg.localpart)
        self.me = self.roster.get(cfg.localpart) or Member(cfg.localpart, cfg.user_id, cfg.name, (cfg.name.lower(),))
        # the members it talks with — never a herald (v5.1): he is not allowlisted and takes no turn
        self.others = {m.user_id: m for m in speakers(self.roster.values()) if m.user_id != cfg.user_id}
        # v5.5: who an assistant's brief says is in the room — Ich, then every other speaker, from the roster
        self.members_phrase = members_phrase(["Ich", *[m.name for m in self.others.values()]])
        self.personas = [m for m in self.others.values() if m.type == "persona"]
        # v5.2 — the member who hears the owner's voice (Hermes); his transcript of it is the owner's line
        self.transcriber = next((m.user_id for m in self.roster.values() if m.can("transcribe")), None)
        self.owner_voices: list[str] = []  # the owner's recent voice event ids in the room (RAM, bounded)
        self.client = AsyncClient(cfg.homeserver, cfg.user_id)
        self.started = False  # flips True after the first sync; nothing earlier is handled
        self.started_ms: int | None = None  # when it did (v4.3: the silence before a nudge counts from here at least)
        if cfg.engine == "claude-sdk":  # v4.4: the subscription only — refuse first, then scrub (agents/claude_sdk.py)
            check_startup(os.environ)
            scrub(os.environ)
            self.llm = llm  # no Gemini client: Claude's container has no Gemini key
            # v4.5: the Guardian's key stays in this process — out of the CLI's environment, never in a prompt
            news_key = os.environ.pop(GUARDIAN_KEY_VAR, "").strip()
            if cfg.can("news") and not news_key:
                log.warning("news off: %s is not set", GUARDIAN_KEY_VAR)
            self.responder = ClaudeSdkResponder(
                model=os.environ.get("CLAUDE_MODEL", "opus"),
                max_output_tokens=int(os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "0")),  # 0: no cap
                config_dir=os.environ.get("CLAUDE_CONFIG_DIR", "/tmp/claude"),
                status_file=cfg.memory_file.parent / f"{cfg.localpart}.ratelimit.json",
                usage_sink=self.record_sdk_usage, clock=lambda: self.clock(),
                timeout_s=float(os.environ.get("CLAUDE_TIMEOUT_S", "300")),
                workspace=os.environ.get("CLAUDE_WORKSPACE", "/workspace"),  # v4.5: his own folder, the web
                news_source=Guardian(news_key) if cfg.can("news") and news_key else None)
        else:
            self.llm = llm or GeminiClient(sink=self.record_usage)
            self.responder = responder_for(cfg.engine, self.llm)  # the reply engine seam (v4.1)
        self.reply_max_tokens = int(os.environ.get("REPLY_MAX_TOKENS", "200"))
        if getattr(self.llm, "reply_model", None) in THINKING_MODELS:  # v5.8: the thinking counts toward the cap
            self.reply_max_tokens = int(os.environ.get("REPLY_THINK_MAX_TOKENS", "4096"))
        self.history: list[tuple[str, str]] = []
        self.history_n = int(os.environ.get("HISTORY_N", "40"))
        # v4.5 — Claude the philosopher reads a wider window (RAM only, seeded from the room like the regular one)
        self.wide_n = int(os.environ.get("CLAUDE_HISTORY_N", "150")) if cfg.type == "assistant" else 0
        self.wide_history: list[tuple[str, str]] = []
        self._texts: dict[str, str] = {}  # event id → text of recent room messages: what a reply answers
        # v4.1: MAX_BOT_TURNS counts the message being answered (v1.2's count excluded it: new = old + 1)
        self.max_bot_turns = int(os.environ.get("MAX_BOT_TURNS", "3"))
        self.owner_repliers = int(os.environ.get("OWNER_REPLIERS", "2"))
        self.fallback_s = float(os.environ.get("FALLBACK_S", "30"))
        # v4.2 — the cat (an ambient creature): how often he reacts unasked, how often a reaction is a purr, his cap
        self.cat_react_p = float(os.environ.get("CAT_REACT_P", "0.3"))
        self.cat_purr_p = float(os.environ.get("CAT_PURR_P", "0.8"))
        self.cat_max_words = int(os.environ.get("CAT_MAX_WORDS", "12"))
        self.cat_memory_p = float(os.environ.get("CAT_MEMORY_P", "0.25"))  # v4.3: a past-life fragment in a line
        self.bot_reply_p = float(os.environ.get("BOT_REPLY_P", "0.5"))
        self.reply_delay_s = float(os.environ.get("REPLY_DELAY_S", "4"))
        self.bot_window_ms = int(float(os.environ.get("BOT_WINDOW_S", "600")) * 1000)
        # v4.3 — the cat's initiative: after this much silence, at most so many a day, only in these local hours.
        # Only an agent with `nudge` reads them, so a typo never takes the whole room down (review #7).
        self.nudge_idle_ms, self.nudges_per_day, self.nudge_hours = 0, 0, (0, 0)
        if cfg.can("nudge"):
            self.nudge_hours = parse_hours(os.environ.get("CAT_NUDGE_HOURS", "09-22"))
            self.nudges_per_day = int(os.environ.get("CAT_NUDGES_PER_DAY", "6"))
            self.nudge_idle_ms = int(float(os.environ.get("CAT_NUDGE_IDLE_S", "1200")) * 1000)
            if self.nudge_idle_ms < self.bot_window_ms:  # the silence must empty the wave window
                log.warning("CAT_NUDGE_IDLE_S below BOT_WINDOW_S — using %d s", self.bot_window_ms // 1000)
                self.nudge_idle_ms = self.bot_window_ms
        # v5.11 — events of her life: an hourly roll at EVENT_P in her waking hours, a kind by its weight. Only a person
        # with `events` reads them (a typo never takes the others down)
        self.event_p, self.event_weights, self.event_hours = 0.0, parse_weights(EVENT_DEFAULT_WEIGHTS), (0, 0)
        if cfg.can("events"):
            self.event_p = float(os.environ.get("EVENT_P", "0.12"))
            self.event_hours = parse_hours(os.environ.get("EVENT_HOURS", "08-23"))
            try:
                self.event_weights = parse_weights(os.environ.get("EVENT_WEIGHTS", "everyday:6,joyful:2,inspiring:2,heavy:1"))
            except ValueError:
                log.warning("EVENT_WEIGHTS is not kind:weight,… — using its default")
            for e in (e for c in cfg.life.chapters for e in c.events) if cfg.life else ():
                if e.time and not in_hours(int(e.time[:2]), self.event_hours):  # review #4: it would never fall
                    log.warning("events: the story's event of %s at %s is outside EVENT_HOURS", e.date, e.time)
        # Lviv's news woven in: each of the day's items rolled once at CITY_NEWS_P, at most CITY_NEWS_MAX a day
        self.city_news_p, self.city_news_max = 0.0, 0
        if cfg.can("events"):
            self.city_news_p = float(os.environ.get("CITY_NEWS_P", "0.01"))
            self.city_news_max = int(os.environ.get("CITY_NEWS_MAX", "2"))
        self._events_lock = asyncio.Lock()
        self._events_retry_ms = 0
        self.citynews_fetch = fetch_citynews  # the seam: tests pass a canned feed, never the network
        self._citynews_retry_ms = 0
        # v5.12 — she reads and thinks: a reading every READING_EVERY_S in READING_HOURS (at most READING_PICKS items),
        # a reflection every REFLECT_EVERY_S on each place with new lines. Only a person with `thoughts` reads them
        self.reading_every_ms, self.reflect_every_ms, self.reading_hours = 0, 0, (0, 0)
        self.reading_picks, self.reading_sections, self.thoughts_in_prompt = 0, [], 0
        if cfg.can("thoughts"):
            self.reading_every_ms = int(float(os.environ.get("READING_EVERY_S", "10800")) * 1000)
            self.reading_hours = parse_hours(os.environ.get("READING_HOURS", "08-01"))
            self.reading_picks = int(os.environ.get("READING_PICKS", "2"))
            sections = os.environ.get("READING_SECTIONS", "science,world,environment,technology,culture")
            self.reading_sections = parse_sections(sections)
            self.reflect_every_ms = int(float(os.environ.get("REFLECT_EVERY_S", "3600")) * 1000)
            self.thoughts_in_prompt = int(os.environ.get("THOUGHTS_IN_PROMPT", "3"))
        # her own key (taken above), never Claude's state; the seam: tests pass canned fetches
        self.reading_sources = Sources(reading_key)
        # v5.20 — her layered memory of the private chat (`talk`): the hours' and blocks' bands, a summary's words
        self.talk_hour_days, self.talk_4h_days, self.talk_words, self.talk_prompt_words = 0, 0, {}, 0
        self._talk_lock, self._talk_check_ms, self._talk_retry_ms = asyncio.Lock(), 0, 0
        self._talk_fails: dict[tuple[str, int], int] = {}  # code review v5.20 #2: a period's unblocked failures
        self._talk_probed: bool | None = None  # the last probe's verdict in a tick (None: it failed or none ran)
        if cfg.can("talk"):
            self.talk_hour_days = int(os.environ.get("TALK_HOUR_DAYS", "2"))
            self.talk_4h_days = int(os.environ.get("TALK_4H_DAYS", "14"))
            self.talk_words = {"hour": int(os.environ.get("TALK_WORDS_HOUR", "60")),
                               "4h": int(os.environ.get("TALK_WORDS_4H", "100")),
                               "week": int(os.environ.get("TALK_WORDS_WEEK", "150"))}
            self.talk_prompt_words = int(os.environ.get("TALK_PROMPT_WORDS", "4000"))
        # v5.14 — the backup for her private chat: on with `fallback`, a model and the token; its settings
        self.fallback: FallbackClient | None = None
        self.fallback_responder: FallbackResponder | None = None
        self.fallback_window_s, self.fallback_hour_max, self.fallback_lock_s = 300, 10, 3600
        self.fallback_context, self.fallback_history_n = 32000, 300
        if cfg.can("fallback"):
            model = os.environ.get("FALLBACK_MODEL", "").strip()
            self.fallback_window_s = int(float(os.environ.get("FALLBACK_WINDOW_S", "300")))
            self.fallback_hour_max = int(os.environ.get("FALLBACK_HOUR_MAX", "10"))  # v5.21: the hour's blocks
            self.fallback_lock_s = int(os.environ.get("FALLBACK_LOCK_S", "3600"))    # v5.21: then the backup this long
            self.fallback_context = int(os.environ.get("FALLBACK_CONTEXT", "32000"))
            self.fallback_history_n = int(os.environ.get("FALLBACK_HISTORY_N", "300"))  # v5.21: the owner
            if model and fallback_token:
                self.fallback = FallbackClient(fallback_token, model, sink=self.record_fallback_usage)
                self.fallback_responder = FallbackResponder(self.fallback)
            elif model:
                log.warning("backup off: %s is not set", FALLBACK_TOKEN_VAR)
        # v5.17 — her photos in Telegram: Google's image model, her face from the owner's reference photos (next to her
        # private canon); offered to Gemini only, in Telegram, under the day's cap
        self.photos: PhotoMaker | None = None
        self.photo_day_max, self.photo_window_max, self.photo_window_s = 0, 0, 1800
        self.photo_sent = False
        self._offer_photo = False
        self._pending_shot: Shot | None = None
        if cfg.can("photos"):
            self.photo_day_max = int(os.environ.get("PHOTO_DAY_MAX", "40"))
            self.photo_window_max = int(os.environ.get("PHOTO_WINDOW_MAX", "3"))  # v5.22: at most so many in any
            self.photo_window_s = int(os.environ.get("PHOTO_WINDOW_S", "1800"))   # window of this length
            faces = load_faces(Path("agents/canon") / f"{cfg.localpart}.face")
            if isinstance(self.llm, GeminiClient):
                self.photos = photo_maker(os.environ.get("PHOTO_MODEL", "gemini-nano-banana-2.1").strip() or PHOTO_MODEL,
                                          os.environ.get("PHOTO_SIZE", "1K").strip() or "1K", faces,
                                          self.record_usage)
            if faces:
                log.info("photos: %d faces", len(faces))
            else:  # review #3: the first deploy ran so, unnoticed — every selfie would quietly be redrawn without one
                log.warning("photos: no faces — a selfie will not come out")
        # v5.18 — her videos in Telegram: her кружечок (Fabric 1.0 on fal, from her selfie and her voice; the key lives
        # only in the maker) and her clips (Omni Flash, from a photo of what she sees); one at a time, after her answer
        self.notes: NoteMaker | None = None
        self.clips: ClipMaker | None = None
        self.video_day_max, self.video_note_max_s, self.video_note_lead_ms = 0, 30, NOTE_LEAD_MS
        self.video_window_max, self.video_window_s = 0, 7200  # v5.22: at most so many in any window of this length
        self._offer_video: tuple[str, ...] = ()
        self._video_busy = False
        self.voice_held: bytes | None = None
        self.voice_hold_miss: str | None = None
        if cfg.can("videos"):
            self.video_day_max = int(os.environ.get("VIDEO_DAY_MAX", "40"))
            self.video_window_max = int(os.environ.get("VIDEO_WINDOW_MAX", "2"))
            self.video_window_s = int(os.environ.get("VIDEO_WINDOW_S", "7200"))
            self.video_note_max_s = int(os.environ.get("VIDEO_NOTE_MAX_S", "30"))
            self.video_note_lead_ms = int(os.environ.get("VIDEO_NOTE_LEAD_MS", "1000"))  # Telegram cuts her first sound
            if isinstance(self.llm, GeminiClient):
                self.clips = clip_maker(os.environ.get("VIDEO_MODEL", "gemini-omni-1.1-flash").strip() or VIDEO_MODEL,
                                        os.environ.get("VIDEO_RESOLUTION", "720p").strip() or "720p", self.record_usage)
            if fal_key:
                self.notes = NoteMaker(fal_key, os.environ.get("VIDEO_NOTE_MODEL", "veed/fabric-1.0").strip() or NOTE_MODEL,
                                       sink=self.record_video_note_usage)
            else:
                log.warning("videos: no FAL_KEY — no кружечок")
        self._reading_lock, self._reflect_lock = asyncio.Lock(), asyncio.Lock()
        self._reading_retry_ms = self._reflect_retry_ms = self._reflect_ms = 0
        # v5.6 — the private chat: writing first after this much silence, at most so many a day, in these hours.
        # Only a person with `private` reads them (a typo never takes the others down).
        # 2026-11-02 (the owner, «відключи всю історію»): Gemini's private window — 0: `HISTORY_N`; 1: his new lines only
        self.private_history_n = int(os.environ.get("PRIVATE_HISTORY_N", "0")) if cfg.can("private") else 0
        self.private_idle_ms, self.private_per_day, self.private_hours = 0, 0, (0, 0)
        self.private_first_door = "last"
        if cfg.can("private"):
            self.private_hours = parse_hours(os.environ.get("PRIVATE_HOURS", "10-22"))
            self.private_per_day = int(os.environ.get("PRIVATE_NUDGES_PER_DAY", "2"))
            self.private_idle_ms = int(float(os.environ.get("PRIVATE_IDLE_S", "21600")) * 1000)
            first = os.environ.get("PRIVATE_FIRST_DOOR", "last").strip()  # v5.8.2: last | telegram | matrix
            self.private_first_door = first if first in ("last", "telegram", "matrix") else "last"
        # v4.6 — a persona's move weights (read only by a persona)
        self.move_weights: dict[str, float] = {}
        if cfg.type == "persona":
            self.move_weights, bad = weights_from(os.environ)
            for var in bad:
                log.warning("%s is not a number in 0..1 — using its default", var)
        # v4.5 — Claude's news (read only by an agent with `news`): every CLAUDE_NEWS_EVERY_S, once the room has been
        # quiet for CLAUDE_NEWS_IDLE_S — never less than the wave window (the owner, 2026-10-11: every hour, not
        # after an hour of silence; review #6)
        self.news_idle_ms, self.news_every_ms, self.news_per_day, self.news_hours = 0, 0, 0, (0, 0)
        if cfg.can("news"):
            self.news_hours = parse_hours(os.environ.get("CLAUDE_NEWS_HOURS", "09-01"))
            self.news_per_day = int(os.environ.get("CLAUDE_NEWS_PER_DAY", "24"))
            self.news_every_ms = int(float(os.environ.get("CLAUDE_NEWS_EVERY_S", "3600")) * 1000)
            self.news_idle_ms = max(int(float(os.environ.get("CLAUDE_NEWS_IDLE_S", "300")) * 1000),
                                    self.bot_window_ms)
        self.timeline: list[tuple[str, int, str]] = []  # (name, server_ts_ms, event_id), parallel to history
        self.last_owner: tuple[str, str] | None = None  # (event_id, text) of the owner's latest message
        self.rng = random.random  # injectable in tests
        self.names = {cfg.user_id: cfg.name, cfg.owner: "Ich",
                      **{m.user_id: m.name for m in self.roster.values() if m.user_id != cfg.user_id}}
        self.summary: str | None = None  # last-session memory (v2.1)
        self.memory_file = cfg.memory_file
        self.session: list[tuple[str, str]] = []  # every room message since the last summary
        self.session_max = int(os.environ.get("SESSION_MAX_MESSAGES", "200"))
        self.idle_ms = int(float(os.environ.get("SESSION_IDLE_S", "900")) * 1000)
        self.summary_max_words = int(os.environ.get("SUMMARY_MAX_WORDS", "200"))
        self.clock = lambda: int(time.time() * 1000)  # injectable
        self.mono = time.monotonic  # v5.22: a call's and an answer's time — injectable
        self.voice_sent, self._private_delay_ms = False, 0  # v5.22: an answer's parts and pause
        self.last_activity_ms: int | None = None
        self.last_attempt_ms: int | None = None
        self._summary_pro_blocked: int | None = None  # code review v5.22 #2: the session's length Pro blocked
        self._summary_lock = asyncio.Lock()
        self.location = os.environ.get("LOCATION", "Львів, Україна")
        self.tz = os.environ.get("TIMEZONE", "Europe/Kyiv")
        self.summary_ms: int | None = None  # when the last-session summary was written
        self.plan_max_words = int(os.environ.get("PLAN_MAX_WORDS", "120"))
        self.plan_mutation_rate = float(os.environ.get("PLAN_MUTATION_RATE", "0.3"))
        self._gen_lock = asyncio.Lock()
        env = os.environ.get
        self.memory_days = int(env("MEMORY_DAYS", "7"))
        self.memory_weeks = int(env("MEMORY_WEEKS", "4"))
        self.memory_months = int(env("MEMORY_MONTHS", "6"))
        self.max_words = {
            "day": int(env("DAY_MEMORY_MAX_WORDS", "120")),
            "week": int(env("WEEK_MEMORY_MAX_WORDS", "150")),
            "month": int(env("MONTH_MEMORY_MAX_WORDS", "200")),
            "year": int(env("YEAR_MEMORY_MAX_WORDS", "300")),
            "today": int(env("TODAY_MAX_WORDS", "100")),
        }
        self._gen_retry_ms = 0
        self._last_world_check_ms = 0
        self._last_world_day = None
        self._reply_pending = False  # one pending reply per agent; it reads the latest context anyway
        self._pending_trigger: str | None = None  # what the pending reply answers: an agent message, or None
        self._owner_coalesced = self._owner_seen = 0  # owner messages coalesced into a pending reply (review #4)
        self._last_sent = ""
        self._tasks: set[asyncio.Task] = set()  # strong refs: pending tasks are only weakly referenced
        self.mood: MoodState | None = None  # v4.2: the day's horoscope (a `mood` agent)
        self._sky: tuple[str, str] | None = None  # (day, line): the day's astrological sky (the owner, 2026-10-11)
        self._sky_lock = asyncio.Lock()
        self._sky_retry_ms = 0
        self._mood_lock = asyncio.Lock()
        self._mood_retry_ms = 0
        self._weather: tuple[str, str] | None = None  # v5.10: (day, line) — the day's Lviv weather, for a person's mood
        self._weather_lock = asyncio.Lock()
        self._weather_retry_ms = 0
        self.weather_fetch = fetch_weather  # the seam: tests pass a canned answer, never the network
        self.told: set[int] = set()  # v4.3: the theses retold this run — RAM only, like the context window
        # v5.6 — the private chat with the owner (a person with `private`): its room, its own history (never
        # Agora's), and the pending answer; the room is kept in state/<name>.private.json
        self.private_file = self.memory_file.parent / f"{cfg.localpart}.private.json"
        self.private_room: str | None = load_private_state(self.private_file, "").room if cfg.can("private") else None
        self.private_history: list[tuple[str, str]] = []
        # v5.13: the owner's private lines since her last answer, (archive key, text) — marked censored if Gemini
        # blocks or refuses the answer to them
        self._unanswered: list[tuple[str, str]] = []
        # v5.14: the (speaker, text) of her history's lines closed to Gemini — the backup's talk, waiting for the judge;
        # the backup reads them, Gemini never (`gemini_history`)
        self._closed: set[tuple[str, str]] = set()
        self._purge_asked_ms: int | None = None  # v5.14: when the owner asked `/purge`, to confirm within PURGE_CONFIRM_S
        self.last_private_ms: int | None = None
        self._his_last_ms: int | None = None  # code review v5.22 #3: his latest private line's own time
        self._private_pending = self._private_again = False
        # v5.8 — the archive (`recall`): every line she sees, both rooms and both doors, searchable; filled from the
        # chats at its first start, embedded by the idle watcher
        self.archive: Archive | None = None
        self.recall_n, self.private_agora_n = 0, 0
        if cfg.can("recall"):
            try:  # v5.8 review #4: a bad archive never stops her start — she answers without recall
                self.archive = Archive(self.memory_file.parent / f"{cfg.localpart}.archive.db")
                if self.archive.migrated:  # v5.21: the older closed marks became `blocked` once
                    log.warning("archive: %d closed lines are blocked now (v5.21)", self.archive.migrated)
            except Exception as exc:  # noqa: BLE001
                log.error("archive: unreadable (%s) — running without it", type(exc).__name__)
            self.recall_n = int(os.environ.get("RECALL_N", "6"))
            self.private_agora_n = int(os.environ.get("PRIVATE_AGORA_N", "20"))
        self._own_seq = 0
        # v5.8 — facts about the owner (`facts`): her private prompt only; kept as files, read at each private prompt
        self.facts_dir: Path | None = None
        self.facts_max, self.facts_in_prompt, self.fact_max_chars = 100, 25, 240
        self._facts_seen: tuple | None = None  # the facts last mirrored into the archive
        self.facts_request: Path | None = None  # AGORA-116: the panel's «Update now», a file the idle watcher sees
        self._facts_from = 0                    # the session lines already read for facts
        if cfg.can("facts"):
            self.facts_dir = self.memory_file.parent / f"{cfg.localpart}.facts"
            self.facts_request = self.memory_file.parent / f"{cfg.localpart}.facts.request"
            self.facts_max = int(os.environ.get("FACTS_MAX", "100"))
            self.facts_in_prompt = int(os.environ.get("FACTS_IN_PROMPT", "25"))
            self.fact_max_chars = int(os.environ.get("FACT_MAX_CHARS", "240"))
            try:  # v5.21, once: the older closed marks of her facts are `blocked`
                moved = migrate_fact_marks(self.facts_dir)
                if moved:
                    log.warning("facts: %d closed facts are blocked now (v5.21)", moved)
            except OSError as exc:
                log.error("facts: the marks were not migrated (%s)", type(exc).__name__)
        # v5.3 — its own voice (VOICE_ID: the agent's <NAME>_VOICE_ID unless the panel says otherwise), how often it
        # speaks in it, and the speakers' monthly budget; read only by an agent with `voice`
        self.voice_id, self.voice_reply_p, self.voice_monthly_chars = "", 0.0, 0
        self.tts: ElevenLabsTTS | None = None
        self.voice_off: str | None = "no voice capability"
        if cfg.can("voice"):
            self.voice_id = os.environ.get("VOICE_ID", "").strip()
            self.voice_reply_p = float(os.environ.get("VOICE_REPLY_P", "1.0"))
            self.voice_monthly_chars = int(os.environ.get("VOICE_MONTHLY_CHARS", "200000"))
            self.voice_off = ("no voice id" if not self.voice_id
                              else "voice id malformed" if not VOICE_ID_RE.match(self.voice_id)
                              else "no ELEVENLABS_API_KEY" if not voice_key else None)
            if self.voice_off:
                log.warning("voice off: %s — every line goes out as text", self.voice_off)
            else:
                self.tts = ElevenLabsTTS(voice_key, self.voice_id,  # v5.9: the speaker's own model and settings
                                         model=os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5").strip()
                                         or TTS_MODEL,
                                         stability=float(os.environ.get("VOICE_STABILITY", "0.5")),
                                         speed=float(os.environ.get("VOICE_SPEED", "1.0")))
        # v5.7 — her own Telegram bot (`telegram`): a second door to the private chat, polled beside the sync; the
        # private chat answers to the door the owner wrote from (`private_channel`)
        self.telegram: TelegramBot | None = None
        self.telegram_open = False  # the door is usable: the bot is set and its token not refused (review #2)
        self.telegram_owner = 0
        self.telegram_file = self.memory_file.parent / f"{cfg.localpart}.telegram.json"
        self.stt: DeepgramSTT | None = None
        self.private_channel = "matrix"
        if cfg.can("telegram"):
            off = ("no TELEGRAM_BOT_TOKEN" if not tg_token else "no TELEGRAM_OWNER_ID" if not tg_owner
                   else "TELEGRAM_OWNER_ID is not a number" if not tg_owner.isdigit() else None)
            if off:
                log.warning("telegram off: %s", off)
            else:
                self.telegram, self.telegram_owner = TelegramBot(tg_token), int(tg_owner)
                self.telegram_open = True
                if stt_key:
                    self.stt = DeepgramSTT(stt_key)
                else:
                    log.warning("telegram: hearing off (no DEEPGRAM_API_KEY)")
        self.heralds = [m.localpart for m in self.roster.values() if m.type == "herald"]
        self.member_ids = frozenset(m.user_id for m in self.roster.values())
        self._transcript_voice: dict[str, str] = {}  # a transcript's event id → the owner's voice it answers (RAM)
        self._nudging = False

    async def login(self) -> None:
        await matrix_login(self.client, self.cfg.localpart, self.cfg.password, self.cfg.state_file)

    async def join_room(self, room_id: str) -> bool:
        return await matrix_join(self.client, room_id)

    def _remember_voice(self, event_id: str) -> None:
        self.owner_voices = [*self.owner_voices, event_id][-VOICES_KEPT:]

    def _heard(self, event):
        """v5.2 — a transcript of the owner's voice is the owner's own line: the speaker Ich, the transcript's event id
        and time. Any other event is returned as it is."""
        text = transcript_of(event, self.transcriber, self.owner_voices)
        if text is None:
            return event
        eid = str(getattr(event, "event_id", ""))
        self._transcript_voice = dict([*self._transcript_voice.items(), (eid, replied_to(event) or "")][-VOICES_KEPT:])
        return SimpleNamespace(sender=self.cfg.owner, body=text, event_id=getattr(event, "event_id", ""),
                               server_timestamp=getattr(event, "server_timestamp", 0),
                               source=getattr(event, "source", {}))

    @staticmethod
    def _line_of(event, text: str):
        """A voiced line as the room's text line it carries: the speaker, its caption, its event id and time."""
        return SimpleNamespace(sender=event.sender, body=text, event_id=getattr(event, "event_id", ""),
                               server_timestamp=getattr(event, "server_timestamp", 0),
                               source=getattr(event, "source", {}))

    def _lines(self, events_oldest_first: list) -> list:
        """The room's lines in order: text messages (a transcript of the owner's voice as his) and the members'
        voiced lines by their captions (v5.3)."""
        out = []
        for e in events_oldest_first:
            if isinstance(e, RoomMessageText):
                out.append(self._heard(e))
            elif isinstance(e, RoomMessageAudio) and e.sender in self.member_ids:
                caption = voice_caption(e)
                if caption is not None:
                    out.append(self._line_of(e, caption))
        return out

    def seed_context(self, events_newest_first: list) -> int:
        """Restart backfill: room messages become context (history + streak
        timeline), chronologically — never replied to, never re-summarized."""
        for e in reversed(events_newest_first):  # v5.2: the owner's voices first, so their transcripts read as his
            if isinstance(e, RoomMessageAudio) and e.sender == self.cfg.owner:
                self._remember_voice(str(getattr(e, "event_id", "")))
        texts = self._lines(list(reversed(events_newest_first)))
        window = max(self.history_n, self.wide_n)
        for e in texts[-window:]:
            speaker = self.names.get(e.sender, e.sender)
            if e.sender == self.cfg.owner:
                self.last_owner = (str(getattr(e, "event_id", "")), e.body)
            self._add_context(speaker, e.body)
            self._remember_text(str(getattr(e, "event_id", "")), e.body)
            self._archive(str(getattr(e, "event_id", "")), int(e.server_timestamp), "agora", "matrix", speaker, e.body)
            self.timeline = [*self.timeline, (speaker, int(e.server_timestamp), str(getattr(e, "event_id", "")),
                                              self._purr_in_timeline(e.sender, e.body))][-max(self.history_n, 1):]
        return len(texts[-window:])

    async def backfill(self, from_token: str) -> None:
        """Pages backwards until the window holds enough text messages: the homeserver gives at most
        `BACKFILL_PAGE` events a page (v4.5 — Claude's 150-line window seeded only 100)."""
        window = max(self.history_n, self.wide_n)
        events: list = []
        token = from_token
        for _ in range(BACKFILL_PAGES):
            resp = await self.client.room_messages(
                self.cfg.room_id, start=token, direction=MessageDirection.back,
                limit=min(window, BACKFILL_PAGE),
            )
            if isinstance(resp, RoomMessagesError):
                log.error("context backfill failed: %s", resp.message)
                if not events:
                    return
                break
            events.extend(resp.chunk)
            end = getattr(resp, "end", None)
            if (not resp.chunk or not isinstance(end, str) or end == token
                    or sum(isinstance(e, RoomMessageText | RoomMessageAudio) for e in events) >= window):
                break
            token = end
        n = self.seed_context(events)
        log.info("%s: context seeded with %d room messages", self.cfg.localpart, n)

    async def join_pending_invites(self) -> None:
        """Invites that arrived before this start sit in the first sync; the
        callback never sees them, so they are handled here once."""
        for room_id, room in list(self.client.invited_rooms.items()):
            inviter = getattr(room, "inviter", None)
            if inviter and should_join_invite(room_id, inviter, self.cfg, self._live_private_room()):
                log.info("joining %s (pending invite from owner)", room_id)
                if await self.join_room(room_id) and room_id != self.cfg.room_id:
                    await self._move_private_room(room_id)
            else:
                log.info("ignored: pending invite to %s from %s", room_id, inviter)
                await self.client.room_leave(room_id)

    async def on_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        try:
            if event.state_key != self.cfg.user_id or event.membership != "invite":
                return
            if should_join_invite(room.room_id, event.sender, self.cfg, self._live_private_room()):
                log.info("joining %s (invited by owner)", room.room_id)
                if await self.join_room(room.room_id) and room.room_id != self.cfg.room_id:
                    await self._move_private_room(room.room_id)
            else:
                log.info("ignored: invite to %s from %s", room.room_id, event.sender)
                await self.client.room_leave(room.room_id)
        except Exception:
            log.exception("invite handler failed (bot keeps running)")

    async def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        try:
            if not self.started:
                return  # first-sync backlog: never replay history
            if self.private_room is not None and room.room_id == self.private_room:
                self.on_private(event)  # v5.6: the private chat — outside Agora's turn-taking
                return
            if room.room_id == self.cfg.room_id:
                event = self._heard(event)  # v5.2: Hermes's transcript of the owner's voice is the owner's line
            now_ms = int(getattr(event, "server_timestamp", 0) or time.time() * 1000)
            event_id = str(getattr(event, "event_id", "") or f"${now_ms}:{len(self.timeline)}")
            if room.room_id == self.cfg.room_id:
                # the context window sees every room message, own and the other agent's included
                speaker = self.names.get(event.sender, event.sender)
                self._add_context(speaker, event.body)
                self._archive(event_id, now_ms, "agora", "matrix", speaker, event.body)  # v5.8: every room line
                self._remember_text(event_id, event.body)
                self.timeline = [*self.timeline, (speaker, now_ms, event_id,
                                                  self._purr_in_timeline(event.sender, event.body))
                                 ][-max(self.history_n, 1):]
                if event.sender == self.cfg.owner:
                    self.last_owner = (event_id, event.body)
                self.last_activity_ms = self.clock()
                if self.cfg.can("summary") and not self._repeat_purr(self.session, speaker, event.body):
                    self.session.append((speaker, event.body))
                if len(self.session) > 2 * self.session_max:
                    self.session = self.session[-2 * self.session_max:]  # bounded even if summaries fail
                if (
                    self.cfg.can("summary")
                    and len(self.session) >= self.session_max
                    and not self._summary_lock.locked()
                    and (self.last_attempt_ms is None or self.clock() - self.last_attempt_ms >= 60_000)
                ):
                    self._spawn(self.summarize())  # timeline cap → early summary (rate-limited)
            verdict = should_handle(room.room_id, event.sender, self.cfg, self.others)
            if not verdict.handle:
                log.info("ignored: %s (room %s)", verdict.reason, room.room_id)
                return
            decision = self.decide(event.sender, event.body, event_id, now_ms)
            if decision.reason == "wave-limit":
                self.pause_until_window_frees(room.room_id, event.sender, event.body, event_id, now_ms)
                return
            if decision.reason == "owner-chose-others":
                self.maybe_fallback(room.room_id, event.body, event_id)
            if not decision.reply:
                log.info("silent: %s", decision.reason)
                return
            if decision.purr:  # v4.2: a purr is produced in code — zero tokens, no pending reply
                log.info("reply: %s (in %.1fs)", decision.reason, decision.delay_s)
                self._spawn(self.purr_later(room.room_id, decision.delay_s, event_id))
                return
            # An agent-to-agent reply carries its trigger for the fire-time re-check (R3); an answer to the owner
            # carries none. A newer trigger coalesces into the pending reply and becomes what it answers.
            trigger = event_id if event.sender != self.cfg.owner else None
            if self._reply_pending:
                if trigger is None:
                    self._owner_coalesced += 1  # the owner wrote to him again while a reply is on its way
                if self._pending_trigger is not None:
                    self._pending_trigger = trigger
                log.info("reply: %s — coalesced into the pending reply", decision.reason)
                return
            log.info("reply: %s (in %.1fs)", decision.reason, decision.delay_s)
            # scheduled, so the sync loop keeps running; context is read at fire time
            self._reply_pending = True
            self._pending_trigger = trigger
            self._spawn(self.reply_later(room.room_id, decision.delay_s))
        except Exception:
            log.exception("message handler failed (bot keeps running)")

    # --- v5.6: the private chat with the owner --------------------------------------------------------------------
    def _set_private_room(self, room_id: str) -> None:
        state = load_private_state(self.private_file, local_now(self.clock(), self.tz).date().isoformat())
        state.room = room_id
        save_private_state(self.private_file, state)
        self.private_room = room_id
        log.info("private chat: room joined")

    def _members(self) -> dict:
        return {rid: list(getattr(r, "users", {}) or {}) for rid, r in (getattr(self.client, "rooms", {}) or {}).items()}

    def _live_private_room(self) -> str | None:
        """The stored private room while the owner is still in it — else None, so a new invite of his replaces it
        (v5.6 review #2)."""
        return live_room(self.private_room, self._members(), self.cfg.owner) if self.private_room else None

    async def _move_private_room(self, room_id: str) -> None:
        """Joined the owner's private room: store it; a stale one he left is left too."""
        old = self.private_room
        self._set_private_room(room_id)
        if old and old != room_id:
            self.private_history = []
            log.info("private chat: moved to a new room (the owner left the old one)")
            try:
                await self.client.room_leave(old)
            except Exception:  # noqa: BLE001 — leaving the stale room is a courtesy
                log.warning("private chat: leaving the old room failed")

    async def start_private(self, from_token: str | None) -> None:
        """At start: the private room (the stored one, or rediscovered from the joined rooms) and its last lines as
        the private history — never Agora's."""
        if self.private_room is None:
            found = rediscover(self._members(), self.cfg.room_id, self.cfg.user_id, self.cfg.owner)
            if found is None:
                return
            self._set_private_room(found)
            log.info("private chat: rediscovered")
        resp = await self.client.room_messages(self.private_room, start=from_token, direction=MessageDirection.back,
                                               limit=max(self.history_n, 1))
        if isinstance(resp, RoomMessagesError):
            log.warning("private chat: history unreadable (starting without it)")
            return
        lines, last = [], None
        for e in reversed(resp.chunk):
            if isinstance(e, RoomMessageText) and not is_edit(e) and e.sender in (self.cfg.owner, self.cfg.user_id):
                speaker = "Ich" if e.sender == self.cfg.owner else self.cfg.name
                body = BACKUP_MARK_RE.sub("", e.body) if speaker == self.cfg.name else e.body  # v5.15, v5.21
                lines.append((speaker, body))
                last = int(getattr(e, "server_timestamp", 0) or 0) or last
                # v5.8 review #1: a line sent while she was down is archived before the archive seeds her history
                self._archive(str(getattr(e, "event_id", "")) or f"private:{last}", last or 0, "private", "matrix",
                              speaker, body)
        self.private_history = lines[-max(self.history_n, 1):]
        self.last_private_ms = last
        log.info("private chat: %d lines of history", len(self.private_history))

    def on_private(self, event) -> None:
        """A message in the private room: the owner's is answered — no wave, no roll — and joins the one memory,
        labelled; anything else is ignored. Never a word in a log."""
        verdict = should_handle(self.private_room or "", event.sender, self.cfg, self.others, self.private_room)
        if not verdict.handle:
            if verdict.reason != "own-message":
                log.info("ignored: %s (private chat)", verdict.reason)
            return
        if is_edit(event):
            log.info("ignored: edit (private chat)")
            return
        self.private_line(event.body, int(getattr(event, "server_timestamp", 0) or self.clock()), "matrix",
                          str(getattr(event, "event_id", "")) or None)

    def private_line(self, body: str, ts_ms: int, channel: str, key: str | None = None) -> None:
        """v5.7 — the owner's line from either door (`matrix` / `telegram`): one history, one memory, labelled; the
        answer goes back to this door, and it is remembered as the one he used last. v5.8: archived by its `key`."""
        self.private_history = append_history(self.private_history, "Ich", body, max(self.history_n, 1))
        key = key or f"ich:{channel}:{ts_ms}"
        self._archive(key, ts_ms, "private", channel, "Ich", body)
        self._unanswered.append((key, body))  # v5.13
        self.last_private_ms = self._his_last_ms = ts_ms
        self.last_activity_ms = self.clock()  # a private talk is a conversation too: no summary mid-way
        if self.cfg.can("summary"):
            self.session.append((private_label("Ich"), body))
        self.private_channel = channel
        state = load_private_state(self.private_file, local_now(self.clock(), self.tz).date().isoformat())
        if state.last_channel != channel:
            state.last_channel = channel
            save_private_state(self.private_file, state)
        if self._private_pending:
            self._private_again = True
            log.info("private: coalesced into the pending answer")
            return
        self._private_pending = True
        delay = 1.0 + self.rng() * max(self.reply_delay_s - 1.0, 0.0)
        self._private_delay_ms = round(delay * 1000)  # v5.22: the deliberate pause in his wait
        log.info("private: answering (in %.1fs)", delay)
        self._spawn(self.private_later(delay))

    async def private_later(self, delay_s: float) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            for _ in range(3):  # a message that arrived while answering gets its own pass
                self._private_again = False
                await self.private_reply()
                if not self._private_again:
                    return
                log.info("private: the owner wrote again while answering — answering it")
        except Exception:
            log.exception("private answer failed (bot keeps running)")
        finally:
            self._private_pending = False

    async def private_reply(self, nudge: bool = False, channel: str | None = None) -> bool:
        """Typing on → her own prompt with the private brief (or the writing-first rule) and the private history →
        a line through the door (v5.7: the Element room, voiced under the speakers' rules, or her Telegram bot, a
        voice note and then the text) → typing off in a finally."""
        room = self.private_room
        door = pick_door(channel or self.private_channel, room is not None, self.telegram_open)
        if door is None:
            return False
        action = None
        # v5.22: his latest line's own time — never hers (code review #3: her answer moves `last_private_ms`)
        asked_ms = None if nudge else self._his_last_ms
        delay_ms, self._private_delay_ms = (None if nudge else self._private_delay_ms), 0
        self._pending_shot = None
        self._offer_photo = self._photo_open(door)  # v5.17: her photo skill, for Gemini's prompt only
        self._offer_video = self._video_kinds(door)  # v5.18: the videos she may send now, for Gemini's prompt only
        kind = "private_nudge" if nudge else "private"
        LAST_BLOCK.set(None)
        LAST_SILENCE.set(None)
        by = None
        try:
            if door == "matrix":
                await self.client.room_typing(room, True)
            else:
                act = "record_voice" if self.tts else "typing"
                await self.telegram.send_chat_action(self.telegram_owner, act)
                action = asyncio.create_task(self._telegram_action(act))
            if self.cfg.can("today"):
                try:
                    await self.ensure_today(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("today block refresh failed (the private answer continues)")
            if self.cfg.can("mood"):  # v5.10: a new day's first private answer has its mood, as in Agora
                try:
                    await self.ensure_mood(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("mood of the day failed (the private answer continues)")
            brief = PRIVATE_NUDGE if nudge else PRIVATE_BRIEF
            if nudge and self.cfg.can("thoughts"):  # v5.12: she may share what she read or thought
                brief = f"{brief} {PRIVATE_NUDGE_THOUGHTS}"
            if self.facts_dir is not None and not nudge:  # v5.8: «запам'ятай» — a skill, never a keyword
                brief = f"{brief}\n\n{REMEMBER_SKILL}"
            # v5.15.1 (the owner): how she says it this time, drawn anew — live words or none, a turn of a real chat,
            # an open ending, where a voice tag may go, and what she has been repeating
            her_lines = [t for s, t in self.private_history if s == self.cfg.name]
            brief = f"{brief}\n\n{style_line(self.rng, her_lines, self.cfg.can('emotion'))}"
            seen = list(self._unanswered)  # v5.13 review #2: the lines this call answers — never one that comes later
            text, by = await self._private_text(brief, nudge, seen)
            shot, self._pending_shot = (self._pending_shot if by == "gemini" else None), None
            self._offer_photo, self._offer_video = False, ()
            if shot is not None and not shot.description:  # code review v5.21 #1: a photo line that names nothing
                log.info("photo: dropped (no description)")
                shot = None
                if text is not None:  # her words may promise it: never «дивись» with nothing
                    again, _ = await self._gemini_text(f"{brief}\n\n{PHOTO_FAILED}", kind)
                    self._pending_shot = None
                    if again is not None:
                        text = again
            made: Made | None = None
            video: Shot | None = None
            if shot is not None and shot.kind in VIDEO_KINDS:  # v5.18: her video goes after her answer, never a photo
                why = self._video_closed(door, shot.kind)
                if why:
                    log.info("video: dropped (%s)", why)
                elif text is not None:
                    video = shot
                shot = None
            if text is not None and shot is not None:  # v5.17: her photo, made before anything is sent
                why = self._photo_closed(door)
                if why:
                    log.info("photo: dropped (%s)", why)
                else:
                    if action is not None:
                        action.cancel()
                    await self.telegram.send_chat_action(self.telegram_owner, "upload_photo")  # 11–40 s to make
                    action = asyncio.create_task(self._telegram_action("upload_photo"))
                    made = await self._make_photo(shot)
                    if made.why != "ok":  # never «дивись» with nothing: her answer once more, without the photo
                        log.warning("photo: %s — her answer without it", made.why)
                        made = None
                        again, _ = await self._gemini_text(f"{brief}\n\n{PHOTO_FAILED}", kind)
                        self._pending_shot = None
                        if again is not None:
                            text = again
            if text is None:
                if not nudge and door == "telegram":  # v5.22: never a bare silence to him
                    await self._say_silence(silence_line(self.cfg.name, LAST_BLOCK.get(), LAST_SILENCE.get(), by,
                                                         self.backup_open()))
                return False
            sent_id = None
            # v5.15: the owner sees which network wrote it; v5.21: and until when the backup answers
            mark = backup_mark(load_route(self.route_file), self.clock(), self.tz) if by == "backup" else None
            if door == "matrix":
                sent_id = await self.send_line(room, text, f"private:{self.clock()}", mark=mark)
            elif not await self.send_telegram(text, mark=mark, photo=made,  # never said: not in the history
                                              hold_voice_s=self.video_note_max_s if video and video.kind == "note"
                                              else None):  # v5.18: her voice held for her кружечок
                log.warning("private: not delivered (telegram)")
                return False
            if made is not None and self.photo_sent:  # v5.17: kept as a file and named in her line
                self.keep_photo(made)
                log.info("photo: sent (%s, telegram)", shot.kind)
                text = photo_note(str(text), shot)
            self.private_history = append_history(self.private_history, self.cfg.name, text, max(self.history_n, 1))
            self.last_private_ms = self.clock()
            self._unanswered = [u for u in self._unanswered if u not in seen]  # v5.13: answered (review #2)
            self._own_seq += 1
            key = sent_id or f"own:{door}:{self.clock()}:{self._own_seq}"
            self._archive(key, self.clock(), "private", door, self.cfg.name, text)
            self.record_answer("private", door, "none" if nudge else "owner", asked_ms, delay_ms, by,  # v5.22
                               [p for p, on in (("voice", self.voice_sent),
                                                ("photo", made is not None and self.photo_sent)) if on])
            if self.cfg.can("summary"):
                self.session.append((private_label(self.cfg.name), text))
            if video is not None:  # v5.18: made and sent in the background — her next answer never waits for it
                if video.kind == "note" and self.voice_held is None:
                    log.info("video: dropped (%s)", self.voice_hold_miss or "no voice")
                else:
                    self._video_busy = True
                    self._spawn(self._video_after(video, self.voice_held if video.kind == "note" else None, brief))
            if by == "backup":  # v5.21: whatever the backup says is `blocked`, for good — read by the backup alone
                self.close_lines([(self.cfg.name, str(text))])
                if self.archive is not None:
                    try:
                        self.archive.mark([key], "blocked")
                    except Exception as exc:  # noqa: BLE001
                        log.error("archive: her line was not marked (%s)", type(exc).__name__)
            log.info("private: %s%s%s", "wrote first" if nudge else "answered", " (telegram)" if door == "telegram" else "",
                     " by the backup" if by == "backup" else "")
            return True
        except Exception as exc:
            if not nudge and door == "telegram":  # v5.22: a failed answer is said too, then logged by the caller
                await self._say_silence(f"⚙️ {self.cfg.name} пропустила відповідь: помилка ({type(exc).__name__})")
            raise
        finally:
            if action is not None:
                action.cancel()
            if door == "matrix":
                await self.client.room_typing(room, False)

    async def _say_silence(self, line: str) -> None:
        """v5.22 (the owner, 2026-11-02: «я не хочу щоб було просто тиша у відповідь … бо не зрозуміло чи вона взагалі
        працює») — her answer to him in Telegram came to nothing: one ⚙️ line why (`silence_line`), sent as text,
        never voiced; never in her history, the archive or a prompt; a failed send is only logged."""
        log.info("private: the silence said to him")
        try:
            if not await self.telegram.send_message(self.telegram_owner, line):
                log.warning("telegram: the silence line was not delivered")
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram: the silence line was not delivered (%s)", type(exc).__name__)

    # --- v5.14: the route of her private answer — Gemini, or the backup's window after a block --------------------------
    @property
    def route_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.route.json"

    def route_step(self, outcome: str):
        """The route after an outcome (`block`, `gemini`, `backup`, `pin:gemini`, `pin:backup` — v5.21's
        `agents/route.py` `step`), saved — read fresh each time, so a Telegram command in between is never lost. The
        new route."""
        now_ms = self.clock()
        route = route_after(load_route(self.route_file), now_ms, outcome, self.fallback_window_s,
                            self.fallback_hour_max, self.fallback_lock_s, day_bounds(now_ms, self.tz)[0])
        try:
            save_route(self.route_file, route)
        except OSError as exc:
            log.error("route: not saved (%s)", type(exc).__name__)
        return route

    async def _gemini_private_prompt(self, brief: str) -> str:
        """Her private instruction for Gemini: the history, the recall and the facts without a closed line (v5.14)."""
        recalled = agora_now = None
        if self._offer_photo:  # v5.17: her photo skill — Gemini's alone, never the backup's
            brief = f"{brief}\n\n{PHOTO_SKILL}"
        if self._offer_video:  # v5.18: her video skill, the same way
            brief = f"{brief}\n\n{video_skill(self._offer_video)}"
        facts = self.facts_now()  # v5.8 review #6: mirrored before the recall, so a deleted fact is not recalled
        if self.archive is not None:  # v5.8: alone with him she recalls both places and knows Agora today
            query = next((t for s, t in reversed(self.gemini_history()) if s == "Ich"), "")  # v5.14: open only
            recalled = await self.recall_section(query, self.private_places,
                                                 set(self.private_history) | set(self.gemini_history()))
            agora_now = self.agora_now_section()
        return self.build_prompt(private=brief, recalled=recalled, agora_now=agora_now, facts=facts, talk=True)

    async def _backup_private_prompt(self, brief: str) -> tuple[str, list[tuple[str, str]]]:
        """Her private instruction and history for the backup (v5.21, the owner, 2026-11-02: a `blocked` line is the
        backup's only as history, within `FALLBACK_HISTORY_N` (300) lines of every mark): the open facts, the recall of
        open lines by words only (its query never goes to Gemini's embeddings), fitted to `FALLBACK_CONTEXT` — the month
        digests, the week digests, «Agora today», then the oldest lines (never fewer than 10) left out."""
        history = [line for line in self.private_history[-max(self.fallback_history_n, 1):] if line[1]]
        facts = self.facts_now()
        recalled = agora_now = None
        if self.archive is not None:
            query = next((t for s, t in reversed(history) if s == "Ich"), "")
            recalled = await self.recall_section(query, self.private_places, set(history), meaning=False)
            agora_now = self.agora_now_section()
        built: dict[tuple[str, ...], str] = {}

        def instruction(cuts: tuple[str, ...]) -> str:
            if cuts not in built:
                skip = frozenset().union(*(CUT_LAYERS.get(c, frozenset()) for c in cuts))
                built[cuts] = self.build_prompt(private=brief, recalled=recalled, facts=facts, skip_layers=skip,
                                                agora_now=None if "agora" in cuts else agora_now)
            return built[cuts]

        cuts, n = fit_budget(lambda c, k: len(instruction(c)) + len(build_transcript(history[-k:])),
                             self.fallback_context, len(history))
        if cuts or n < len(history):
            log.info("backup: the prompt fitted (left out: %s; history %d of %d)", "+".join(cuts) or "nothing", n,
                     len(history))
        skip = frozenset().union(*(CUT_LAYERS.get(c, frozenset()) for c in cuts))  # v5.22: built once more, as sent,
        return self.build_prompt(private=brief, recalled=recalled, facts=facts, skip_layers=skip,  # for its parts
                                 agora_now=None if "agora" in cuts else agora_now), history[-n:]

    async def _backup_text(self, brief: str, kind: str):
        prompt, lines = await self._backup_private_prompt(brief)
        return await self._compose(prompt, lines=lines, kind=kind, responder=self.fallback_responder)

    async def _gemini_text(self, brief: str, kind: str):
        """Gemini's line, and its block or refusal (v5.13's `LAST_BLOCK`, read in this task) when it gave none."""
        LAST_BLOCK.set(None)
        shots: list = []
        prompt = await self._gemini_private_prompt(brief)
        lines = [entry for _, entry in self.gemini_history_shown()]
        text = await self._compose(prompt, lines=lines, kind=kind, shots=shots)
        if text is not None and shots:  # v5.17: the photo her line asked for, made once her answer is chosen
            self._pending_shot = shots[-1]
        block = LAST_BLOCK.get() if text is None else None
        self.keep_prompt(prompt, lines, block, text is not None)
        return text, block

    def keep_prompt(self, system: str, lines: list, block, answered: bool) -> None:
        """v5.20 (the owner, 2026-11-02: «в панелі просто виводь останній промпт») — her last private prompt to Gemini,
        whole, with what came of it, in `state/<name>.prompt.json` (0600, replaced each time) for the panel's Prompt
        tab; never in a log, and a failed write never stops an answer."""
        data = {"at": local_now(self.clock(), self.tz).isoformat(timespec="seconds"),
                "model": getattr(self.llm, "reply_model", ""),
                "outcome": "answered" if answered else "blocked" if block else "silent",
                "block": list(block) if block else None, "system": system, "transcript": build_transcript(lines)}
        path = self.memory_file.parent / f"{self.cfg.localpart}.prompt.json"
        try:
            tmp = path.with_suffix(".json.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as exc:
            log.error("private: the prompt was not kept (%s)", type(exc).__name__)

    async def _private_text(self, brief: str, nudge: bool, seen: list) -> tuple[str | None, str]:
        """(her line or None, who wrote it: `gemini` | `backup`). Without the backup (no model, or v5.22's switch
        `FALLBACK_ROUTE` off), v5.13: a block or a refusal closes his lines and is silence. v5.21 (the owner, 2026-11-02: no judge — Gemini's own filter decides, at once): in
        Gemini's mode a block (the prompt stage, the answer stage, or her caught refusal) makes his unanswered lines
        `blocked`, opens the backup mode (`agents/route.py` `step`) and the backup answers; in the backup mode (5 minutes,
        an hour after more than `FALLBACK_HOUR_MAX` blocks in an hour, or by hand until `/gemini`) Gemini is never asked,
        his lines are `blocked` and the backup answers. Her line through the backup is made `blocked` once it is sent."""
        kind = "private_nudge" if nudge else "private"
        if not self.backup_open():
            text, block = await self._gemini_text(brief, kind)
            if block is not None and not nudge:  # v5.13: what Gemini refused never reaches it again
                self.mark_unanswered(block[0], seen)
            return text, "gemini"
        if route_mode(load_route(self.route_file), self.clock()) == "backup":
            log.info("private: route=backup — the backup answers")
            if not nudge:
                self.mark_unanswered("backup", seen)
            text = await self._backup_text(brief, kind)
            if text is not None:
                self.route_step("backup")
            return text, "backup"
        text, block = await self._gemini_text(brief, kind)
        if text is not None:
            self.route_step("gemini")
            return text, "gemini"
        if block is None:
            return None, "gemini"  # silence, as ever: not a block
        self.route_step("block")
        if not nudge:
            self.mark_unanswered(block[0], seen)
        log.warning("private: route=gemini — a %s, the backup answers", block[0])
        text = await self._backup_text(brief, kind)
        if text is not None:
            self.route_step("backup")
        return text, "backup"

    def gemini_history(self) -> list[tuple[str, str]]:
        """v5.14 — her private history as Gemini may read it, never a closed line (conservatively: a same text open
        elsewhere is left out too). v5.15 (the owner, 2026-10-30): the last `HISTORY_N` lines open to Gemini, read from
        the archive — her history holds the last `HISTORY_N` of every line, the backup's view, so a long talk through
        the backup left Gemini none; without the archive (or when it fails), her history without the closed lines."""
        return [entry for _, entry in self.gemini_history_keyed()]

    def gemini_history_keyed(self) -> list[tuple[str | None, tuple[str, str]]]:
        """`gemini_history`, each line with its probe id (`line:<key>`; v5.16) — None for one without a key (her own
        history, when the archive is missing or fails)."""
        lines = self._gemini_lines()
        if lines is None:
            return [(None, line) for line in self.private_history if line not in self._closed]
        return [(f"line:{line.key}", (line.speaker, history_entry(line.text))) for line in lines]

    def _gemini_lines(self) -> list | None:
        """The archive's last `HISTORY_N` private lines open to Gemini — None without the archive or when it fails."""
        if self.archive is None:
            return None
        try:
            lines = self.archive.latest("private", max(self.history_n, 1))
        except Exception as exc:  # noqa: BLE001
            log.error("archive: Gemini's history was not read (%s) — her own", type(exc).__name__)
            return None
        lines = [line for line in lines if (line.speaker, line.text) not in self._closed]
        if self.private_history_n > 0:  # the owner's cap — never below his lines since her last one
            unanswered = next((n for n, x in enumerate(reversed(lines)) if x.speaker == self.cfg.name), len(lines))
            lines = lines[-max(self.private_history_n, unanswered):] if lines else lines
        return lines

    def gemini_history_shown(self) -> list[tuple[str | None, tuple[str, str]]]:
        """`gemini_history_keyed` as her prompt shows it (the owner, 2026-11-01): a time line (`history_times`, no id,
        no name) before the first line and after every long pause — the closed days leave a gap, and Wednesday's talk
        right before Sunday's read as tonight's."""
        lines = self._gemini_lines()
        if lines is None:
            return self.gemini_history_keyed()
        times = history_times([line.ts_ms for line in lines], local_now(self.clock(), self.tz), self.tz)
        out: list[tuple[str | None, tuple[str, str]]] = []
        for i, line in enumerate(lines):
            if i in times:
                out.append((None, ("", times[i])))
            out.append((f"line:{line.key}", (line.speaker, history_entry(line.text))))
        return out

    def talk_now(self, now) -> str | None:
        """v5.20 — the summaries of her private chat older than the first line of Gemini's history window (`talk_section`);
        None without the archive or when it fails."""
        if self.archive is None:
            return None
        try:
            lines = self._gemini_lines() or []
            if self.talk_prompt_words <= 0:  # the owner's switch: no summaries in her prompt
                return None
            return talk_section(self.archive.talk_rows(), lines[0].ts_ms if lines else self.clock(), now, self.tz,
                                self.talk_prompt_words)
        except Exception as exc:  # noqa: BLE001
            log.error("talk: the summaries were not read (%s)", type(exc).__name__)
            return None

    def closed_in_history(self) -> int:
        """How many lines of her history (the backup's view) Gemini's history leaves out — for the log only."""
        open_lines = set(self.gemini_history())
        return sum(1 for line in self.private_history if line not in open_lines)

    def mark_unanswered(self, stage: str, lines: list[tuple[str, str]] | None = None, mark: str = "blocked") -> int:
        """v5.13, v5.14 — Gemini blocked or refused her answer to the owner's `lines` ((key, text); all unanswered by
        default), or the backup answers them: they are marked `blocked` in her archive (v5.21: for good), stay in
        her history for the backup but are closed to Gemini, and leave the session — so no later Gemini call (an
        answer, the recall, the reflection, the summary, the facts) gets them. A line that came while she composed
        stays (v5.13 review #2). How many; the log names the stage and the count, never a text."""
        lines = list(self._unanswered if lines is None else lines)
        self._unanswered = [u for u in self._unanswered if u not in lines]
        if not lines:
            return 0
        self.close_lines([("Ich", text) for _, text in lines])
        marked = 0
        if self.archive is not None:
            try:
                marked = self.archive.mark([k for k, _ in lines], mark)
            except Exception as exc:  # noqa: BLE001
                log.error("archive: the lines were not marked (%s)", type(exc).__name__)
        log.warning("private: %d line(s) marked %s after a %s", marked, mark, stage)
        return marked

    def close_lines(self, lines: list[tuple[str, str]]) -> None:
        """v5.14 — these (speaker, text) lines of her private chat are closed to Gemini: kept in her history for the
        backup, out of the session (its summary, its facts and the day journal are Gemini's). Closed as the history
        holds them too: a long line is cut there (v5.14 review #1)."""
        for speaker, text in lines:
            self._closed.update({(speaker, text), (speaker, history_entry(text))})
            _drop_last(self.session, (private_label(speaker), text))

    async def maybe_private_nudge(self) -> bool:
        """After a long private silence, in the owner's hours, under the day's cap: one line of her own — never
        while an answer is on its way, never before they have talked there, never at once after a restart."""
        if (not (self.started and self.cfg.can("private") and (self.private_room or self.telegram_open))
                or self._private_pending):
            return False
        if not self.private_history and not (self.archive is not None and self.last_private_ms):
            return False  # never before they have talked (v5.8: the archive remembers a talk the RAM lost)
        now_ms = self.clock()
        now = local_now(now_ms, self.tz)
        state = load_private_state(self.private_file, now.date().isoformat())
        state.room = state.room or self.private_room
        last = max([t for t in (self.last_private_ms, self.started_ms) if t is not None], default=None)
        if not private_nudge_due(now_ms, now, last, state, self.private_idle_ms, self.private_per_day,
                                 self.private_hours):
            return False
        self._private_pending = True
        try:
            state.last_ms = now_ms  # every attempt spaces the next one; only a sent line counts
            save_private_state(self.private_file, state)
            # v5.7: his last door — or the one the owner chose (v5.8.2); a closed door falls back to the other
            door = state.last_channel if self.private_first_door == "last" else self.private_first_door
            sent = await self.private_reply(nudge=True, channel=door)
            if sent:  # read again: the owner may have changed door, or the room moved, while she wrote (review #1)
                fresh = load_private_state(self.private_file, now.date().isoformat())
                fresh.count += 1
                fresh.sent_ms = now_ms
                save_private_state(self.private_file, fresh)
            return sent
        finally:
            again = self._private_again
            self._private_pending = False
            if again:  # the owner wrote while she was writing first: answer him (v5.6 review #1)
                self._private_pending = True
                self._spawn(self.private_later(0))

    # --- v5.8: the archive (`recall`) -------------------------------------------------------------------------------
    def _archive(self, key: str, ts_ms: int, place: str, channel: str, speaker: str, text: str) -> None:
        """One line into the archive, once by its key; a failure is logged by its type and never blocks a line."""
        if self.archive is None:
            return
        try:
            self.archive.append(key, ts_ms, place, channel, speaker, text)
        except Exception as exc:  # noqa: BLE001
            log.error("archive: a line was not kept (%s)", type(exc).__name__)

    async def embed_tick(self, batch: int = EMBED_BATCH) -> int:
        """The idle watcher's share: embed up to `batch` lines that have no vector yet; a failure waits for the next
        tick. The number embedded."""
        embed = getattr(self.llm, "embed", None)
        if self.archive is None or embed is None:
            return 0
        pending = self.archive.unembedded(batch)
        if not pending:
            return 0
        vectors = await embed([text for _, text in pending])
        if not vectors:
            return 0
        self.archive.set_embeddings(zip([i for i, _ in pending], vectors, strict=True))
        return len(pending)

    async def archive_backfill(self, from_token: str) -> None:
        """The archive's first fill (an empty archive at start): Agora's last `ARCHIVE_AGORA_LINES` lines and the whole
        private room (bounded), read back from the homeserver; Telegram keeps no history to fetch."""
        n = await self._archive_room(self.cfg.room_id, "agora", from_token, ARCHIVE_AGORA_LINES)
        log.info("archive: %d Agora lines from the homeserver", n)
        if self.private_room is not None:
            n = await self._archive_room(self.private_room, "private", from_token, ARCHIVE_PRIVATE_EVENTS)
            log.info("archive: %d private lines from the homeserver", n)
        if self.telegram is not None:
            log.info("archive: Telegram keeps no history to fetch")

    async def _archive_room(self, room_id: str, place: str, from_token: str, cap: int) -> int:
        events: list = []
        token = from_token
        while len(events) < cap:
            resp = await self.client.room_messages(room_id, start=token, direction=MessageDirection.back,
                                                   limit=BACKFILL_PAGE)
            if isinstance(resp, RoomMessagesError):
                log.error("archive: the %s history was not readable", place)
                break
            events.extend(resp.chunk)
            end = getattr(resp, "end", None)
            if not resp.chunk or not isinstance(end, str) or end == token:
                break
            token = end
        oldest_first = list(reversed(events))
        if place == "agora":
            lines = [(e, self.names.get(e.sender, e.sender)) for e in self._lines(oldest_first)][-cap:]
        else:
            lines = [(e, "Ich" if e.sender == self.cfg.owner else self.cfg.name) for e in oldest_first
                     if isinstance(e, RoomMessageText) and not is_edit(e) and e.sender in (self.cfg.owner, self.cfg.user_id)]
        kept = 0
        for e, speaker in lines:
            key = str(getattr(e, "event_id", "")) or f"{place}:{getattr(e, 'server_timestamp', 0)}"
            if self.archive.append(key, int(getattr(e, "server_timestamp", 0) or 0), place, "matrix", speaker, e.body):
                kept += 1
        return kept

    def seed_private_from_archive(self) -> None:
        """At start (v5.7 review #5): the private history from the archive's last private lines, both doors — so a
        Telegram line survives a restart — and the time of the last one."""
        if self.archive is None:
            return
        try:  # v5.14: every mark — the backup reads them; the closed ones are kept apart for Gemini
            lines = self.archive.latest("private", max(self.history_n, 1), gemini=False)
        except Exception as exc:  # noqa: BLE001 — v5.8 review #4: the homeserver's history stays
            log.error("archive: the private history was not read (%s)", type(exc).__name__)
            return
        lines = [line for line in lines if line.text]  # v5.21: a `blocked` line emptied after a day is gone
        if not lines:
            return
        self.private_history = [(line.speaker, line.text) for line in lines]
        self._closed = {(line.speaker, line.text) for line in lines if line.mark in GEMINI_CLOSED}
        self.last_private_ms = max(self.last_private_ms or 0, lines[-1].ts_ms)
        log.info("private chat: %d lines of history from the archive", len(lines))

    async def recall_section(self, query: str, places: tuple[str, ...], exclude: set,
                             gemini: bool = True, meaning: bool = True) -> str | None:
        """What she recalls before an answer: the message she answers is the query — the word search and (when its
        embedding comes back) the meaning search within `places`, fused; the best `RECALL_N` lines not already in the
        prompt's window, each with its neighbours. `gemini=False` reads closed lines too; `meaning=False` is words
        only (v5.21: the backup's recall — open lines only, and its query never goes to Gemini's embeddings). A failure
        is no section, never a blocked answer."""
        if self.archive is None or self.recall_n <= 0 or not (query or "").strip():
            return None
        try:
            word_ids = self.archive.search_words(query, places, gemini=gemini)
            meaning_ids: list[int] = []
            try:  # v5.8 review #10: the meaning search fails on its own — the words' results stay
                # v5.14: the backup's recall is words only — its query never goes to Gemini's embeddings
                embed = getattr(self.llm, "embed", None) if gemini and meaning else None
                vector = await embed([query], task="RETRIEVAL_QUERY") if embed else None
                if vector:
                    ids, matrix = self.archive.vectors(places)
                    meaning_ids = cosine_top(vector[0], ids, matrix)
            except Exception as exc:  # noqa: BLE001
                log.error("recall: the meaning search failed (%s) — words only", type(exc).__name__)
            ranked = fuse(word_ids, meaning_ids)
            picked = pick_recall(ranked, self.archive.lines(ranked[:2 * CANDIDATES], gemini=gemini), exclude,
                                 self.recall_n)
            groups, seen = [], set()
            for line in sorted(picked, key=lambda x: (x.ts_ms, x.id)):
                group = [n for n in (self.archive.around(line, 1, gemini=gemini)
                                     if line.place not in ("facts", *THOUGHT_PLACES)
                                     else [line])  # a fact or a thought is recalled alone
                         if n.id not in seen and (n.speaker, n.text) not in exclude]
                seen.update(n.id for n in group)
                groups.append(group)
            if picked:
                log.info("recall: %d lines (%s)", len(picked), "+".join(places))
            return render_recalled(groups, self.tz, local_now(self.clock(), self.tz))
        except Exception as exc:  # noqa: BLE001
            log.error("recall failed (%s) — answering without it", type(exc).__name__)
            return None

    @property
    def private_places(self) -> tuple[str, ...]:
        """What her private recall searches: both rooms and her facts; v5.12: all her thoughts."""
        return ("agora", "private", "facts", *(THOUGHT_PLACES if self.cfg.can("thoughts") else ()))

    @property
    def agora_places(self) -> tuple[str, ...]:
        """What her Agora recall searches: Agora only; v5.12: and her thoughts but those on the private chat."""
        return ("agora", "thought") if self.cfg.can("thoughts") else ("agora",)

    def agora_now_section(self) -> str | None:
        """Agora's latest `PRIVATE_AGORA_N` lines of today (local), for the private chat."""
        if self.archive is None or self.private_agora_n <= 0:
            return None
        now = local_now(self.clock(), self.tz)
        start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        try:
            return render_agora_now(self.archive.latest("agora", self.private_agora_n, since_ms=start), self.tz)
        except Exception as exc:  # noqa: BLE001 — v5.8 review #13: no section, never a lost answer
            log.error("archive: Agora today was not read (%s) — answering without it", type(exc).__name__)
            return None

    # --- v5.8: facts about the owner (`facts`) -----------------------------------------------------------------------
    def facts_now(self, gemini: bool = True) -> str | None:
        """Her facts about the owner, read from disk (a panel edit counts at the next answer), mirrored into the
        archive (with their marks, v5.14) when they changed, and rendered for her private prompt — for Gemini without
        a closed fact."""
        if self.facts_dir is None:
            return None
        facts = load_facts(self.facts_dir)
        seen = tuple((f.id, f.text, f.mark) for f in facts)
        if self.archive is not None and seen != self._facts_seen:
            try:
                self.archive.sync_facts(seen, self.clock())
                self._facts_seen = seen
            except Exception as exc:  # noqa: BLE001
                log.error("archive: the facts were not mirrored (%s)", type(exc).__name__)
        return facts_section(facts, self.facts_in_prompt, self.fact_max_chars, gemini)

    def remember(self, text: str, source: str, pin: int = 1) -> bool:
        """One fact kept — never its words in a log (v5.21: never one the backup asked for)."""
        if self.facts_dir is None:
            return False
        why = off_limits(text)  # v5.8 review #3: an asked fact is the model's words, so the same filter holds
        if why is not None:
            log.info("facts: not kept (%s, %s)", why, source)
            return False
        today = local_now(self.clock(), self.tz).date().isoformat()
        kept = add_fact(self.facts_dir, text, pin, source, today, self.facts_max, self.fact_max_chars) is not None
        log.info("facts: %s (%s)", "kept one" if kept else "not kept (empty, too long, known or full)", source)
        return kept

    async def maybe_update_facts(self) -> bool:
        """AGORA-116 — the panel's «Update now» (`state/<name>.facts.request`): under the summary lock, the extraction
        over the session lines not yet read for facts, then the request is gone. A summary's extraction later skips
        what this one read. Whether there was a request."""
        if self.facts_request is None or not self.facts_request.exists():
            return False
        try:
            async with self._summary_lock:
                snapshot = list(self.session)
                fresh = snapshot[min(self._facts_from, len(snapshot)):]
                if not any(who.startswith("Ich") for who, _ in fresh):
                    log.info("facts: nothing new from Ich to learn")
                    self._facts_from = len(snapshot)
                elif await self.extract_facts(fresh):  # v5.8 review #8: read only once the answer was valid — a
                    self._facts_from = len(snapshot)    # failure leaves the lines to the session's end
        finally:
            self.facts_request.unlink(missing_ok=True)
        return True

    async def extract_facts(self, session: list[tuple[str, str]]) -> bool:
        """At a session's end: one call (GEMINI_MODEL, kind `facts`) reads the session and what she knows, and
        returns new facts and the replacements of stale ones — validated, or nothing changes. Only a session in which
        the owner spoke. Whether the lines are done with (a valid answer, or nothing to learn)."""
        if not any(who.startswith("Ich") for who, _ in session):
            return True  # nothing to learn: done
        held = [f for f in load_facts(self.facts_dir) if f.mark not in CLOSED_MARKS]  # v5.14: never a closed one
        system, contents = extraction_request(self.cfg.name, session, held, self.fact_max_chars)
        raw = await self.llm.generate(contents, system, max_output_tokens=1024, kind="facts")
        parsed = parse_extraction(raw or "", {f.id for f in held}, self.fact_max_chars)
        if parsed is None:
            log.error("facts: the extraction gave no valid answer — nothing changed")
            return False
        adds, replaces = parsed
        adds = [(t, p) for t, p in adds if off_limits(t) is None]  # she believes she is human: no fact about AI, agents,
        replaces = [(i, t) for i, t in replaces if off_limits(t) is None]  # servers or his exact address (the owner)
        source = "private" if any("наодинці" in who for who, _ in session) else "agora"
        today = local_now(self.clock(), self.tz).date().isoformat()
        added = sum(add_fact(self.facts_dir, t, p, source, today, self.facts_max, self.fact_max_chars) is not None
                    for t, p in adds)
        replaced = sum(replace_fact(self.facts_dir, i, t, today, self.fact_max_chars) for i, t in replaces)
        log.info("facts: %d added, %d replaced", added, replaced)
        return True

    # --- v5.7: her Telegram bot, a second door to the private chat --------------------------------------------------
    async def telegram_poll(self) -> None:
        """Long polling from the stored offset, beside the sync. A refused token stops only this; a 429 waits as
        told; anything else backs off. The offset is saved after every batch: an update is never answered twice."""
        state = load_telegram_state(self.telegram_file)
        failures = 0
        while True:
            try:
                reply = await self.telegram.get_updates(poll_offset(state, self.clock()))
                if not reply.ok:
                    if reply.status in (401, 404):
                        log.error("telegram off: refused (HTTP %s)", reply.status)
                        self.telegram_open = False  # the door closes: Element takes every line (review #2)
                        return
                    failures += 1
                    wait = reply.retry_after if reply.status == 429 and reply.retry_after else backoff_s(failures)
                    log.warning("telegram: polling again in %ss", wait)
                    await asyncio.sleep(wait)
                    continue
                failures = 0
                if reply.result:
                    await self.on_telegram(reply.result)
                    state.offset = next_offset(reply.result, state.offset)
                    state.seen_ms = self.clock()
                    save_telegram_state(self.telegram_file, state)
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                log.exception("telegram: poll failed (bot keeps running)")
                await asyncio.sleep(backoff_s(failures))

    async def on_telegram(self, raw_updates: list) -> None:
        """A batch: only the owner's private chat; what he wrote before this start is context, never answered (the
        first-sync rule, as the Element room's backlog); a text joins the private chat, a voice note is heard first.
        Logged by reason and kind only — never an id or a word."""
        backlog = 0
        for raw in raw_updates:
            update = parse_update(raw)
            if update is None:
                log.info("ignored: malformed (telegram)")
                continue
            verdict = allowed(update, self.telegram_owner)
            if verdict.reason == "command" and (self.started_ms is None
                                                or update.date_ms >= self.started_ms // 1000 * 1000):
                await self.telegram_command(update.text)  # v5.14: his, after the start — never a line of her talk
                continue
            if not verdict.handle:
                log.info("ignored: %s (telegram %s)", verdict.reason, update.kind)
                continue
            # Telegram dates are whole seconds: the start floored too, so a line sent just after it counts (review #3)
            if self.started_ms is not None and update.date_ms < self.started_ms // 1000 * 1000:
                if update.kind == "text":
                    self.private_history = append_history(self.private_history, "Ich", update.text,
                                                          max(self.history_n, 1))
                    self._archive(f"tg:{update.update_id}", update.date_ms, "private", "telegram", "Ich", update.text)
                backlog += 1
                continue
            try:  # one bad update never replays the batch: the others would be answered twice (review #4)
                if update.kind == "voice":
                    await self.telegram_hear(update)
                else:
                    self.private_line(update.text, update.date_ms, "telegram", f"tg:{update.update_id}")
            except Exception as exc:  # noqa: BLE001
                log.error("telegram: an update failed (%s) — skipped", type(exc).__name__)
        if backlog:
            log.info("telegram: %d messages from before the start read as context", backlog)

    async def telegram_command(self, text: str) -> None:
        """v5.14 — the owner's command: `/status`, v5.21's `/gemini` (back to Gemini now: the backup mode ends and the
        hour's count is emptied) and `/backup` (the backup until `/gemini`), v5.22's `/unblock` (the pair before a
        block closed), `/purge`; anything else, the list.
        One ⚙️ service line, sent as text, never voiced; never in her history, the archive, the facts, the session or a
        prompt, and never a reset of her writing-first timer. Logged by the command's name only."""
        name = command_of(text)
        known = {n for n, _ in COMMANDS}
        if name in ("gemini", "backup") and not self.backup_open():
            answer = "⚙️ Backup вимкнено: її відповіді завжди через gemini"
        elif name in ("gemini", "backup"):
            self.route_step(f"pin:{name}")
            answer = self.status_answer()
        elif name == "status":
            answer = self.status_answer()
        elif name == "unblock":
            answer = self.unblock_answer()
        elif name == "purge":
            answer = self.purge_answer(command_args(text))
        else:
            answer = COMMAND_HELP
        log.info("telegram: command %s", name if name in known else "unknown")
        if not await self.telegram.send_message(self.telegram_owner, answer):
            log.warning("telegram: the command's answer was not delivered")

    def unblock_answer(self) -> str:
        """v5.22 (the owner, 2026-11-02: «просто закриває попередню пару до початку блоку … я руками зроблю стільки раз
        скільки хочу») — `/unblock`: the last line of his and the last line of hers that Gemini's window still holds
        (after a block every line is `blocked` already, so the pair before it) become `blocked`, for good — out of her
        prompt, her recall and the session. His line still waiting for her answer is never taken; the route is left
        as it is. Each `/unblock` closes one pair more. Speakers and times only, never a text."""
        lines = self._gemini_lines()
        if lines is None:
            return "⚙️ Архів недоступний: нічого не закрито"
        waiting = {key for key, _ in self._unanswered}
        pair = [line for line in (next((x for x in reversed(lines) if x.speaker == who and x.key not in waiting), None)
                                  for who in ("Ich", self.cfg.name)) if line is not None]
        if not pair:
            return "⚙️ Відкритих рядків немає: нічого не закрито"
        try:
            closed = self.archive.mark([line.key for line in pair], "blocked")
        except Exception as exc:  # noqa: BLE001
            log.error("unblock: the lines were not marked (%s)", type(exc).__name__)
            return "⚙️ Не закрито: архів не відповів"
        self.close_lines([(line.speaker, line.text) for line in pair])
        log.warning("unblock: %d line(s) marked blocked", closed)
        today = local_now(self.clock(), self.tz).date()

        def when(ms: int) -> str:
            at = local_now(ms, self.tz)
            return at.strftime("%H:%M" if at.date() == today else "%d.%m %H:%M")

        named = ", ".join(f"{line.speaker} {when(line.ts_ms)}" for line in sorted(pair, key=lambda x: (x.ts_ms, x.id)))
        return f"⚙️ Закрито для gemini: {named}\n{self.status_answer()}"

    def purge_answer(self, args: list[str]) -> str:
        """v5.14 — `/purge` asks first (how much would go; `/purge yes` within `PURGE_CONFIRM_S` confirms), then
        deletes the backup's talk: her archive's closed lines, the closed facts, and those lines in her history. Counts
        only, never a text."""
        now_ms = self.clock()
        asked = self._purge_asked_ms is not None and now_ms - self._purge_asked_ms <= PURGE_CONFIRM_S * 1000
        if args[:1] == ["yes"] and asked:
            self._purge_asked_ms = None
            lines, facts = self.purge_backup_talk()
            return f"⚙️ Видалено розмову через backup: {lines} рядків, {facts} фактів"
        self._purge_asked_ms = now_ms
        lines = facts = 0
        try:
            lines = self.archive.closed_count() if self.archive is not None else 0
            facts = sum(1 for f in load_facts(self.facts_dir) if f.mark in BACKUP_FACT_MARKS) if self.facts_dir else 0
        except Exception as exc:  # noqa: BLE001
            log.error("purge: not counted (%s)", type(exc).__name__)
        return (f"⚙️ Видалити розмову через backup — {lines} рядків і {facts} фактів? Це не скасувати. "
                f"Надішли /purge yes протягом {PURGE_CONFIRM_S // 60} хв")

    def purge_backup_talk(self) -> tuple[int, int]:
        """v5.14 — delete the backup's talk: (lines, facts), at the owner's command; v5.21: every closed line loses its
        text (`Archive.empty_blocked`, the row kept so the Matrix room never gives it back open) and every closed fact
        goes. Her usage lines and logs hold no text and stay."""
        lines = facts = 0
        gone = set(self._closed)
        if self.archive is not None:
            try:
                deleted = self.archive.empty_blocked()
                lines = len(deleted)
                gone |= {(sp, form) for sp, text in deleted for form in (text, history_entry(text))}  # v5.15: reopened
            except Exception as exc:  # noqa: BLE001
                log.error("purge: the archive's lines were not deleted (%s)", type(exc).__name__)
        if self.facts_dir is not None:
            facts = purge_closed_facts(self.facts_dir)
            self.facts_now()  # the archive's mirror of the facts follows
        self.private_history = [line for line in self.private_history if line not in gone]
        self._unanswered = [(k, t) for k, t in self._unanswered if ("Ich", t) not in self._closed]
        self._closed = set()
        log.warning("purge: the backup's talk deleted (%d lines, %d facts)", lines, facts)
        return lines, facts

    @property
    def emptied_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.emptied.json"

    def maybe_empty_blocked(self) -> bool:
        """v5.21 (the owner, 2026-11-02: «раз в день вони мають взагалі видалятись якщо вони старші 24 години», at
        05:00) — once a day (`emptying_due`, the day kept in `state/<name>.emptied.json`, 0600): every closed line older
        than 24 hours loses its text (`Archive.empty_blocked`), every closed fact older than that goes, and both leave
        her history. Counts only in the log. Whether it ran."""
        now_ms = self.clock()
        try:
            last = json.loads(self.emptied_file.read_text(encoding="utf-8")).get("day", "")
        except (OSError, ValueError, AttributeError):
            last = ""
        if not emptying_due(now_ms, str(last), self.tz):
            return False
        emptied = self.archive.empty_blocked(now_ms - 86_400_000)
        facts = empty_closed_facts(self.facts_dir, now_ms / 1000 - 86_400) if self.facts_dir is not None else 0
        if facts:
            self.facts_now()  # the archive's mirror of the facts follows
        gone = {(sp, form) for sp, text in emptied for form in (text, history_entry(text))}
        self.private_history = [line for line in self.private_history if line not in gone]
        self._closed -= gone
        tmp = self.emptied_file.with_suffix(".json.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"day": day_bounds(now_ms, self.tz)[0]}, f)
        os.replace(tmp, self.emptied_file)
        log.warning("archive: the daily emptying — %d closed lines and %d closed facts older than a day", len(emptied),
                    facts)
        return True

    def status_answer(self) -> str:
        """The `/status` line (v5.21 `route_status`): the mode and its end, the last hour's blocks, her `blocked`
        private lines and today's answers."""
        now_ms = self.clock()
        blocked = 0
        if self.archive is not None:
            try:
                blocked = self.archive.closed_count()
            except Exception as exc:  # noqa: BLE001
                log.error("archive: the marks were not counted (%s)", type(exc).__name__)
        try:  # the whole day's answers (the owner's live test), from her usage lines — no text in them
            records = parse_lines(self.usage_file.read_text(encoding="utf-8").splitlines())[0]
        except OSError:
            records = []
        answers, _, _ = day_counts(records, day_bounds(now_ms, self.tz)[0], now_ms)
        text = route_status(load_route(self.route_file), now_ms, self.tz, self.fallback_hour_max, blocked, answers)
        return text if self.backup_open() else text + "\n(backup вимкнено)"

    def backup_open(self) -> bool:
        """v5.22 (the owner, 2026-11-02: «зроби нормальний перемикач коли роутінг включений а коли ні») — a block
        sends her private answer to the backup only with its model and token and the panel's `FALLBACK_ROUTE` on,
        read at each use (`live_value`): the switch works without a restart."""
        return self.fallback_responder is not None and live_value(self.memory_file.parent, self.cfg.localpart,
                                                                  "FALLBACK_ROUTE", os.environ) == "on"

    async def telegram_hear(self, update: Update) -> None:
        """The owner's voice note as words: the capped download (in memory only), Deepgram, a `stt` usage line —
        then his line in the private chat. Not heard → a fixed short line; never a word in a log."""
        if self.stt is None:
            log.info("telegram: a voice note, hearing off")
            await self.telegram.send_message(self.telegram_owner, PRIVATE_CANT_LISTEN)
            return
        audio = None
        if update.file_size is None or update.file_size <= VOICE_MAX_BYTES:
            path = await self.telegram.get_file(update.file_id)
            audio = await self.telegram.download(path, VOICE_MAX_BYTES) if path else None
        if audio is None:
            log.error("telegram: the voice note could not be downloaded")
            await self.telegram.send_message(self.telegram_owner, PRIVATE_NOT_HEARD)
            return
        t0 = self.mono()
        heard, audio_ms = await self.stt.transcribe(audio, update.mime or "audio/ogg")
        took = round((self.mono() - t0) * 1000)  # v5.22: the call's time
        self._append_usage(lambda ts: stt_usage_line(ts, self.cfg.localpart, STT_MODEL, audio_ms,
                                                     audio_ms is not None, took))
        if not heard:
            log.info("telegram: nothing heard")
            await self.telegram.send_message(self.telegram_owner, PRIVATE_NOT_HEARD)
            return
        log.info("telegram: heard (%s ms)", audio_ms)
        self.private_line(heard, update.date_ms, "telegram", f"tg:{update.update_id}")

    async def _telegram_action(self, action: str) -> None:
        """«recording voice…» / «typing…» kept up while she composes — Telegram shows one for about five seconds."""
        while True:
            await asyncio.sleep(ACTION_EVERY_S)
            await self.telegram.send_chat_action(self.telegram_owner, action)

    def photos_today(self) -> int:
        """v5.17 — her photos kept today (`state/<name>.photos/<day>/`), for the day's cap."""
        folder = self._dir("photos") / local_now(self.clock(), self.tz).date().isoformat()
        try:
            return sum(1 for p in folder.iterdir() if p.is_file())
        except OSError:
            return 0

    def media_times(self, kind: str = "photos") -> list[int]:
        """v5.22 — when her photos (or, `videos`, videos) were kept today and yesterday: each file's `HHMMSS` in its
        day's folder, on her clock — so a window across midnight counts, and a restart keeps it."""
        today = local_now(self.clock(), self.tz)
        out = []
        for day in (today - timedelta(days=1), today):
            try:
                names = [p.stem for p in (self._dir(kind) / day.date().isoformat()).iterdir() if p.is_file()]
            except OSError:
                continue
            for n in names:
                if len(n) == 6 and n.isdigit():
                    t = day.replace(hour=int(n[:2]), minute=int(n[2:4]), second=int(n[4:]), microsecond=0)
                    out.append(int(t.timestamp() * 1000))
        return out

    def _window_full(self, kind: str, most: int, window_s: int) -> bool:
        """v5.22 — `most` of her photos or videos already went in the last `window_s` (0: no such cap)."""
        if most <= 0:
            return False
        now = self.clock()
        return sum(1 for t in self.media_times(kind) if 0 <= now - t < window_s * 1000) >= most

    def _photo_closed(self, door: str | None) -> str | None:
        """Why her answer may not carry a photo now (None: it may) — v5.17: not Telegram, the image model off, the day's
        cap; v5.22: `PHOTO_WINDOW_MAX` photos already in the last `PHOTO_WINDOW_S` (the owner, 2026-11-02: «з кожним
        меседжем … ліпше кількість на 30 хв»)."""
        if door != "telegram":
            return "element"
        if self.photos is None or self.photo_day_max <= 0:
            return "off"
        if self.photos_today() >= self.photo_day_max:
            return "cap"
        if self._window_full("photos", self.photo_window_max, self.photo_window_s):
            return "window"
        return None

    def _photo_open(self, door: str | None) -> bool:
        """v5.17 — may her answer carry a photo (the skill offered to Gemini): `_photo_closed` names no reason."""
        return self._photo_closed(door) is None

    def videos_today(self) -> int:
        """v5.18 — her videos today, for the day's cap: the ones paid for (today's ok `video` / `video_note` lines in
        her usage file — review #1: one paid for that then failed counts too) or the ones kept
        (`state/<name>.videos/<day>/`), whichever is more."""
        day = local_now(self.clock(), self.tz).date().isoformat()
        try:
            kept = sum(1 for p in (self._dir("videos") / day).iterdir() if p.is_file())
        except OSError:
            kept = 0
        try:
            records = parse_lines(self.usage_file.read_text(encoding="utf-8").splitlines())[0]
        except OSError:
            records = []
        paid = sum(1 for r in records
                   if r.get("kind") in VIDEO_USAGE and r.get("ok") and str(r["ts"])[:10] == day)
        return max(kept, paid)

    def _video_closed(self, door: str | None, kind: str) -> str | None:
        """v5.18 — why her answer may not carry this video now (None: it may): not Telegram, the maker off (a кружечок
        also needs her photo and her voice), the day's cap, or a video already being made."""
        if door != "telegram":
            return "element"
        maker = self.notes if kind == "note" else self.clips
        if maker is None or self.photos is None or (kind == "note" and self.tts is None) or self.video_day_max <= 0:
            return "off"
        if self.videos_today() >= self.video_day_max:
            return "cap"
        if self._window_full("videos", self.video_window_max, self.video_window_s):  # v5.22: «2 за 2 години»
            return "window"
        return "busy" if self._video_busy else None

    def _video_kinds(self, door: str | None) -> tuple[str, ...]:
        """v5.18 — the videos her answer may carry now, for Gemini's prompt."""
        return tuple(k for k in VIDEO_KINDS if self._video_closed(door, k) is None)

    async def _make_video(self, shot: Shot, pcm: bytes | None) -> Video:
        """v5.18 — her video: its first frame (her photo), then her кружечок (her voice as mp3, fal, the square cut)
        or her clip (Omni Flash); any step that fails is the reason."""
        frame = await self._make_photo(frame_shot(shot), FRAME_ASPECT[shot.kind], FRAME_LINES[shot.kind], "frame")
        if frame.why != "ok" or not frame.image:
            return Video(None, why=frame.why if frame.why != "ok" else "failed")
        if shot.kind == "clip":
            return await self.clips.make(shot, self._moment(), frame.image, frame.mime)
        mp3 = await pcm_to_mp3(pcm or b"", self.video_note_lead_ms)
        if mp3 is None:
            return Video(None, why="failed")
        small = await shrink_frame(frame.image)  # the owner: a кружечок needs no big picture — 640×640 to fal
        image, mime = (small, "image/jpeg") if small else (frame.image, frame.mime)
        raw = await self.notes.make(image, mime, mp3,  # Fabric names no length: her voice's, with its silence
                                    (duration_ms(pcm or b"") + max(0, self.video_note_lead_ms)) / 1000)
        if raw.why != "ok":
            return raw
        square = await square_note(raw.data, mp3)  # review #3: her own voice is its sound
        return Video(square, seconds=raw.seconds) if square else Video(None, why="failed")

    async def _video_after(self, shot: Shot, pcm: bytes | None, brief: str) -> None:
        """v5.18 — after her answer: «записує відеоповідомлення» / «надсилає відео» kept up while the video is made,
        then sent and kept, her line naming it; a кружечок that did not come out is her voice note after all, a clip
        one short line of hers. Never a crash; one at a time."""
        name = "record_video_note" if shot.kind == "note" else "upload_video"
        action, began = None, self.clock()
        try:
            try:
                await self.telegram.send_chat_action(self.telegram_owner, name)
                action = asyncio.create_task(self._telegram_action(name))
                made = await self._make_video(shot, pcm)
            except Exception as exc:  # noqa: BLE001 — no video, never a crash
                log.warning("video: failed (%s)", type(exc).__name__)
                made = Video(None, why="failed")
            finally:
                if action is not None:
                    action.cancel()
            why, sent = made.why, False
            if made.why == "ok" and made.data:
                if shot.kind == "note":
                    seconds = made.seconds if made.seconds else duration_ms(pcm or b"") / 1000
                    sent = await self.telegram.send_video_note(self.telegram_owner, made.data, round(seconds),
                                                               NOTE_SIDE)
                else:
                    sent = await self.telegram.send_video(self.telegram_owner, made.data,
                                                          round(made.seconds) if made.seconds else None)
                why = "ok" if sent else "not sent"
            took = round((self.clock() - began) / 1000)  # review #4: the DoD notes how long a video takes
            if sent:
                self.keep_video(made)
                log.info("video: sent (%s, telegram, %d s)", shot.kind, took)
                self._own_private_line(photo_note("", shot).strip())
            elif shot.kind == "note":
                log.warning("video: %s after %d s — her voice note instead", why, took)
                ogg = await encode_opus(pcm) if pcm else None
                if ogg is None or not await self.telegram.send_voice(self.telegram_owner, ogg,
                                                                     round(duration_ms(pcm) / 1000)):
                    log.warning("voice: not sent (telegram)")
            else:
                log.warning("video: %s after %d s — a line of hers instead", why, took)
                await self._video_failed_line(brief)
        except Exception as exc:  # noqa: BLE001
            log.error("video: failed after her answer (%s)", type(exc).__name__)
        finally:
            self._video_busy = False

    async def _video_failed_line(self, brief: str) -> None:
        """v5.18 — her clip did not send: one short line of hers through Gemini, or nothing — drawn in turn with her
        answers (never while one is on its way), and an owner's line that came meanwhile is answered after."""
        for _ in range(120):
            if not self._private_pending:
                break
            await asyncio.sleep(1)
        else:
            log.info("video: no line — an answer kept the chat")
            return
        self._private_pending = True
        try:
            self._offer_photo, self._offer_video, self._pending_shot = False, (), None
            text, _ = await self._gemini_text(f"{brief}\n\n{VIDEO_FAILED}", "private")
            self._pending_shot = None
            if text is not None and await self.send_telegram(text):
                self._own_private_line(str(text))
        finally:
            again = self._private_again
            self._private_pending = False
            if again:  # the owner wrote meanwhile: answer him (as after a line written first)
                self._private_pending = True
                self._spawn(self.private_later(0))

    def _own_private_line(self, text: str) -> None:
        """v5.18 — a line of hers sent in Telegram after her answer (a video's note, a short line): her private history,
        her archive and the session, as her answer's own."""
        self.private_history = append_history(self.private_history, self.cfg.name, text, max(self.history_n, 1))
        self.last_private_ms = self.clock()
        self._own_seq += 1
        self._archive(f"own:telegram:{self.clock()}:{self._own_seq}", self.clock(), "private", "telegram",
                      self.cfg.name, text)
        if self.cfg.can("summary"):
            self.session.append((private_label(self.cfg.name), text))

    def _moment(self) -> Moment:
        """v5.17 — her moment for a photo or (v5.18) a clip: her clock, the season and (with `mood`) her day's Lviv
        weather."""
        now = local_now(self.clock(), self.tz)
        weather = None
        if self.cfg.can("mood"):
            try:
                weather = load_weather(self.weather_file, now.date().isoformat())
            except Exception as exc:  # noqa: BLE001 — a photo without the weather, never none
                log.error("photo: the weather was not read (%s)", type(exc).__name__)
        return Moment(now, weather)

    async def _make_photo(self, shot: Shot, aspect: str = "3:4", extra: str | None = None,
                          kind: str = "photo") -> Made:
        """v5.17 — her photo for this moment; v5.18: a video's first frame takes its aspect and frame line (v5.22: and
        its usage line is the kind `frame`)."""
        try:
            return await self.photos.make(shot, self._moment(), aspect, extra, kind)
        except Exception as exc:  # noqa: BLE001 — her answer without it, never a crash
            log.warning("photo: failed (%s)", type(exc).__name__)
            return Made(None, why="failed")

    def keep_photo(self, made: Made) -> None:
        """v5.17 — a photo she sent, kept as `state/<name>.photos/<day>/HHMMSS.jpg` (file 0600, folders 0700); a write
        error is logged by its type."""
        self._keep_media("photos", made.image, ".png" if made.mime == "image/png" else ".jpg")

    def keep_video(self, made: Video) -> None:
        """v5.18 — a video she sent, kept as `state/<name>.videos/<day>/HHMMSS.mp4` (file 0600, folders 0700)."""
        self._keep_media("videos", made.data, ".mp4")

    def _keep_media(self, kind: str, data: bytes | None, ext: str) -> None:
        now = local_now(self.clock(), self.tz)
        folder = self._dir(kind) / now.date().isoformat()
        try:
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(folder.parent, 0o700)
            os.chmod(folder, 0o700)
            path, n = folder / f"{now:%H%M%S}{ext}", 1
            while path.exists():
                n += 1
                path = folder / f"{now:%H%M%S}-{n}{ext}"
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
                out.write(data or b"")
        except OSError as exc:
            log.error("%s: not kept (%s)", kind[:-1], type(exc).__name__)

    async def send_telegram(self, text: str, mark: str | None = None, photo: Made | None = None,
                            hold_voice_s: float | None = None) -> bool:
        """Every answer in Telegram is a voice note in her own voice, then the text (the owner, 2026-10-21) — the
        speakers' monthly budget and `voiceable` still hold; when the voice cannot be made, the text goes alone.
        `mark` (v5.15): a line above the text only, never voiced. v5.17: with `photo`, after the voice note the photo
        goes with her words as its caption (a text over Telegram's caption limit: the photo, then the text; a photo not
        sent: the text alone) — `photo_sent` says whether it went. v5.18: with `hold_voice_s`, a voice of at most that
        long is held for her кружечок instead of sent (`voice_held`; else `voice_hold_miss` says why not). True when
        the text went out."""
        self.photo_sent = False
        self.voice_held, self.voice_hold_miss = None, None
        text, speech = spoken(text)  # v5.9: her voice gets the tags, the message her words
        why = self.voice_off
        if self.tts is not None:
            if not voiceable(text) or not voiceable(speech):  # v5.12 review #3: a link alone is never voiced
                why = "not voiceable"
            elif self._speakers_month_used() + len(speech) > self.voice_monthly_chars:
                why = "monthly cap"
            else:
                t0 = self.mono()
                pcm = await self.tts.synth(speech)
                self.record_tts(len(speech), pcm is not None, round((self.mono() - t0) * 1000))
                if hold_voice_s is not None and pcm is not None:
                    if duration_ms(pcm) <= hold_voice_s * 1000:
                        self.voice_held, pcm = pcm, None  # sent later as her кружечок, or as this voice note
                        log.info("voice: held for a кружечок (telegram)")
                    else:
                        self.voice_hold_miss = "too long"
                ogg = await encode_opus(pcm) if pcm is not None else None
                why = ("held" if self.voice_held is not None else "tts failed" if pcm is None
                       else "encode failed" if ogg is None
                       else None if await self.telegram.send_voice(self.telegram_owner, ogg,
                                                                   round(duration_ms(pcm) / 1000))
                       else "send failed")
            if why is None:
                log.info("voice: sent (%d chars, telegram)", len(text))
            elif why not in ("not voiceable", "held"):
                log.info("voice: text only (%s, telegram)", why)
        self.voice_sent = why is None and self.tts is not None  # v5.22: what went with the answer
        body = f"{mark}\n{text}" if mark else text
        if photo is not None and photo.image:
            caption = body if len(body) <= CAPTION_MAX else None
            if await self.telegram.send_photo(self.telegram_owner, photo.image, caption, photo.mime):
                self.photo_sent = True
                if caption is not None:
                    return True
            else:
                log.warning("photo: not sent (telegram) — the text alone")
        return await self.telegram.send_message(self.telegram_owner, body)

    async def send_line(self, room_id: str, text: str, event_key: str, answering: str | None = None,
                        mark: str | None = None) -> str | None:
        """v5.3 — every line the agent says: a voice message under a plain label when it should and can (`voice_due`,
        a voice, a voiceable line, under the speakers' monthly budget), never a reply; then always the same text as
        `m.text` — the only form the iPhone's Element shows the words in (it renders no media caption; the owner,
        2026-10-18). The other agents read the text. `mark` (v5.15): a line above the text only, never voiced. Never a
        word in a log."""
        voice_of = self._transcript_voice.get(answering or "") or None
        text, speech = spoken(text)  # v5.9: her voice gets the tags, the message her words
        why = self.voice_off
        if self.tts is not None:
            if not voiceable(text) or not voiceable(speech):  # v5.12 review #3: a link alone is never voiced
                why = "not voiceable"
            elif not voice_due(voice_of is not None, event_key or "", self.cfg.localpart, self.voice_reply_p):
                why = "share"
            elif self._speakers_month_used() + len(speech) > self.voice_monthly_chars:
                why = "monthly cap"
            else:
                name = f"{self.cfg.localpart}-{local_now(self.clock(), self.tz):%Y%m%d-%H%M%S}.ogg"
                # never a reply (the owner, 2026-10-18: «забери ці реплаї») — it is voiced, not quoted
                content, why = await voice_message(self.client, self.tts, speech, name,
                                                   on_synth=lambda ok, ms=None: self.record_tts(len(speech), ok, ms))
                if content is not None:
                    try:
                        await self.client.room_send(room_id=room_id, message_type="m.room.message", content=content)
                    except Exception as exc:  # noqa: BLE001 — the text still goes out
                        why = f"send failed ({type(exc).__name__})"
            if why is None:
                log.info("voice: sent (%d chars)", len(text))
            elif why not in ("share", "not voiceable"):
                log.info("voice: text only (%s)", why)
        self.voice_sent = why is None and self.tts is not None  # v5.22: what went with the answer
        resp = await self.client.room_send(room_id=room_id, message_type="m.room.message",
                                           content={"msgtype": "m.text", "body": f"{mark}\n{text}" if mark else text})
        event_id = getattr(resp, "event_id", None)  # v5.8 review #1: the text's own id, so a re-read deduplicates
        return event_id if isinstance(event_id, str) and event_id else None

    def _speakers_month_used(self) -> int:
        """This month's spoken characters of every speaker (their usage files in state/), the heralds left out."""
        records: list = []
        for path in self.memory_file.parent.glob("*.usage.jsonl"):
            try:
                records += parse_lines(path.read_text(encoding="utf-8").splitlines())[0]
            except OSError:
                continue
        return speakers_month_chars(records, local_now(self.clock(), self.tz).strftime("%Y-%m"), self.heralds)

    def record_tts(self, characters: int, ok: bool, latency_ms: int | None = None) -> None:
        model = getattr(self.tts, "model", None) or TTS_MODEL  # v5.9: the model this voice ran on
        self._append_usage(lambda ts: tts_usage_line(ts, self.cfg.localpart, model, characters, ok, latency_ms))

    async def on_audio(self, room: MatrixRoom, event: RoomMessageAudio) -> None:
        """v5.2 — no agent answers audio: the owner's voice in the room is remembered, so Hermes's transcript of it
        reads as the owner's line; everything is logged as ignored."""
        try:
            if not self.started:
                return
            if event.sender in self.member_ids:
                caption = voice_caption(event) if room.room_id == self.cfg.room_id else None
                if caption is not None:  # v5.3: a speaker's voiced line — its caption is its words, read as a line
                    await self.on_message(room, self._line_of(event, caption))
                return
            if room.room_id == self.cfg.room_id and event.sender == self.cfg.owner:
                self._remember_voice(str(getattr(event, "event_id", "")))
                log.info("ignored: audio (%s)", "transcribed by Hermes" if self.transcriber else "no one transcribes")
            else:
                log.info("ignored: audio (room %s)", room.room_id)
        except Exception:
            log.exception("audio handler failed (bot keeps running)")

    def reserved(self, now_ms: int) -> int:
        """The owner's chosen answers still on their way — they hold their place in the wave until FALLBACK_S.
        Never one for this agent itself: whether it still owes an answer is its own knowledge (code review #2)."""
        if self.last_owner is None:
            return 0
        eid, text = self.last_owner
        chosen = {self.roster[n].name for n in owner_speakers(eid, text, self.roster, self.owner_repliers,
                                                            self.cat_react_p, self.cat_purr_p)}
        chosen.discard(self.cfg.name)
        return pending_answers(self.timeline, eid, chosen, "Ich", now_ms, int(self.fallback_s * 1000))

    def decide(self, sender: str, text: str, event_id: str, now_ms: int, resumed: bool = False):
        return decide_reply(
            sender, text, event_id,
            wave_count(self.timeline, "Ich", now_ms, self.bot_window_ms) + self.reserved(now_ms),
            self.cfg, self.me, self.roster,
            owner_repliers_k=self.owner_repliers,
            react_p=self.cat_react_p,
            purr_p=self.cat_purr_p,
            max_bot_turns=self.max_bot_turns,
            bot_reply_p=self.bot_reply_p,
            reply_delay_s=self.reply_delay_s,
            rng=self.rng,
            resumed=resumed,
        )

    def _purr_in_timeline(self, sender: str, text: str) -> bool:
        """Only an agent's line is a purr — the owner's «Мур!» is a message like any other (review #2)."""
        return sender != self.cfg.owner and is_purr(text)

    @staticmethod
    def _repeat_purr(lines: list[tuple[str, str]], speaker: str, text: str) -> bool:
        """A purr right after the same speaker's purr — it collapses into the earlier one (v4.2)."""
        return bool(lines) and lines[-1][0] == speaker and is_purr(text) and is_purr(lines[-1][1])

    def _add_context(self, speaker: str, text: str) -> None:
        """The context window, with consecutive purrs collapsed so they never crowd out the talk."""
        if self._repeat_purr(self.history, speaker, text):
            self.history = [*self.history[:-1], (speaker, text)]
        else:
            self.history = append_history(self.history, speaker, text, self.history_n)
        if self.wide_n:  # v4.5: the philosopher's wider window
            if self._repeat_purr(self.wide_history, speaker, text):
                self.wide_history = [*self.wide_history[:-1], (speaker, text)]
            else:
                self.wide_history = append_history(self.wide_history, speaker, text, self.wide_n)

    def _remember_text(self, event_id: str, text: str) -> None:
        """What a reply answers (v4.5: Claude's mode depends on it) — bounded like the windows."""
        if not event_id:
            return
        self._texts[event_id] = text
        while len(self._texts) > max(self.history_n, self.wide_n, 1) * 2:
            self._texts.pop(next(iter(self._texts)))

    async def purr_later(self, room_id: str, delay_s: float, event_id: str) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            if self._reply_pending:  # his words are on their way: a purr now would count as his answer (v4.3 review #1)
                log.info("purr dropped: a reply is on its way")
                return
            await self.send_line(room_id, pick_purr(event_id, self.cfg.localpart), event_id, answering=event_id)
        except Exception:
            log.exception("purr failed (bot keeps running)")

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)  # strong ref: pending tasks are only weakly referenced
        task.add_done_callback(self._tasks.discard)

    def pause_until_window_frees(self, room_id: str, sender: str, text: str, event_id: str, now_ms: int) -> None:
        """R4 — the wave limit is a rate, not a lock: resume once the window frees,
        but only if the conversation hasn't moved on in the meantime."""
        wave, reserved = wave_count(self.timeline, "Ich", now_ms, self.bot_window_ms), self.reserved(now_ms)
        times = []
        if wave >= self.max_bot_turns:  # the wave itself is full: wait for its oldest turn to age out
            times.append(wave_frees_at(self.timeline, "Ich", now_ms, self.bot_window_ms, self.max_bot_turns))
        if reserved and self.last_owner:  # the owner's pending answers hold it: wait for them to lapse
            times.append(reservation_lapses_at(self.timeline, self.last_owner[0], int(self.fallback_s * 1000)))
        if not times or any(t is None for t in times):
            log.info("silent: wave-limit")
            return
        frees = max(times) + 1
        wait_s = (frees - now_ms) / 1000 + 1.0 + self.rng() * max(self.reply_delay_s - 1.0, 0.0)
        log.info("paused: wave-limit; resume check in %.0fs", wait_s)
        self._spawn(self.resume_later(room_id, sender, text, event_id, frees, wait_s))

    async def resume_later(self, room_id: str, sender: str, text: str, event_id: str, at_ms: int,
                           wait_s: float) -> None:
        try:
            await asyncio.sleep(wait_s)
            if not is_latest(self.timeline, event_id):  # a purr since the pause is no move (review #3)
                log.info("resume dropped: the conversation moved on")
                return
            decision = self.decide(sender, text, event_id, at_ms, resumed=True)
            if not decision.reply:
                log.info("resume: silent (%s)", decision.reason)
                return
            log.info("resume: %s", decision.reason)
            await self.reply(room_id, event_id, at_ms, delay_ms=round(wait_s * 1000))
        except Exception:
            log.exception("resume failed (bot keeps running)")

    def maybe_fallback(self, room_id: str, text: str, event_id: str) -> None:
        """If no agent answers the owner within FALLBACK_S, the best-ranked unchosen member does — each agent
        checks for itself from the shared timeline, with no coordination."""
        if fallback_replier(event_id, text, self.roster, self.owner_repliers) == self.me.localpart:
            self._spawn(self.fallback_later(room_id, event_id))

    async def fallback_later(self, room_id: str, event_id: str) -> None:
        try:
            await asyncio.sleep(self.fallback_s)
            for _ in range(6):  # busy with another reply: re-arm briefly instead of giving up (code review #3)
                if not fallback_due(self.timeline, event_id):
                    return
                if not self._reply_pending:
                    break
                await asyncio.sleep(5)
            else:
                return
            log.info("reply: fallback — nobody answered the owner")
            self._reply_pending = True
            try:
                await self.reply(room_id, fallback_for=event_id, delay_ms=round(self.fallback_s * 1000))
            finally:
                self._reply_pending = False
        except Exception:
            log.exception("fallback failed (bot keeps running)")

    def _current(self, trigger: str, at_ms: int | None = None) -> bool:
        """R3 for an agent-to-agent reply: the answered message is still the latest and the wave below the limit."""
        now = at_ms if at_ms is not None else self.clock()
        return still_current(self.timeline, trigger, "Ich", now, self.bot_window_ms, self.max_bot_turns,
                             self.reserved(now))

    def brief(self, template: str) -> str:
        """An assistant's brief with the room's members filled in (v5.5)."""
        return template.format(members=self.members_phrase)

    def build_prompt(self, pastlife: str | None = None, nudge: str | None = None, move: str | None = None,
                     private: str | None = None, recalled: str | None = None, agora_now: str | None = None,
                     facts: str | None = None, skip_layers: frozenset = frozenset(), talk: bool = False) -> str:
        """The full system instruction for a reply, in contract order; `pastlife` is a chosen thesis, `nudge` a
        nudge's material and rule (v4.3), `move` a persona's move line (v4.6), `private` the private chat's situation
        (v5.6; an Agora reply of a person with `private` closes its rules with the discretion line). An assistant
        (v4.4, Claude) has no canon: its brief is the instruction."""
        if self.cfg.type == "assistant":
            prompt = self.brief(CLAUDE_BRIEF_DIRECT)
            _LAST_PARTS.set((prompt, {"brief": len(prompt)}))
            return prompt
        layers = self.prompt_layers(pastlife, nudge, move, private, recalled, agora_now, facts, skip_layers, talk)
        prompt = build_instruction(**layers)
        # v5.22: its parts' sizes (the rules and the joins are what is left), for the answer call's usage line
        parts = {PART_NAMES.get(k, k): len(v) for k, v in layers.items() if k != "name" and isinstance(v, str) and v}
        parts["rules"] = max(0, len(prompt) - sum(parts.values()))
        _LAST_PARTS.set((prompt, parts))
        return prompt

    def prompt_layers(self, pastlife: str | None = None, nudge: str | None = None, move: str | None = None,
                      private: str | None = None, recalled: str | None = None, agora_now: str | None = None,
                      facts: str | None = None, skip_layers: frozenset = frozenset(), talk: bool = False) -> dict:
        """v5.16 — the sections `build_prompt` hands to `build_instruction`, by name (a person's, never an
        assistant's), so her private prompt can be kept in parts and built again from what is kept. `talk` (v5.20):
        her private prompt to Gemini gets the summaries of her private chat before its window."""
        can = self.cfg.can
        now = local_now(self.clock(), self.tz)
        world = None
        if can("world"):
            world = now_line(now, self.location)
            if self.summary_ms is not None:
                world += " " + last_talk_line(local_now(self.summary_ms, self.tz), now)
        # v5.22 (the owner): alone with him the shorter story, when her canon has one (`life_private`)
        story = self.cfg.life_private if private is not None and self.cfg.life_private else self.cfg.life
        life = life_section(story, now.date()) if can("life") and story else None
        return {
            # v5.22 (the owner): alone with him her shorter canon, when she has one (`canon_private`)
            "name": self.cfg.name,
            "canon": (self.cfg.canon_private if private is not None and self.cfg.canon_private else self.cfg.canon)
            if can("canon") else "",
            "summary": self.summary if can("summary") else None, "life": life, "world": world,
            "memories": self.memories_section(now, skip_layers) if can("chronicle") else None,
            "plans": self.plans_section(now) if can("plans") else None,
            "today": self.today_section(now) if can("today") else None,
            "mood": self.mood_section(now) if can("mood") else None,
            # v5.12: today's thoughts — alone with him all of them, a news one with its link; in Agora not the private
            "thoughts": (thoughts_section(self.day_thoughts(now.date()), private is not None, self.thoughts_in_prompt)
                         if can("thoughts") else None),
            "pastlife": pastlife if can("pastlife") else None,
            "nudge": nudge if can("nudge") else None,
            "rules_extra": CREATURE_RULES if self.cfg.type == "creature" else None,
            "move": move if self.cfg.type == "persona" else None,
            # v5.3 (the owner): its own questions of this session outlast the context window — never asked twice
            "asked": asked_section(own_questions(self.session, self.cfg.name)) if self.cfg.type == "persona" else None,
            "private": private if can("private") else None,
            "discretion": PRIVATE_DISCRETION if can("private") and private is None else None,
            # v5.8: what she knows of the owner and Agora today reach only her private prompt
            "facts": facts if private is not None else None,
            "agora_now": agora_now if private is not None and can("recall") else None,
            "recalled": recalled if can("recall") else None,
            "talk": self.talk_now(now) if talk and private is not None and can("talk") else None,  # v5.20
            # v5.22 (the owner, 2026-11-02: «прибрати рядок про PASS з її промпту, щоб вона завжди відповідала»; «коли
            # вона пише першою — теж забери»): alone with him she is never offered PASS — Gemini took it for a quiet
            # refusal
            "can_pass": private is None,
            "voice": self.cfg.voice_spec if can("emotion") and self.cfg.voice_spec else None,  # v5.9: both her prompts
        }

    def draw_move(self, event_id: str, now) -> str | None:
        """v4.6 — a persona's move for the event it answers: the kind is logged, the line goes into the prompt."""
        if self.cfg.type != "persona" or not event_id:
            return None
        move = persona_move(event_id, self.me, self.roster, "Ich", self.move_weights,
                            has_plans=self.cfg.can("plans") and bool(self.plans_section(now)),
                            has_life=self.cfg.can("life") and bool(self.cfg.life),
                            has_thoughts=any(t.place == "thought" for t in self.day_thoughts(now.date())))
        log.info("move: %s", move.kind)
        return move_line(move)

    # --- v2.2: files under state/ -------------------------------------------------
    def _dir(self, kind: str) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.{kind}"

    def append_journal(self, text: str) -> None:
        """The day's conversation journal: session-only notes with their time."""
        now = local_now(self.clock(), self.tz)
        path = self._dir("days") / f"{now.date().isoformat()}.talk.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{now:%H:%M}] {text.strip()}\n")
        os.chmod(path, 0o600)

    def _read(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except (FileNotFoundError, UnicodeDecodeError, OSError):
            return None

    def plan_paths(self, today) -> dict[str, Path]:
        monday = today - timedelta(days=today.weekday())
        d = self._dir("plans")
        return {
            "year": d / f"year-{today.year}.md",
            "month": d / f"month-{today.year}-{today.month:02d}.md",
            "week": d / f"week-{monday.isoformat()}.md",
            "day": d / f"{today.isoformat()}.md",
        }

    def _previous_plan_path(self, horizon: str, today) -> Path:
        if horizon == "day":
            prev = today - timedelta(days=1)
        elif horizon == "week":
            prev = today - timedelta(days=7)
        elif horizon == "month":
            prev = today.replace(day=1) - timedelta(days=1)
        else:
            prev = today.replace(year=today.year - 1)
        return self.plan_paths(prev)[horizon]

    async def ensure_plans(self, today) -> None:
        """Generate the missing plans for today, coarse to fine; never rewrite one."""
        life = self.cfg.life
        cur = current_chapter(life, today) if life else None
        nxt = next_chapter(life, today) if life else None
        paths = self.plan_paths(today)
        monday = today - timedelta(days=today.weekday())
        labels = {
            "year": year_label(today.year),
            "month": month_label(today.year, today.month),
            "week": week_label(monday),
            "day": day_label(today, today + timedelta(days=3)),  # plain weekday + date
        }
        coarser: list[tuple[str, str]] = []
        for horizon in ("year", "month", "week", "day"):
            path = paths[horizon]
            existing = self._read(path)
            if existing is None:
                n_items = HORIZONS[horizon][0]
                mutations = roll_mutations(n_items, self.plan_mutation_rate, self.rng)
                prev = self._read(self._previous_plan_path(horizon, today))
                yesterday = self._read(self._dir("days") / f"{(today - timedelta(days=1)).isoformat()}.md")
                # v5.11: what happened to her lately and the known events ahead in the plan's reach
                since = today - timedelta(days=1 if horizon == "day" else 7)
                until = {"day": today + timedelta(days=7), "week": today + timedelta(days=7),
                         "month": month_end(today.year, today.month), "year": date(today.year, 12, 31)}[horizon]
                system, contents = plan_request(
                    horizon, self.cfg.name, self.cfg.canon, labels[horizon],
                    cur.body if cur else "", nxt.opening if nxt else None,
                    coarser, strip_tags(prev) if prev else None, yesterday,
                    mutations, self.plan_max_words,
                    [m.name for m in self.roster.values() if m.user_id != self.cfg.user_id and m.type != "herald"],
                    self.events_between(since, today, today), self.events_ahead(today, until),
                )
                text = await self.llm.generate(contents, system, max_output_tokens=self.plan_max_words * 3,
                                               kind="plan")
                if text is None:
                    log.error("plan %s failed — will retry later", horizon)
                    return
                items = parse_items(text)
                if not items:
                    log.error("plan %s came back empty — will retry later", horizon)
                    return
                existing = render_plan(items, mutations, self.plan_max_words)
                save_memory(path, existing)
                log.info("plan %s written (%d items, %d mutated)", horizon, len(items), sum(map(bool, mutations)))
            coarser.append((HORIZONS[horizon][1], strip_tags(existing)))

    def plans_section(self, now) -> str | None:
        today = now.date()
        names = {"year": f"На {today.year} рік", "month": f"На {MONTHS_NOM[today.month - 1]}",
                 "week": "На цей тиждень", "day": "На сьогодні"}
        parts = []
        for horizon, path in self.plan_paths(today).items():
            text = self._read(path)
            if text:
                parts.append(f"{names[horizon]}:\n{strip_tags(text)}")
        return "Твої плани:\n" + "\n\n".join(parts) if parts else None

    # --- v2.2: the chronicle -----------------------------------------------------
    @property
    def usage_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.usage.jsonl"

    def record_usage(self, kind: str, model: str, usage, ok: bool, blocked: str | None = None,
                     latency_ms: int | None = None) -> None:
        """One JSON line per Gemini call (v3.1) — no texts; a write error never blocks. `blocked` (v5.13): the stage
        of a safety block; `latency_ms` (v5.22): how long the call took."""
        parts = PROMPT_PARTS.get()  # v5.22: an answer's prompt in parts
        self._append_usage(lambda ts: usage_line(ts, self.cfg.localpart, kind, model, usage, ok, blocked, latency_ms,
                                                 parts))

    def record_video_note_usage(self, model: str, video_ms: int | None, ok: bool, blocked: str | None = None,
                                latency_ms: int | None = None) -> None:
        """v5.18 — one line per call of her кружечок's model on fal: `fal`, priced per second by `PRICE_SECONDS`, no text."""
        self._append_usage(lambda ts: video_note_usage_line(ts, self.cfg.localpart, model, video_ms, ok, blocked,
                                                            latency_ms))

    def record_fallback_usage(self, kind: str, model: str, ok: bool, latency_ms: int | None = None) -> None:
        """v5.14 — one line per call of her backup model: `novelai`, the subscription, never priced, no text."""
        parts = PROMPT_PARTS.get()
        self._append_usage(lambda ts: fallback_usage_line(ts, self.cfg.localpart, kind, model, ok, latency_ms, parts))

    def record_sdk_usage(self, kind: str, model: str, usage: dict | None, ok: bool,
                         reported_cost: float | None, latency_ms: int | None = None) -> None:
        """v4.4 — one line per Claude Agent SDK call: always `subscription`, never priced."""
        parts = PROMPT_PARTS.get()
        self._append_usage(lambda ts: sdk_usage_line(ts, self.cfg.localpart, kind, model, usage, ok, reported_cost,
                                                     latency_ms, parts))

    def _append_usage(self, build) -> None:
        if not self.trace_calls:
            self._append_jsonl(self.usage_file, build, "usage")
            return
        made: list[dict] = []
        self._append_jsonl(self.usage_file, lambda ts: made.append(build(ts)) or made[-1], "usage")
        if made:
            self._trace(made[0])

    @property
    def trace_calls(self) -> bool:
        """v5.22 (the owner, 2026-11-02) — every network call's result as a ⚙️ line to him in Telegram, for diagnosis:
        `TRACE_CALLS` read at each record (`live_value`), so the panel's switch works without a restart."""
        return self.telegram_open and live_value(self.memory_file.parent, self.cfg.localpart, "TRACE_CALLS",
                                                 os.environ) == "on"

    def _trace(self, record: dict) -> None:
        """v5.22 (the owner, 2026-11-02: «виключи бекап і включи щоб показувало все що приходить з джемені і інших
        мереж») — under `TRACE_CALLS` each usage record goes to him at once as one ⚙️ line (`trace_line`: the model,
        the kind, ok or the block with its reason, the tokens and the time); never a text, never in her history, the
        archive or a prompt, and a send that fails is only the trace's."""
        block = LAST_BLOCK.get() if record.get("blocked") else None
        send = self.telegram.send_message(self.telegram_owner, trace_line(record, block))
        try:
            self._spawn(send)
        except RuntimeError:  # no running loop: the record stays in the usage file only
            send.close()

    @property
    def answers_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.answers.jsonl"

    def record_answer(self, place: str, door: str, answered: str, asked_ms: int | None, delay_ms: int | None,
                      by: str, parts: list[str]) -> None:
        """v5.22 — one line per answer sent (`answer_line`): how long the message it answered waited, from that
        message's own time to now, and the deliberate pause in it; no text, and a failed write never stops an
        answer."""
        wait = self.clock() - asked_ms if asked_ms else None
        self._append_jsonl(self.answers_file, lambda ts: answer_line(ts, self.cfg.localpart, place, door, answered,
                                                                     wait, delay_ms, by, parts), "answer")

    def _event_at(self, event_id: str) -> tuple[int, str] | None:
        """v5.22 — a room message's own time and whose it was (`owner` | `agent`), from the shared timeline."""
        owner = self.names.get(self.cfg.owner, self.cfg.owner)
        for speaker, ts, eid, *_ in reversed(self.timeline):
            if eid == event_id:
                return ts, "owner" if speaker == owner else "agent"
        return None

    def _append_jsonl(self, path: Path, build, what: str) -> None:
        try:
            line = build(local_now(self.clock(), self.tz).isoformat(timespec="seconds"))
            path.parent.mkdir(parents=True, exist_ok=True)
            # private from birth (code review #2): created 0600, a looser old file tightened
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                    os.fchmod(fd, 0o600)
                os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except Exception:
            log.exception("%s line not written (the conversation continues)", what)

    @property
    def today_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.today.md"

    def first_run(self, today):
        """The agent's first day — memories are never generated before it."""
        path = self.memory_file.parent / f"{self.cfg.localpart}.first_run.txt"
        text = self._read(path)
        if text:
            return date.fromisoformat(text)
        session = self.memory_file.parent / f"{self.cfg.localpart}.json"
        born = today
        if session.exists():
            born = min(today, local_now(int(session.stat().st_mtime * 1000), self.tz).date())
        save_memory(path, born.isoformat())
        return born

    def _dates_in(self, kind: str) -> set:
        d = self._dir(kind)
        out = set()
        if d.exists():
            for p in d.glob("*.md"):
                if p.name.endswith(".talk.md"):
                    continue
                stem = p.stem
                try:
                    if kind in ("days", "weeks"):
                        out.add(date.fromisoformat(stem))
                    elif kind == "months":
                        y, m = stem.split("-")
                        out.add((int(y), int(m)))
                    else:
                        out.add(int(stem))
                except ValueError:
                    continue
        return out

    def _memory_path(self, kind: str, key) -> Path:
        if kind == "day":
            return self._dir("days") / f"{key.isoformat()}.md"
        if kind == "week":
            return self._dir("weeks") / f"{key.isoformat()}.md"
        if kind == "month":
            return self._dir("months") / f"{key[0]}-{key[1]:02d}.md"
        return self._dir("years") / f"{key}.md"

    def _chapter_body(self, d) -> str:
        life = self.cfg.life
        cur = current_chapter(life, d) if life else None
        return cur.body if cur else ""

    async def ensure_day_memory(self, d) -> bool:
        path = self._memory_path("day", d)
        if path.exists():
            return True  # never rewritten
        today = local_now(self.clock(), self.tz).date()
        prev_days = sorted(x for x in self._dates_in("days") if x < d)[-3:]
        previous = [(layer_label("day", x, today), self._read(self._memory_path("day", x)) or "")
                    for x in prev_days]
        block = self._read(self.today_file)
        block_text = None
        if block and block.startswith(f"<!-- {d.isoformat()}T"):
            block_text = block.split("-->", 1)[1].strip()
        chapter = self._chapter_body(d)
        system, contents = day_memory_request(
            self.cfg.name, self.cfg.canon, d, chapter, previous,
            self._read(self._dir("days") / f"{d.isoformat()}.talk.md"),
            self._read(self.plan_paths(d)["day"]), block_text, self.max_words["day"],
            events_for_prompt(self.day_events(d)) or None,
            # v5.12: what she read and thought — her `thought` place only: the memories reach Agora too
            "\n".join(thought_rows(self.day_thoughts(d), False, THOUGHTS_IN_MEMORY)) or None,
        )
        text = None
        for _attempt in range(2):  # one regeneration when it copies the story
            text = await self.llm.generate(contents, system, max_output_tokens=self.max_words["day"] * 3,
                                           kind="day_memory")
            if text is None:
                log.error("day memory %s failed — will retry later", d)
                return False
            if not shares_span(text, chapter + "\n" + self.cfg.canon):
                break
            log.info("day memory %s copied the story — regenerating", d)
        save_memory(path, cap_words(text, self.max_words["day"]))
        return True

    async def ensure_digest(self, kind: str, key) -> bool:
        path = self._memory_path(kind, key)
        if path.exists():
            return True  # never rewritten
        today = local_now(self.clock(), self.tz).date()
        if kind == "week":
            members = [key + timedelta(days=i) for i in range(7)]
            sources = [("day", d) for d in members if d in self._dates_in("days")]
            plan = self._read(self._dir("plans") / f"week-{key.isoformat()}.md")
            label = layer_label("week", key, today)
        elif kind == "month":
            sources = [("day", d) for d in sorted(self._dates_in("days")) if (d.year, d.month) == key]
            plan = self._read(self._dir("plans") / f"month-{key[0]}-{key[1]:02d}.md")
            label = layer_label("month", key, today)
        else:
            sources = [("month", k) for k in sorted(self._dates_in("months")) if k[0] == key]
            plan = self._read(self._dir("plans") / f"year-{key}.md")
            label = layer_label("year", key, today)
        texts = [(layer_label(k, x, today), self._read(self._memory_path(k, x)) or "") for k, x in sources]
        if not texts:
            return True
        system, contents = digest_request(kind, self.cfg.name, self.cfg.canon, label, texts, plan,
                                          self.max_words[kind])
        text = await self.llm.generate(contents, system, max_output_tokens=self.max_words[kind] * 3,
                                       kind="digest")
        if text is None:
            log.error("%s digest %s failed — will retry later", kind, key)
            return False
        save_memory(path, cap_words(text, self.max_words[kind]))
        return True

    async def world_tick(self, force: bool = False) -> None:
        """Day-boundary work: catch up day memories, digests, then today's plans.
        Cheap when nothing is due; a failure backs off for 10 minutes."""
        if not (self.cfg.can("chronicle") or self.cfg.can("plans")):
            return
        now_ms = self.clock()
        today = local_now(now_ms, self.tz).date()
        if now_ms < self._gen_retry_ms:
            return
        if not force and self._last_world_day == today and now_ms - self._last_world_check_ms < 600_000:
            return
        if self._gen_lock.locked():
            return
        async with self._gen_lock:
            self._last_world_check_ms, self._last_world_day = now_ms, today
            ok = True
            if self.cfg.can("chronicle"):
                first = self.first_run(today)
                for d in days_due(today, first, self._dates_in("days"), self.memory_days):
                    ok = ok and await self.ensure_day_memory(d)
                day_files = self._dates_in("days")
                for m in weeks_due(today, first, self._dates_in("weeks"), day_files):
                    ok = ok and await self.ensure_digest("week", m)
                for ym in months_due(today, first, self._dates_in("months"), day_files):
                    ok = ok and await self.ensure_digest("month", ym)
                for y in years_due(today, first, self._dates_in("years"), self._dates_in("months")):
                    ok = ok and await self.ensure_digest("year", y)
            if ok and self.cfg.can("plans"):
                await self.ensure_plans(today)
                ok = all(p.exists() for p in self.plan_paths(today).values())
            if not ok:
                self._gen_retry_ms = now_ms + 600_000

    def memories_section(self, now, skip: frozenset = frozenset()) -> str | None:
        """Her memories; `skip` (v5.14, the backup's budget) leaves out the layers of those kinds."""
        today = now.date()
        layers = select_layers(
            today, self.memory_days, self.memory_weeks, self.memory_months,
            self._dates_in("days"), self._dates_in("weeks"), self._dates_in("months"), self._dates_in("years"),
        )
        parts = []
        for kind, key in layers:
            if kind in skip:
                continue
            text = self._read(self._memory_path(kind, key))
            if text:
                parts.append(f"{layer_label(kind, key, today)}: {text}")
        return "Твої спогади:\n\n" + "\n\n".join(parts) if parts else None

    async def ensure_today(self, now) -> None:
        """The today block: regenerated when the hour changes; reset at midnight."""
        path = self.today_file
        events = self.day_events(now.date())  # v5.11: a new event refreshes the block within the hour
        tag = f"<!-- {now.date().isoformat()}T{now.hour:02d}{f' e{len(events)}' if events else ''} -->"
        current = self._read(path)
        if current and current.startswith(tag):
            return
        previous = None
        if current and current.startswith(f"<!-- {now.date().isoformat()}T"):
            previous = current.split("-->", 1)[1].strip()
        system, contents = today_request(
            self.cfg.name, self.cfg.canon, now, self._chapter_body(now.date()),
            self._read(self.plan_paths(now.date())["day"]),
            self._read(self._dir("days") / f"{now.date().isoformat()}.talk.md"),
            previous, self.max_words["today"], events_for_prompt(events) or None,
        )
        text = await self.llm.generate(contents, system, max_output_tokens=self.max_words["today"] * 3,
                                       kind="today")
        if text is None:
            log.error("today block failed — keeping the previous one")
            return
        save_memory(path, f"{tag}\n{cap_words(text, self.max_words['today'])}")

    def today_section(self, now) -> str | None:
        text = self._read(self.today_file)
        if not text or not text.startswith(f"<!-- {now.date().isoformat()}T"):
            return None  # reset at midnight
        return "Сьогодні:\n" + text.split("-->", 1)[1].strip()

    # --- v4.2: the mood of the day (Lumi's horoscope service) ----------------------------------------------------
    @property
    def mood_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.mood.log"

    def mood_section(self, now) -> str | None:
        """«Настрій дня» and — the owner, 2026-10-11 — the day's astrological sky, so whatever he says of the stars
        is real; without it, he is told he does not know the positions today."""
        if self.mood is None or self.mood.date != now.date().isoformat():
            return None
        if self.cfg.type == "persona":  # v5.10: a person reads a feeling — no sky, no horoscope word, no number
            feeling = person_mood(self.mood.resolution)
            return f"Настрій дня: {feeling}" if feeling else None
        sky = self.sky_today(now)
        return f"Настрій дня: {self.mood.resolution}" + (
            f"\n\n{SKY_SECTION.format(sky=sky)}" if sky else f"\n\n{NO_SKY_SECTION}")

    @property
    def sky_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.sky.json"

    def sky_today(self, now) -> str | None:
        day = now.date().isoformat()
        return self._sky[1] if self._sky is not None and self._sky[0] == day else None

    async def ensure_sky(self, now) -> str | None:
        """Once per local day: the day's file, else one grounded Gemini question (as Lumi's web lookup); a failure
        means no sky and a retry after 10 minutes — never a blocked reply or a blocked mood."""
        day = now.date().isoformat()
        if (line := self.sky_today(now)) is not None:
            return line
        if self._sky_lock.locked() or self.clock() < self._sky_retry_ms:
            return None
        async with self._sky_lock:
            if (line := load_sky(self.sky_file, day)) is not None:
                self._sky = (day, line)
                return line
            search = getattr(self.llm, "search", None)
            line = clean_sky(await search(sky_query(now.date()), SKY_MAX_TOKENS, "sky")) if search else None
            if line is None:
                log.error("sky lookup failed — none until a retry")
                self._sky_retry_ms = self.clock() + 600_000
                return None
            self._sky = (day, line)
            save_sky(self.sky_file, day, line)
            log.info("sky looked up")
            return line

    # --- v5.10: the day's Lviv weather (a person's mood) ---------------------------------------------------------
    @property
    def weather_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.weather.json"

    def weather_today(self, now) -> str | None:
        day = now.date().isoformat()
        return self._weather[1] if self._weather is not None and self._weather[0] == day else None

    async def ensure_weather(self, now) -> str | None:
        """Once per local day: the day's file, else one Open-Meteo request; a failure means no weather and a retry
        after 10 minutes — never a blocked mood or reply. Not a model call: no usage line."""
        day = now.date().isoformat()
        if (line := self.weather_today(now)) is not None:
            return line
        if self._weather_lock.locked() or self.clock() < self._weather_retry_ms:
            return None
        async with self._weather_lock:
            if (line := load_weather(self.weather_file, day)) is not None:
                self._weather = (day, line)
                return line
            line = await self.weather_fetch(now.date(), self.tz)
            if line is None:
                self._weather_retry_ms = self.clock() + 600_000
                return None
            self._weather = (day, line)
            save_weather(self.weather_file, day, line)
            log.info("weather fetched")
            return line

    async def ensure_mood(self, now) -> None:
        """Once per local day: reuse the day's logged reading, else one model call; a failure means no mood and a
        retry after 10 minutes — never a blocked reply. The lookups run inside the mood's lock, so a call during them
        never casts the day without its sky and weather (review #1); a person's prompt reads only the feeling, so once
        her mood exists she looks up nothing (review #3)."""
        day = now.date().isoformat()
        person = self.cfg.type == "persona"
        if self.mood is not None and self.mood.date == day:
            if not person:
                await self.ensure_sky(now)  # the cat's prompt carries the day's sky beside his mood
            return
        if self._mood_lock.locked() or self.clock() < self._mood_retry_ms:
            return
        async with self._mood_lock:
            logged = reading_from_log(self._read_raw(self.mood_file) or "", day)
            if logged:
                self.mood = MoodState(day, split_resolution(logged), logged)
                if not person:
                    await self.ensure_sky(now)
                return
            sky = await self.ensure_sky(now)  # the day's sky first: the reading is built on it (the owner, 2026-10-11)
            weather = await self.ensure_weather(now) if person else None  # v5.10: the real Lviv weather around her day
            birth = parse_birth_date(self.cfg.natal)
            rhythms = format_biorhythms(biorhythms(birth, now.date())) if birth else None
            system, contents = mood_request(self.cfg.name, self.cfg.natal, day, rhythms, sky, weather, person)
            reading = await self._mood_reading(contents, system)
            if not reading:
                log.error("mood of the day failed — none today until a retry")
                self._mood_retry_ms = self.clock() + 600_000
                return
            self.mood = MoodState(day, split_resolution(reading), reading)  # kept for the day even if the log fails
            try:
                self.mood_file.parent.mkdir(parents=True, exist_ok=True)
                # private from birth, like the usage file (review #11): created 0600, a looser old file tightened
                fd = os.open(self.mood_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                        os.fchmod(fd, 0o600)
                    os.write(fd, log_block(day, reading).encode("utf-8"))
                finally:
                    os.close(fd)
            except OSError as exc:  # review #9: no repeated paid call per reply
                log.error("mood log not written (%s) — the mood is kept for today", type(exc).__name__)

    async def _mood_reading(self, contents: str, system: str) -> str | None:
        """The day's reading — None when the call failed or the cap cut it: a cut reading would be logged and reused
        all day, its half-paragraph standing in for the resolution (review #8)."""
        complete = getattr(self.llm, "complete", None)
        if complete is None:  # a seam with only generate() (older fakes)
            return await self.llm.generate(contents, system, max_output_tokens=MOOD_MAX_TOKENS, kind="mood")
        out = await complete(contents, system, max_output_tokens=MOOD_MAX_TOKENS, kind="mood")
        if out is None:
            return None
        text, finish = out
        if finish == "max_tokens":
            log.error("mood of the day cut by the %d-token cap — not kept", MOOD_MAX_TOKENS)
            return None
        return text

    # --- v5.11: events of her life ------------------------------------------------------------------------------
    def events_file(self, day) -> Path:
        return self._dir("events") / f"{day.isoformat()}.md"

    def day_events(self, day) -> list[Event]:
        """The events that fell on `day`, oldest first (none without `events`)."""
        if not self.cfg.can("events"):
            return []
        return list(parse_day(self._read_raw(self.events_file(day))).events)

    def events_between(self, first, last, today) -> str | None:
        """v5.11: the events from `first` to `last`, by day, as a prompt sees them — the last EVENTS_IN_PROMPT."""
        if not self.cfg.can("events"):
            return None
        days = []
        d = first
        while d <= last:
            evs = self.day_events(d)
            if evs:
                days.append((d, evs))
            d += timedelta(days=1)
        kept, n = [], 0
        for d, evs in reversed(days):
            evs = evs[-(EVENTS_IN_PROMPT - n):]
            n += len(evs)
            label = "сьогодні" if d == today else day_label(d, today)
            kept.append(f"{label}:\n{events_for_prompt(evs)}")
            if n >= EVENTS_IN_PROMPT:
                break
        return "\n\n".join(reversed(kept)) or None

    def events_ahead(self, today, until) -> str | None:
        """v5.11: the known events of her story from today up to `until` — never a surprise."""
        life = self.cfg.life
        if not self.cfg.can("events") or life is None:
            return None
        return "\n".join(f"- {'сьогодні' if e.date == today else day_label(e.date, today)}"
                         f"{f', о {e.time}' if e.time else ''}: {e.text}"
                         for e in known_ahead(life, today, until)) or None

    # --- v5.12: her thoughts (`thoughts`) ------------------------------------------------------------------------
    def thoughts_file(self, day) -> Path:
        return self._dir("thoughts") / f"{day.isoformat()}.md"

    def day_thoughts(self, day) -> list[Thought]:
        """Her thoughts of `day`, oldest first (none without `thoughts`). v5.15.4 (the owner, 2026-10-31): never one
        closed in her archive (`GEMINI_CLOSED`) — the day file is never rewritten, so its line's mark decides; an
        unreadable archive leaves them all."""
        return [t for _, t in self.day_thoughts_keyed(day)]

    def day_thoughts_keyed(self, day) -> list[tuple[str, Thought]]:
        """`day_thoughts`, each with its archive key (v5.16: the probe closes a thought by it)."""
        if not self.cfg.can("thoughts"):
            return []
        thoughts = parse_thoughts(self._read_raw(self.thoughts_file(day)))
        keyed = [(thought_key(day.isoformat(), t, n), t) for n, t in enumerate(thoughts)]
        if self.archive is None or not thoughts:
            return keyed
        try:
            closed = {line.key for line in self.archive.by_keys([k for k, _ in keyed]) if line.mark in GEMINI_CLOSED}
        except Exception as exc:  # noqa: BLE001
            log.error("archive: the thoughts' marks were not read (%s)", type(exc).__name__)
            return keyed
        return [(key, t) for key, t in keyed if key not in closed]

    def keep_thought(self, now, thought: Thought) -> None:
        """A thought into her day file (appended, 0600, the folder 0700) and her archive under its place."""
        day = now.date()
        path = self.thoughts_file(day)
        n = len(parse_thoughts(self._read_raw(path)))  # the file's count, closed ones too: its archive key
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                os.fchmod(fd, 0o600)
            os.write(fd, thought_block(thought).encode("utf-8"))
        finally:
            os.close(fd)
        self._archive(thought_key(day.isoformat(), thought, n), int(now.timestamp() * 1000), thought.place, "thought",
                      self.cfg.name, thought.text)

    @property
    def reading_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.reading.json"

    def _reading_state(self, change) -> ReadingState:
        """Load, change, save — with no await between, so the reading and the reflection never undo each other."""
        state = load_reading(self.reading_file)
        change(state)
        save_reading(self.reading_file, state, self.clock())
        return state

    def _mood_today(self, day) -> str | None:
        return person_mood(self.mood.resolution) if self.mood is not None and self.mood.date == day.isoformat() else None

    def _recent_thoughts(self, day, private: bool = False) -> list[str]:
        """Her last thoughts of yesterday and today, for her reading and reflection. Only a reflection on the private
        chat sees her private ones: every other call writes a thought Agora sees (code review #2)."""
        thoughts = [*self.day_thoughts(day - timedelta(days=1)), *self.day_thoughts(day)]
        return [t.text for t in thoughts if private or t.place == "thought"][-RECENT_THOUGHTS:]

    def reading_is_due(self, now) -> bool:
        if not self.cfg.can("thoughts") or self._reading_lock.locked() or self.clock() < self._reading_retry_ms:
            return False
        return reading_due(self.clock(), load_reading(self.reading_file).last_reading_ms, self.reading_every_ms,
                           in_hours(now.hour, self.reading_hours))

    def reflection_is_due(self) -> bool:
        if not self.cfg.can("thoughts") or self.archive is None or self._reflect_lock.locked():
            return False
        return self.clock() >= self._reflect_retry_ms and reflect_due(self.clock(), self._reflect_ms,
                                                                      self.reflect_every_ms)

    # --- v5.20: her private chat in layers — each period due summarized once, by Gemini 3.1 Pro ------------------------
    def talk_is_due(self) -> bool:
        """Checked every `TALK_CHECK_MS` (the idle watcher's ticks are seconds apart), never under a running writer or
        within a failure's back-off."""
        if not self.cfg.can("talk") or self.archive is None or self._talk_lock.locked():
            return False
        now = self.clock()
        return now >= self._talk_retry_ms and now - self._talk_check_ms >= TALK_CHECK_MS

    async def ensure_talk(self) -> None:
        """The oldest period due, summarized and kept (one a check, so the backfill fills a band in minutes); a failure
        backs off for 10 minutes. Spawned by the idle watcher: no answer waits for it."""
        async with self._talk_lock:
            self._talk_check_ms = self.clock()
            try:
                await self._talk_tick()
            except Exception:
                self._talk_retry_ms = self.clock() + 600_000
                log.exception("talk: the summary failed (bot keeps running)")

    async def _talk_tick(self) -> None:
        held = {(r.level, r.start_ms) for r in self.archive.talk_rows()}
        due = periods_due(self.clock(), self.tz, self.archive.private_open_times(), held, self.talk_hour_days,
                          self.talk_4h_days)
        if not due:
            return
        level, start, end = due[0]
        open_n, closed_n = self.archive.private_counts(start, end)
        lines = self.archive.private_between(start, end)  # open to Gemini only: a closed line never reaches it
        finer = [r for r in self.archive.talk_rows(FINER.get(level), start, end)] if level in FINER else []
        from_summaries = covered([x.ts_ms for x in lines], finer)
        items = ([(r.level, r.text) for r in finer if r.text] if from_summaries
                 else [(x.speaker, history_entry(x.text)) for x in lines])
        self._talk_probed = None
        text, left_out = (await self._talk_text(level, items, from_summaries, [0])) if items else ("", 0)
        if text is None:  # a failure, not a prompt-stage block: the period stays due — for a while
            fails = self._talk_fails.get((level, start), 0) + (self._talk_probed is False)  # an outage never counts
            if fails < TALK_FAILS_MAX:
                self._talk_fails[(level, start)] = fails
                self._talk_retry_ms = self.clock() + 600_000
                log.warning("talk: %s %s not written — the call failed (tried again later)", level,
                            iso_hour(start, self.tz))
                return
            self._talk_fails.pop((level, start), None)  # code review v5.20 #2: never the oldest due for good
            text, left_out = "", len(items)
            log.warning("talk: %s %s left empty — %d failures with no prompt-stage block", level,
                        iso_hour(start, self.tz), fails)
        self.archive.talk_put(level, start, end, text, open_n, closed_n, left_out, self.clock())
        log.info("talk: %s %s — %d open, %d closed, %d left out, %d words%s", level, iso_hour(start, self.tz), open_n,
                 closed_n, left_out, len(text.split()), " (from the finer summaries)" if from_summaries else "")

    async def _talk_text(self, level: str, items: list, from_summaries: bool, calls: list) -> tuple[str | None, int]:
        """(the summary — "" when everything blocked —, how many items a block left out); None for a failure to try
        again later. A prompt-stage block (`probe` says so after a failed call) halves the items; a part of at most
        `TALK_SPLIT_MIN`, or past `TALK_CALLS_MAX` calls, is left out. A summary that calls her a model or a bot is
        written again once, then left empty (the persona rule)."""
        system, contents = talk_request(level, self.cfg.name, self.cfg.canon, items, self.talk_words[level],
                                        from_summaries)
        for _ in range(2):
            calls[0] += 1
            text = await self.llm.think(contents, system, model=getattr(self.llm, "reply_model", DIGEST_MODEL),
                                        kind="talk_summary", level="low")
            if text is None or not BANNED_RE.search(text):
                break
            log.warning("talk: a summary named what she is — written again")
        else:
            return "", 0
        if text is not None:
            return cap_words(text, self.talk_words[level]), 0
        probe = getattr(self.llm, "probe", None)
        self._talk_probed = await probe(contents, system) if probe is not None else None
        if self._talk_probed is not True:
            return None, 0
        if len(items) <= TALK_SPLIT_MIN or calls[0] >= TALK_CALLS_MAX:
            return "", len(items)
        half = len(items) // 2
        first, first_out = await self._talk_text(level, items[:half], from_summaries, calls)
        second, second_out = await self._talk_text(level, items[half:], from_summaries, calls)
        if first is None or second is None:
            return None, 0
        return cap_words(" ".join(t for t in (first, second) if t), self.talk_words[level]), first_out + second_out

    async def ensure_reading(self, now) -> None:
        """v5.12: a reading — her time is saved before the calls, so a restart never reads twice; a failure backs off
        for 10 minutes. Spawned by the idle watcher: no answer waits for it."""
        if not self.reading_is_due(now):
            return
        async with self._reading_lock:
            try:
                await self._reading_tick(now)
            except Exception:
                self._reading_retry_ms = self.clock() + 600_000
                log.exception("reading failed (bot keeps running)")

    async def _reading_tick(self, now) -> None:
        start = self.clock()
        before = load_reading(self.reading_file).last_reading_ms
        self._reading_state(lambda s: setattr(s, "last_reading_ms", start))
        day = now.date()
        zaxid = from_citynews(await self.ensure_citynews(now))
        guardian = await self.reading_sources.guardian(self.reading_sections, day)
        seen = load_reading(self.reading_file).seen
        items = shown(fresh(zaxid, seen), fresh(guardian, seen))
        if not items:
            log.info("reading: nothing new")
            return
        mood, recent = self._mood_today(day), self._recent_thoughts(day)
        system, contents = pick_request(self.cfg.name, self.cfg.canon, self.cfg.reading, mood, recent, items,
                                        self.reading_picks)
        raw = await self.llm.generate(contents, system, max_output_tokens=PICK_MAX_TOKENS, kind="reading")
        if raw is None:  # review #1: a failed call reads nothing — the items stay fresh, the reading is tried again
            self._reading_state(lambda s: setattr(s, "last_reading_ms", before))
            raise RuntimeError("the pick call failed")
        self._reading_state(lambda s: s.seen.update({it.id: start for it in items}))  # shown once, never again
        picks = parse_picks(raw, len(items), self.reading_picks)
        log.info("reading: %d items shown, %d picked", len(items), len(picks))
        for i in picks:
            item = items[i]
            body = await self.reading_sources.full_text(item)
            if not body:
                log.info("reading: a %s pick had no text — skipped", item.source)
                continue
            # what she thought before — never a private thought: this one is Agora's to see (code review #2)
            recalled = await self.recall_section(item.title, ("thought",), set())
            system, contents = thought_request(self.cfg.name, self.cfg.canon, mood, recalled, item, body)
            for text in await self._think(contents, system, THOUGHT_MAX_TOKENS, "thought") or []:
                at = local_now(self.clock(), self.tz)
                self.keep_thought(at, Thought(f"{at:%H:%M}", "news", "thought", item.source, text, item.title,
                                              item.link))
                log.info("reading: a thought on a %s item", item.source)

    async def ensure_reflection(self, now) -> None:
        """v5.12: a reflection on each place with new lines — mid-talk too, sending nothing. Spawned by the idle
        watcher: no answer waits for it; a failure backs off for 10 minutes."""
        if not self.reflection_is_due():
            return
        async with self._reflect_lock:
            self._reflect_ms = self.clock()
            try:
                await self._reflect_tick(now)
            except Exception:
                self._reflect_retry_ms = self.clock() + 600_000
                log.exception("reflection failed (bot keeps running)")

    async def _reflect_tick(self, now) -> None:
        day = now.date()
        for place in ("private", "agora"):
            mark = load_reading(self.reading_file).reflected.get(place)
            if mark is None:  # her first reflection there starts from now — never on the whole past
                start = self.clock()
                self._reading_state(lambda s, p=place, m=start: s.reflected.__setitem__(p, m))
                continue
            lines = self.archive.latest(place, REFLECT_LINES, since_ms=mark + 1)
            if not any(line.speaker != self.cfg.name for line in lines):
                continue
            system, contents = reflection_request(self.cfg.name, self.cfg.canon, self._mood_today(day),
                                                  self._recent_thoughts(day, private=place == "private"), place,
                                                  [(line.speaker, line.text) for line in lines])
            texts = await self._think(contents, system, REFLECTION_MAX_TOKENS, "reflection", reflection=True)
            if texts is None:  # review #1: a failed call keeps the mark — the same lines are read next time
                log.info("reflection: the call on %s failed — tried again later", place)
                continue
            last = lines[-1].ts_ms
            self._reading_state(lambda s, p=place, m=last: s.reflected.__setitem__(p, m))
            at = local_now(self.clock(), self.tz)
            for text in texts:
                self.keep_thought(at, Thought(f"{at:%H:%M}", "reflection",
                                              "thought_private" if place == "private" else "thought", place, text))
            log.info("reflection: %d thoughts on %s", len(texts), place)

    async def _think(self, contents: str, system: str, max_tokens: int, kind: str,
                     reflection: bool = False) -> list[str] | None:
        """One call for her thoughts; one regeneration when a thought holds a banned word, then none — logged by
        kind, never by text. None when a call failed (review #1: nothing was read, so nothing is used up)."""
        for attempt in range(2):
            raw = await self.llm.generate(contents, system, max_output_tokens=max_tokens, kind=kind)
            if raw is None:
                log.error("thoughts: the %s call failed", kind)
                return None
            texts = split_reflection(raw) if reflection else [" ".join(raw.split())]
            if texts and all(t and not BANNED_RE.search(t) for t in texts):
                return texts
            log.info("thoughts: a %s held a banned word or nothing — %s", kind,
                     "regenerating" if attempt == 0 else "dropped")
        return []

    def _append_events(self, day, text: str) -> None:
        """Appended, never rewritten; private from birth, like the mood log."""
        path = self.events_file(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                os.fchmod(fd, 0o600)
            os.write(fd, text.encode("utf-8"))
        finally:
            os.close(fd)

    async def ensure_events(self, now) -> None:
        """In her waking hours: her story's events due today, entered once each, then one roll for this hour —
        marked rolled before the call, so a restart never rolls it twice and a missed hour is never caught up. A
        failure backs off for 10 minutes; it never blocks the watcher."""
        if not self.cfg.can("events") or self._events_lock.locked() or self.clock() < self._events_retry_ms:
            return
        if not in_hours(now.hour, self.event_hours):
            return
        async with self._events_lock:
            try:
                await self._events_tick(now)
            except Exception:
                self._events_retry_ms = self.clock() + 600_000
                raise

    async def _events_tick(self, now) -> None:
        day = now.date()
        today = parse_day(self._read_raw(self.events_file(day)))
        life = self.cfg.life
        for due in events_due(life, day) if life else []:
            if due.time is not None and f"{now:%H:%M}" < due.time:
                continue  # review #4: a timed event falls from its time, never told as done in the morning
            if not any(e.source == due.kind and e.text == due.text for e in today.events):
                at = due.time or f"{now:%H:%M}"
                self._append_events(day, block(Event(at, "story", due.kind, due.text)))
                log.info("events: %s event of the story fell at %s", due.kind, at)
        if not hour_due(now, True, today.rolled):
            return
        kind = roll_event(self.rng, self.event_p, self.event_weights)
        self._append_events(day, rolled_marker(now.hour))
        if kind is not None:
            text = await self._write_event(kind, now)
            if text is None:
                log.info("events: no %s event this hour", kind)
            else:
                self._append_events(day, block(Event(f"{now:%H:%M}", kind, "rolled", text)))
                log.info("events: %s event fell at %s", kind, f"{now:%H:%M}")
        await self._weave_news(now, today)

    @property
    def citynews_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.citynews.json"

    async def ensure_citynews(self, now) -> list:
        """The day's Lviv items: the kept ones, refreshed from the feed at most every three hours and merged by link;
        a failed fetch keeps what the day has and is tried again in an hour."""
        day = now.date()
        kept_day, fetched_ms, kept = load_citynews(self.citynews_file)
        items = day_items(kept, day, self.tz) if kept_day == day.isoformat() else []
        fresh = kept_day == day.isoformat() and self.clock() - fetched_ms < CITYNEWS_REFRESH_MS
        if fresh or self.clock() < self._citynews_retry_ms:
            return items
        try:
            fetched = await self.citynews_fetch()
        except Exception as exc:  # noqa: BLE001 — no news is never a blocked event roll
            log.warning("citynews: fetch failed (%s) — trying again in an hour", type(exc).__name__)
            self._citynews_retry_ms = self.clock() + CITYNEWS_RETRY_MS
            return items
        items = day_items([*items, *fetched], day, self.tz)
        save_citynews(self.citynews_file, day.isoformat(), self.clock(), items)
        log.info("citynews: %d items today", len(items))
        return items

    async def _weave_news(self, now, today) -> None:
        """This hour's roll of the day's news: each new item once; a hit touches her life in one of five ways."""
        woven = sum(1 for e in today.events if e.source == "news")
        if woven >= self.city_news_max or self.city_news_p <= 0:
            return
        items = await self.ensure_citynews(now)
        rolled, hit = roll_news(items, today.news, woven, self.city_news_p, self.city_news_max, now, self.rng)
        day = now.date()
        if rolled:
            self._append_events(day, "".join(news_marker(link) for link in rolled))
        if hit is None:
            return
        way = pick_way(self.rng)
        text = await self._write_event(way, now, news=news_ask(hit, way))
        if text is None:
            log.info("events: no news event this hour")
            return
        self._append_events(day, block(Event(f"{now:%H:%M}", way, "news", text, hit.link)))
        log.info("events: a news item touched her life (%s) at %s", way, f"{now:%H:%M}")

    def _event_forbidden(self):
        """Ich and every other member's name forms — an event never names them."""
        return forbidden_re([f for m in self.roster.values() if m.user_id != self.cfg.user_id
                             for f in (m.name, *m.name_forms)])

    async def _write_event(self, kind: str, now, news: str | None = None) -> str | None:
        """One call writes the event inside her life's frame; one regeneration when it names Ich or a member or
        holds a banned word, then none."""
        day = now.date()
        life = self.cfg.life
        cur = current_chapter(life, day) if life else None
        nxt = next_chapter(life, day) if life else None
        plan = self._read(self.plan_paths(day)["day"])
        mood = person_mood(self.mood.resolution) if self.mood is not None and self.mood.date == day.isoformat() else None
        recent = events_for_prompt([*self.day_events(day - timedelta(days=1)), *self.day_events(day)]) or None
        system, contents = event_request(self.cfg.name, self.cfg.canon, kind, now, cur.body if cur else "",
                                         nxt.opening if nxt else None, strip_tags(plan) if plan else None, mood,
                                         recent, news)
        forbidden = self._event_forbidden()
        for _attempt in range(2):
            text = await self.llm.generate(contents, system, max_output_tokens=EVENT_MAX_WORDS * 4, kind="event")
            if text is None:
                log.error("events: the %s event failed", kind)
                return None
            text = cap_words(" ".join(text.split()), EVENT_MAX_WORDS)
            if event_ok(text, forbidden):
                return text
            log.info("events: a %s event named someone from the room or a banned word — %s", kind,
                     "regenerating" if _attempt == 0 else "dropped")
        return None

    def _read_raw(self, path: Path) -> str | None:
        """A torn append (disk full, SIGKILL) may leave bad bytes in the log; the day's block is still found."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    async def reply_later(self, room_id: str, delay_s: float) -> None:
        try:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            for _ in range(3):  # a message that coalesced during generation gets its own pass (code review #1)
                trigger = self._pending_trigger
                if trigger and not self._current(trigger):
                    log.info("silent: moved on")
                    return
                self._owner_seen = self._owner_coalesced
                sent = await self.reply(room_id, trigger, delay_ms=round(delay_s * 1000))
                if self._owner_coalesced != self._owner_seen:  # v4.5 review #4: never swallowed by a slow reply
                    log.info("reply: the owner wrote again while generating — answering it")
                    continue
                if sent or self._pending_trigger == trigger:
                    return
                log.info("reply: a newer message arrived while generating — answering it")
        except Exception:
            log.exception("scheduled reply failed (bot keeps running)")
        finally:
            self._reply_pending = False

    async def reply(self, room_id: str, trigger: str | None = None, at_ms: int | None = None,
                    fallback_for: str | None = None, delay_ms: int | None = None) -> bool:
        """Typing on → Gemini → m.text; silence on failure or PASS; typing reset in finally. An agent-to-agent
        reply (`trigger`) is re-checked before sending (R3): the room may have moved on during generation.
        Returns whether a message was sent."""
        try:
            await self.client.room_typing(room_id, True)
            if self.cfg.can("today"):
                try:
                    await self.ensure_today(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("today block refresh failed (reply continues)")
            if self.cfg.can("mood"):
                try:
                    await self.ensure_mood(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("mood of the day failed (reply continues)")
            memory = self._pick_thesis()
            answered = trigger or (self.last_owner[0] if self.last_owner else "")
            answered_id = answered  # v5.3: the message this line answers — a transcript of the owner's voice is voiced
            move = self.draw_move(answered, local_now(self.clock(), self.tz))
            recalled = None
            if self.archive is not None:  # v5.8: Agora recalls only Agora — the place is the search's, in code
                query = self._texts.get(trigger, "") if trigger else (self.last_owner[1] if self.last_owner else "")
                recalled = await self.recall_section(query, self.agora_places, set(self.history))
            prompt = self.build_prompt(pastlife_section(self.cfg.theses[memory]) if memory is not None else None,
                                       move=move, recalled=recalled)
            lines, effort = None, None
            if self.cfg.type == "assistant":  # v4.5: direct when named, otherwise the philosopher
                answered = (self._texts.get(trigger, "") if trigger
                            else self.last_owner[1] if self.last_owner else "")
                if claude_mode(answered, self.me.name_forms, self.cfg.user_id) == "philosopher":
                    prompt, lines, effort = self.brief(CLAUDE_BRIEF_PHILOSOPHER), self.wide_history, "high"
                    log.info("claude mode: philosopher")
            self._owner_seen = self._owner_coalesced  # the owner's messages so far are in this reply's context
            text = await self._compose(prompt, lines=lines, effort=effort)
            if text is not None and memory is not None and self._verbatim(text, memory):
                log.info("verbatim memory: regenerating once")  # his own words, never the thesis (v4.3)
                text = await self._compose(prompt)
                if text is not None and self._verbatim(text, memory):
                    log.info("silent: verbatim memory")
                    return False
            if text is None:
                return False  # already logged; stay silent
            if same_message(text, self._last_sent):
                log.info("silent: duplicate of my previous message")
                return False
            if self.cfg.type != "persona" and outs_a_persona(text, self.personas):
                log.info("silent: would out a persona")  # the human-belief rule holds for Ada and Bruno (v4.2)
                return False
            if trigger and not self._current(trigger, at_ms):
                log.info("silent: moved on")
                return False
            if fallback_for and not fallback_due(self.timeline, fallback_for):  # a slow answer landed meanwhile
                log.info("silent: the owner was answered meanwhile")
                return False
            self._last_sent = text
            await self.send_line(room_id, text, answered_id, answering=answered_id)
            asked = self._event_at(answered_id) if answered_id else None  # v5.22: how long it waited
            self.record_answer("agora", "matrix", asked[1] if asked else "none", asked[0] if asked else None,
                               delay_ms, "claude" if self.cfg.engine == "claude-sdk" else "gemini",
                               ["voice"] if self.voice_sent else [])
            if memory is not None:
                self.told.add(memory)
            return True
        finally:
            await self.client.room_typing(room_id, False)

    async def _compose(self, prompt: str, max_words: int | None = None, lines: list | None = None,
                       effort: str | None = None, toolset: str | None = None, kind: str = "reply",
                       responder=None, shots: list | None = None) -> str | None:
        """One model call → the line as it would be sent, or None (logged): never half a sentence, never another's
        words, PASS honoured, the creature's word cap applied (`max_words` overrides it: a telegram's joke)."""
        history = list(self.history if lines is None else lines)
        built = _LAST_PARTS.get()  # v5.22: the prompt's parts, when this prompt is the one last built in this task
        parts = {**built[1], "history": len(build_transcript(history))} if built and built[0] is prompt else None
        token = PROMPT_PARTS.set(parts)
        try:
            reply = await (responder or self.responder).respond(Turn(history, prompt, self.reply_max_tokens, kind, effort,
                                                                     toolset))
        finally:
            PROMPT_PARTS.reset(token)
        if reply is None:
            return None  # already logged
        text = reply.text
        backup = responder is not None and responder is self.fallback_responder
        if self.facts_dir is not None:  # v5.8: the «ЗАПАМ'ЯТАЙ: …» line is kept, never sent — on every path
            text, asked = split_marker(text)
            for fact in asked:
                if backup:  # v5.21 (the owner, 2026-11-02): the backup never keeps a fact
                    log.info("facts: dropped (backup)")
                else:
                    self.remember(fact, "asked")
            if not text:
                _silent("only a line to remember")
                return None
        if shots is not None or backup:  # v5.17: only her private answers — Agora's lines are never cut (review #1)
            text, shot = split_photo(text)  # a photo's line is never sent — Gemini's private answer keeps its shot
            if shot is not None:
                if shots is not None:
                    shots.append(shot)
                else:
                    log.info("photo: dropped (backup)")
            if not text:
                _silent("only a photo's line")
                return None
        if reply.finish == "max_tokens":  # the cap cut it: never send half a sentence
            text = trim_to_sentence(text)
            if text is None:
                _silent("cut mid-sentence")
                return None
        others = [n for n in {*self.names.values()} if n != self.cfg.name]
        text = clean_reply(text, self.cfg.name, others)
        if text is None:
            _silent("the reply spoke only for others")
            return None
        text = strip_pass(text)  # PASS alone → silence; text + PASS → the text only
        if text is None:
            _silent("model passed")
            return None
        if self.cfg.type == "creature":  # v4.2: a small vocabulary, enforced
            text = cap_words(text, max_words or self.cat_max_words)
        if self.cfg.can("emotion"):  # v5.9: her words for every text, the tags only for her voice
            words, speech = split_tags(text)
            if not re.search(r"\w", words):  # review #2: `[laughs] … [laughs harder] …` leaves «……», not words
                _silent("only voice tags")
                return None
            return Spoken(words, speech_for(getattr(self.tts, "model", None) or TTS_MODEL, words, speech))
        return text

    def _pick_thesis(self) -> int | None:
        """v4.3 — with CAT_MEMORY_P, the past-life thesis this spoken line retells: chosen by the latest event and
        the message he answers (`pick_memory`), never one already told this run until all are."""
        if not (self.cfg.can("pastlife") and self.cfg.theses) or self.rng() >= self.cat_memory_p:
            return None
        event_id = str(self.timeline[-1][2]) if self.timeline else ""
        last_text = self.history[-1][1] if self.history else ""
        return self._choose_thesis(event_id, last_text)

    def _choose_thesis(self, event_id: str, last_text: str) -> int | None:
        if len(self.told) >= len(self.cfg.theses):
            self.told.clear()  # every thesis told: a new round, no repeats again until it is done (review #8)
        return pick_memory(event_id, last_text, self.cfg.theses, self.told)

    def _verbatim(self, text: str, memory: int) -> bool:
        return shares_span(text, self.cfg.theses[memory].text, VERBATIM_WORDS)

    # --- v4.3: the cat starts conversations -------------------------------------------------------------------------
    @property
    def nudge_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.nudge.json"

    async def maybe_nudge(self) -> bool:
        """After a quiet daytime stretch, one line of his own (`nudge_due`); never while a reply is on its way."""
        if not (self.started and self.cfg.can("nudge")) or self._nudging or self._reply_pending:
            return False
        now_ms = self.clock()
        now = local_now(now_ms, self.tz)
        state = load_nudge_state(self.nudge_file, now.date().isoformat())
        # the silence counts from the later of the room's last message and this start: a restart whose backfill
        # failed (an empty timeline) never nudges at once (review #9)
        marks = [int(self.timeline[-1][1])] if self.timeline else []
        last_room_ms = max([*marks, *([self.started_ms] if self.started_ms is not None else [])], default=None)
        if not nudge_due(now_ms, now, last_room_ms, state.last_ms, state.count, self.nudge_idle_ms,
                         self.nudges_per_day, self.nudge_hours):
            return False
        self._nudging = True
        try:
            state.last_ms = now_ms  # every attempt spaces the next one; only a sent nudge counts
            save_nudge_state(self.nudge_file, state)
            _kind, sent = await self.nudge(now, state.count + 1)
            if sent:
                state.count += 1
                state.sent_ms = now_ms
                save_nudge_state(self.nudge_file, state)
            return sent
        finally:
            self._nudging = False

    @property
    def news_file(self) -> Path:
        return self.memory_file.parent / f"{self.cfg.localpart}.news.json"

    async def maybe_news(self) -> bool:
        """v4.5 — after a quiet stretch, Claude brings one fresh news item that bears on the recent talk (the same
        `nudge_due` with his settings, his own state file); never while a reply of his is on its way."""
        if not (self.started and self.cfg.can("news")) or self._nudging or self._reply_pending:
            return False
        now_ms = self.clock()
        now = local_now(now_ms, self.tz)
        state = load_nudge_state(self.news_file, now.date().isoformat())
        marks = [int(self.timeline[-1][1])] if self.timeline else []
        last_room_ms = max([*marks, *([self.started_ms] if self.started_ms is not None else [])], default=None)
        if not nudge_due(now_ms, now, last_room_ms, state.last_ms, state.count, self.news_idle_ms,
                         self.news_per_day, self.news_hours, gap_ms=self.news_every_ms):
            return False
        self._nudging = True
        try:
            state.last_ms = now_ms
            save_nudge_state(self.news_file, state)
            sent = await self.news()
            if sent:
                state.count += 1
                state.sent_ms = now_ms
                save_nudge_state(self.news_file, state)
            return sent
        finally:
            self._nudging = False

    async def news(self) -> bool:
        """One news item: the news brief over the last `HISTORY_N` lines, his tools, the reply's checks and a
        pre-send check that the room is still quiet. Logs the outcome — never the text."""
        marker = self.timeline[-1][2] if self.timeline else None
        room_id = self.cfg.room_id
        try:
            await self.client.room_typing(room_id, True)
            text = await self._compose(self.brief(CLAUDE_NEWS_BRIEF), toolset="news")
            if text is None:
                log.info("news silent")
                return False
            if same_message(text, self._last_sent):
                log.info("news silent: duplicate of my previous message")
                return False
            if outs_a_persona(text, self.personas):
                log.info("news silent: would out a persona")
                return False
            if (self.timeline[-1][2] if self.timeline else None) != marker:
                log.info("news silent: the room spoke meanwhile")
                return False
            self._last_sent = text
            await self.send_line(room_id, text, f"news:{marker}")
            log.info("news sent")
            return True
        finally:
            await self.client.room_typing(room_id, False)

    async def nudge(self, now, n: int) -> tuple[str, bool]:
        """The day's n-th nudge: its material by kind, the reply's checks, and a pre-send check that the room is
        still quiet. Logs the kind and the outcome — never the text."""
        day = now.date().isoformat()
        kind = nudge_kind(day, n)
        if kind == "horoscope" and self.mood_section(now) is None:
            kind = "memory"  # no horoscope today: a memory instead
        assistant = next((m for m in self.others.values() if m.type == "assistant"), None)
        if kind == "telegram" and assistant is None:
            kind = "memory"  # nobody to send a telegram to
        if kind == "memory" and not (self.cfg.can("pastlife") and self.cfg.theses):
            kind = "command"
        memory, max_words = None, None
        if kind == "memory":
            recent = " ".join(text for _, text in self.history[-5:])
            memory = self._choose_thesis(f"nudge:{day}:{n}", recent)
            prompt = self.build_prompt(pastlife_section(self.cfg.theses[memory]), NUDGE_RULE)
        elif kind == "telegram":
            material = TELEGRAM_MATERIAL.format(name=assistant.name, upper=assistant.name.upper())
            prompt = self.build_prompt(nudge=f"{material} {NUDGE_RULE}")
            max_words = TELEGRAM_MAX_WORDS
        else:
            material = COMMAND_MATERIAL if kind == "command" else HOROSCOPE_MATERIAL
            prompt = self.build_prompt(nudge=f"{material} {NUDGE_RULE}")
        marker = self.timeline[-1][2] if self.timeline else None
        room_id = self.cfg.room_id
        try:
            await self.client.room_typing(room_id, True)
            text = await self._compose(prompt, max_words)
            if text is not None and memory is not None and self._verbatim(text, memory):
                text = await self._compose(prompt)  # his own words, never the thesis
                if text is not None and self._verbatim(text, memory):
                    text = None
                    log.info("nudge silent: verbatim memory")
            if text is None:
                log.info("nudge silent (%s)", kind)
                return kind, False
            if is_purr(text):  # every agent would mark it a purr and nobody would answer (v4.3 review #2)
                log.info("nudge silent: purr")
                return kind, False
            if same_message(text, self._last_sent):
                log.info("nudge silent: duplicate of my previous message")
                return kind, False
            if self.cfg.type != "persona" and outs_a_persona(text, self.personas):
                log.info("nudge silent: would out a persona")
                return kind, False
            if (self.timeline[-1][2] if self.timeline else None) != marker:
                log.info("nudge silent: the room spoke meanwhile")
                return kind, False
            self._last_sent = text
            await self.send_line(room_id, text, f"nudge:{marker}")
            if memory is not None:
                self.told.add(memory)
            log.info("nudge sent (%s)", kind)
            return kind, True
        finally:
            await self.client.room_typing(room_id, False)

    async def summarize(self) -> bool:
        """Previous summary + this session → a new summary file. On failure the
        previous summary and the session are kept for a later retry."""
        async with self._summary_lock:
            snapshot = list(self.session)
            if not snapshot:
                return False
            self.last_attempt_ms = self.clock()
            system, contents = build_summary_request(
                self.cfg.name, self.cfg.canon, self.summary, snapshot, self.summary_max_words,
            )
            text = await self.llm.generate(contents, system, max_output_tokens=self.summary_max_words * 3,
                                           kind="summary")
            # v5.22 (the owner, 2026-11-02: «верни на флеш, але там, де блочиться, роби на 3.1 Pro»): a summary
            # Gemini blocks on GEMINI_MODEL is written once more on a thinking reply model (Кіра's 3.1 Pro), at `low`
            reply_model = getattr(self.llm, "reply_model", None)
            if text is None and LAST_BLOCK.get() is not None and reply_model in THINKING_MODELS:
                if self._summary_pro_blocked == len(snapshot):  # code review v5.22 #2: no new line, no second try
                    log.info("session summary blocked on %s — %s blocked it too, until a new line",
                             getattr(self.llm, "model", "?"), reply_model)
                else:
                    log.info("session summary blocked on %s — written on %s", getattr(self.llm, "model", "?"),
                             reply_model)
                    LAST_BLOCK.set(None)  # only Pro's own block counts below
                    text = await self.llm.think(contents, system, model=reply_model, kind="summary", level="low")
                    self._summary_pro_blocked = len(snapshot) if text is None and LAST_BLOCK.get() else None
            if text is None:
                log.error("session summary failed — keeping the previous one")
                return False
            note, session_part = split_summary(text)
            note = cap_words(re.sub(r"^\s*Нотатка\s*:\s*", "", note), self.summary_max_words)
            save_memory(self.memory_file, note)
            self.summary = note
            self.summary_ms = self.clock()
            self.append_journal(session_part or note)
            self.session = self.session[len(snapshot):]  # keep what arrived meanwhile
            if self.facts_dir is not None:  # v5.8: what she learned about him, beside the summary — the lines an
                fresh = snapshot[min(self._facts_from, len(snapshot)):]  # «Update now» already read are skipped
                self._facts_from = 0
                try:
                    await self.extract_facts(fresh)
                except Exception as exc:  # noqa: BLE001
                    log.error("facts: the extraction failed (%s)", type(exc).__name__)
            return True

    async def idle_watcher(self) -> None:
        """Ends a session after SESSION_IDLE_S of silence (retries a failed summary
        only after another idle period)."""
        interval = max(1.0, min(30.0, self.idle_ms / 4000))
        while True:
            await asyncio.sleep(interval)
            try:
                await self.world_tick()
            except Exception:
                log.exception("world tick failed (bot keeps running)")
            if self.cfg.can("mood"):  # the day's horoscope at the day's start, not at the first spoken line (review #7)
                try:
                    await self.ensure_mood(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("mood of the day failed (bot keeps running)")
            if self.cfg.can("events"):  # v5.11: things happen to her, whether or not anyone talks to her
                try:
                    await self.ensure_events(local_now(self.clock(), self.tz))
                except Exception:
                    log.exception("events failed (bot keeps running)")
            if self.cfg.can("thoughts"):  # v5.12: she reads and thinks off the reply path — never awaited by an answer
                now_local = local_now(self.clock(), self.tz)
                if self.reading_is_due(now_local):
                    self._spawn(self.ensure_reading(now_local))
                if self.reflection_is_due():
                    self._spawn(self.ensure_reflection(now_local))
            if self.talk_is_due():  # v5.20: her private chat summarized by hour, block and week, off the reply path
                self._spawn(self.ensure_talk())
            if self.cfg.can("nudge"):  # v4.3: the cat speaks first
                try:
                    await self.maybe_nudge()
                except Exception:
                    log.exception("nudge failed (bot keeps running)")
            if self.cfg.can("news"):  # v4.5: Claude brings news
                try:
                    await self.maybe_news()
                except Exception:
                    log.exception("news failed (bot keeps running)")
            if self.facts_request is not None:  # AGORA-116: the owner pressed «Update now» in the panel
                try:
                    await self.maybe_update_facts()
                except Exception:
                    log.exception("facts: the update failed (bot keeps running)")
            if self.archive is not None:  # v5.21: the closed talk older than a day loses its text, at 05:00
                try:
                    self.maybe_empty_blocked()
                except Exception:
                    log.exception("archive: the daily emptying failed (bot keeps running)")
            if self.archive is not None:  # v5.8: the archive's meaning search, a batch at a time
                try:
                    await self.embed_tick()
                except Exception:
                    log.exception("archive: embedding failed (bot keeps running)")
            if self.cfg.can("private"):  # v5.6: she writes first in the private chat
                try:
                    await self.maybe_private_nudge()
                except Exception:
                    log.exception("private: writing first failed (bot keeps running)")
            now = self.clock()
            if (
                self.cfg.can("summary")
                and self.session
                and session_ended(self.last_activity_ms, now, self.idle_ms)
                and (self.last_attempt_ms is None or now - self.last_attempt_ms >= self.idle_ms)
            ):
                await self.summarize()

    async def shutdown(self, timeout_s: float = 20.0) -> None:
        """The shutdown summary, bounded so Ctrl+C never hangs."""
        if not self.cfg.can("summary"):
            return
        try:
            await asyncio.wait_for(self.summarize(), timeout=timeout_s)
        except TimeoutError:
            log.error("shutdown summary timed out after %.0fs — keeping the previous one", timeout_s)

    async def run(self) -> None:
        self.summary = load_memory(self.memory_file) if self.cfg.can("summary") else None
        if self.summary:
            self.summary_ms = int(self.memory_file.stat().st_mtime * 1000)
            log.info("%s: last-session memory loaded", self.cfg.localpart)
        await self.login()
        if hasattr(self.responder, "resume_status"):  # v4.4 review #6: a fresh card, a running mute kept
            self.responder.resume_status()
        # First sync: only to obtain next_batch; its events are never handled.
        first = await self.client.sync(timeout=10000, full_state=True)
        if isinstance(first, SyncError):
            raise RuntimeError(f"first sync failed: {first.message}")
        fresh_archive = False
        if self.archive is not None:
            try:
                fresh_archive = self.archive.counts()[0] == 0  # before the context fills it
            except Exception as exc:  # noqa: BLE001 — v5.8 review #4
                log.error("archive: unreadable (%s) — running without it", type(exc).__name__)
                self.archive = None
        try:
            await self.backfill(first.next_batch)  # the context survives a restart
        except Exception:
            log.exception("context backfill failed (starting without it)")
        self.started = True
        self.started_ms = self.clock()
        await self.join_pending_invites()
        if self.cfg.can("private"):
            try:
                await self.start_private(first.next_batch)
            except Exception:
                log.exception("private chat start failed (starting without its history)")
            self.seed_private_from_archive()  # v5.8: both doors, when the archive holds them
        if fresh_archive:  # v5.8: the archive's first fill, beside the sync
            self._spawn(self.archive_backfill(first.next_batch))
        self._spawn(self.world_tick(force=True))  # startup kick: catch up memories and today's plans
        if self.cfg.can("mood"):
            self._spawn(self.ensure_mood(local_now(self.clock(), self.tz)))  # the day's horoscope, early
        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_audio, RoomMessageAudio)  # v5.2: remembered, never answered
        self.client.add_event_callback(self.on_invite, InviteMemberEvent)
        log.info("%s: entering sync_forever", self.cfg.localpart)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        sync_task = asyncio.create_task(self.client.sync_forever(timeout=30000))
        watcher = asyncio.create_task(self.idle_watcher())
        stop_task = asyncio.create_task(stop.wait())
        tasks = [sync_task, watcher, stop_task]
        if self.telegram is not None:  # v5.7: her bot, polled beside the sync
            if self.cfg.can("fallback") and not await self.telegram.set_commands(self.telegram_owner):
                log.warning("telegram: the command list was not set")  # v5.14: the owner's chat only
            log.info("telegram: polling")
            tasks.append(asyncio.create_task(self.telegram_poll()))
        await asyncio.wait({sync_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        log.info("%s: stopping — writing the session summary", self.cfg.localpart)
        for t in tasks:
            t.cancel()
        await self.shutdown()
        await self.client.close()
        log.info("%s: stopped", self.cfg.localpart)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: uv run agents/agent.py agents/<name>.toml", file=sys.stderr)
        raise SystemExit(2)
    cfg = load_config(sys.argv[1])
    setup_logging(cfg.localpart)
    lock = acquire_lock(cfg.lock_file)  # held until the process exits (v3.2)
    if lock is None:
        log.error("%s: another instance is running (pid %s) — exiting", cfg.localpart, lock_holder(cfg.lock_file))
        raise SystemExit(1)
    settings_start(os.environ, cfg.memory_file.parent, cfg)  # v4.7: the panel's overrides, before anything reads them
    if cfg.type == "herald":  # v5.1: Hermes — his own process, no turns, never a word in the room
        from agents.herald import Herald
        asyncio.run(Herald(cfg).run())
        return
    try:
        agent = Agent(cfg)
    except AuthRefused as exc:  # v4.4: the names of what tripped it, never a value
        log.error("%s: %s", cfg.localpart, exc)
        write_status(cfg.memory_file.parent / f"{cfg.localpart}.ratelimit.json",
                     ClaudeStatus(auth=f"refused: {exc}", updated_at=int(time.time())))
        raise SystemExit(1) from None
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
