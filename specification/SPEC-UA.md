# matrix-agora — специфікація PoC

Власний Matrix-сервер у домашній мережі, де в одній кімнаті розмовляють **ти і два прості LLM-агенти** (Gemini 2.5 Flash). Агенти бачать і тебе, і одне одного; ніхто ззовні писати їм не може.

Мета PoC — перевірити саму схему (сервер → клієнт → боти → розмова втрьох) перед тим, як підключати до неї справжніх агентів на кшталт Лілі. Простота важливіша за повноту.

## 1. Архітектура

```
 ┌──────────────── Ubuntu server 192.168.1.197 ────────────────┐
 │  Docker: continuwuity (Matrix homeserver)  :8008  (HTTP, LAN) │
 │  server_name = agora.lan, федерація OFF, шифрування OFF       │
 └───────────────▲──────────────────▲──────────────────▲────────┘
                 │ Client-Server API (http://192.168.1.197:8008)
     ┌───────────┴───┐     ┌────────┴────────┐  ┌──────┴──────────┐
     │ Element Desktop│     │ agent "Ада"     │  │ agent "Бруно"   │
     │ (ти, @me)      │     │ Python + nio    │  │ Python + nio    │
     └────────────────┘     │ → Gemini API    │  │ → Gemini API    │
                            └─────────────────┘  └─────────────────┘
                 Mac (клієнт і обидва агенти працюють тут)
```

- **Сервер:** [Continuwuity](https://continuwuity.org) — Matrix homeserver на Rust: один контейнер, вбудована БД (RocksDB), без Postgres.
- **Клієнт:** Element Desktop на Mac. Саме Desktop, а не app.element.io: веб-версія працює по HTTPS і не під'єднається до HTTP-сервера в LAN (mixed content).
- **Агенти:** два процеси Python на Mac, один і той самий код, різні конфіги (ім'я, персона, акаунт). Бібліотеки `matrix-nio` (Matrix) + `google-genai` (Gemini).
- **TLS:** немає, бо це PoC у домашній мережі. Доступ ззовні — тільки пізніше через Tailscale, порт у роутері **не відкривати**.

Імена агентів «Ада» і «Бруно» — умовні, заміни на свої.

## 2. Фаза 0 — сервер (Ubuntu, 192.168.1.197)

### Задачі

1. Встановити Docker Engine + compose plugin (офіційний репозиторій Docker для Ubuntu).
2. Створити `~/matrix-agora/server/docker-compose.yml` (у репозиторії — `server/docker-compose.yml`):

   ```yaml
   services:
     homeserver:
       image: forgejo.ellis.link/continuwuation/continuwuity:latest
       # дзеркало, якщо основний реєстр недоступний: ghcr.io/continuwuity/continuwuity:latest
       restart: unless-stopped
       ports:
         - "8008:8008"
       volumes:
         - db:/var/lib/continuwuity
       environment:
         CONTINUWUITY_SERVER_NAME: agora.lan        # НЕ можна змінити без стирання БД
         CONTINUWUITY_DATABASE_PATH: /var/lib/continuwuity
         CONTINUWUITY_ADDRESS: 0.0.0.0
         CONTINUWUITY_PORT: 8008
         CONTINUWUITY_ALLOW_FEDERATION: "false"     # повністю закритий від мережі Matrix
         CONTINUWUITY_ALLOW_ENCRYPTION: "false"     # жодних E2EE-кімнат — ботам так простіше
         CONTINUWUITY_ALLOW_REGISTRATION: "true"    # тимчасово, на фазу 2
         CONTINUWUITY_REGISTRATION_TOKEN: "${REGISTRATION_TOKEN}"
   volumes:
     db:
   ```

   `REGISTRATION_TOKEN` лежить у `server/.env` поруч (довгий випадковий рядок, `openssl rand -hex 24`), у git не потрапляє.
3. Firewall: `sudo ufw allow from 192.168.1.0/24 to any port 8008 proto tcp` — порт доступний лише з домашньої мережі.
4. `docker compose up -d`, перевірити логи: `docker compose logs -f homeserver`.

`server_name` — це лише «домен» в іменах користувачів (`@ada:agora.lan`). DNS для нього не потрібен, бо клієнти ходять на `http://192.168.1.197:8008` напряму. Якщо IP сервера колись зміниться, зміниться тільки URL у конфігах, імена лишаться.

### DoD

- З Mac: `curl http://192.168.1.197:8008/_matrix/client/versions` повертає JSON зі списком версій.
- `curl http://192.168.1.197:8008/_matrix/federation/v1/version` не відповідає як федерація (федерація вимкнена).
- Після `sudo reboot` сервера контейнер піднімається сам.

## 3. Фаза 1 — клієнт (Mac)

### Задачі

1. `brew install --cask element`.
2. Element → Create account → **Edit** homeserver → `http://192.168.1.197:8008` → зареєструвати себе (`me`) з `REGISTRATION_TOKEN`. Перший акаунт на сервері автоматично стає адміном і отримує запрошення в admin room.

### DoD

- Ти залогінений як `@me:agora.lan`, бачиш admin room.

## 4. Фаза 2 — акаунти ботів і кімната

### Задачі

1. Створити акаунти `ada` і `bruno` — або через реєстрацію з токеном (вийти/залогінитися в Element, або `curl` на `/_matrix/client/v3/register`), або командою в admin room (`!admin users create-user ada`).
2. **Закрити реєстрацію:** `CONTINUWUITY_ALLOW_REGISTRATION: "false"`, `docker compose up -d`. Відтепер нові акаунти створює тільки адмін.
3. В Element створити кімнату **«Агора»**: private (invite-only), шифрування вимкнене (воно й так заборонене на сервері). Запросити `@ada:agora.lan` і `@bruno:agora.lan`.
4. Записати `room_id` кімнати (Room settings → Advanced, вигляд `!xxxx:agora.lan`).

### DoD

- Спроба зареєструвати новий акаунт без адміна — відмова.
- У кімнаті ти + два запрошення (боти приймуть їх у фазі 3).

## 5. Фаза 3 — echo-бот (Matrix без LLM)

Мета — перевірити Matrix-частину окремо від LLM.

### Структура проєкту

```
matrix-agora/
  SPEC.md
  README.md
  pyproject.toml            # uv; deps: matrix-nio, google-genai, python-dotenv
  server/
    docker-compose.yml
    .env.example            # REGISTRATION_TOKEN=
  agents/
    agent.py                # один код для обох агентів
    ada.toml                # name, user_id, persona, …
    bruno.toml
  .env.example              # HOMESERVER, ROOM_ID, OWNER, ADA_PASSWORD, BRUNO_PASSWORD, GEMINI_API_KEY
  state/                    # access token + device_id кожного бота (gitignored)
```

Запуск: `uv run agents/agent.py agents/ada.toml` (і так само для `bruno.toml` в окремому терміналі).

### Поведінка

1. **Логін:** перший запуск — логін паролем, `access_token` + `device_id` зберегти в `state/<name>.json`. Наступні запуски — з токена (інакше кожен старт створює новий «пристрій» на сервері).
2. **Інвайти:** приймати (`join`) **лише** запрошення від `OWNER` у кімнату `ROOM_ID`. Інші — `leave`/ігнор.
3. **Старт без минулого:** перший `sync` лише для отримання `next_batch` — події з нього **не обробляти** (інакше після рестарту бот відповість на всю історію). Далі — `sync_forever`.
4. **Фільтр повідомлень** (`RoomMessageText`), обробляти тільки якщо всі умови виконані:
   - `room.room_id == ROOM_ID`;
   - `event.sender != власний user_id`;
   - `event.sender ∈ {OWNER, user_id іншого агента}` — **allowlist у коді**, як `LUMI_TELEGRAM_ALLOWLIST` у Лілі.
5. **Echo:** відповісти `"<name> чує: <text>"`.

### DoD

- Ти пишеш у «Агору» — обидва боти відповідають echo.
- Рестарт бота — він не відповідає на старі повідомлення і не створює новий device.
- Повідомлення в іншій кімнаті / в DM бота — ігнорується (видно в лозі як `ignored`).

## 6. Фаза 4 — LLM (Gemini 2.5 Flash)

### Задачі

1. Замінити echo на виклик Gemini через `google-genai` (async):

   ```python
   from google import genai
   from google.genai import types

   client = genai.Client()  # бере GEMINI_API_KEY з оточення
   resp = await client.aio.models.generate_content(
       model="gemini-2.5-flash",
       contents=transcript,  # див. нижче
       config=types.GenerateContentConfig(
           system_instruction=persona,
           max_output_tokens=400,
           thinking_config=types.ThinkingConfig(thinking_budget=0),  # швидше й дешевше для чату
       ),
   )
   reply = resp.text
   ```

2. **Контекст:** кожен агент тримає в пам'яті останні `HISTORY_N` (напр. 30) повідомлень кімнати з `sync` — **включно з власними та іншого агента**. У модель вони йдуть одним текстом `"Ім'я: текст"` по рядку + інструкція: «Ти — <name>. Відповідай лише від себе, коротко, без префікса з іменем».
3. **Персона** — у `<name>.toml`: 3–5 речень характеру, щоб агенти помітно відрізнялися.
4. **Typing:** `room_typing(room_id, True)` перед викликом Gemini, `False` після.
5. **Помилки:** якщо Gemini впав або повернув порожнє — лог + коротке службове повідомлення не надсилати (мовчати); бот не падає.
6. Надсилати як `m.text` (не `m.notice`) — інакше інший агент може вважати це службовим повідомленням.

### DoD

- Ти пишеш — кожен агент відповідає у своєму характері, з урахуванням попередніх реплік.
- Поки агент думає, в Element видно «друкує…».
- Без `GEMINI_API_KEY` або з невалідним — бот живий, пише помилку в лог.

## 7. Фаза 5 — розмова втрьох і захист від зациклення

Агенти бачать одне одного, тож без правил вони відповідатимуть одне одному нескінченно.

### Правила, хто відповідає

1. **Твоє повідомлення:**
   - згадує одного агента (ім'я або mention) — відповідає **тільки він**;
   - нікого не згадує — відповідають **обидва**, кожен після випадкової затримки 1–4 с (щоб не говорити одночасно, і другий уже бачив репліку першого в історії).
2. **Повідомлення іншого агента:** відповідати, лише якщо `bot_streak < MAX_BOT_TURNS` (за замовчуванням **2**), і з імовірністю `BOT_REPLY_P` (напр. 0.5) — щоб розмова не була механічною.
   - `bot_streak` — кількість повідомлень агентів поспіль **після твого останнього** повідомлення. Обидва агенти рахують його з однієї й тієї ж стрічки кімнати, тож рахунок узгоджений без жодної координації.
   - Твоє повідомлення скидає `bot_streak` у 0.
3. Агент може вирішити «тут нічого додати»: якщо модель повернула рівно `PASS`, нічого не надсилати (дозволити це в інструкції).

### Налаштування

У `.env` / toml: `MAX_BOT_TURNS`, `BOT_REPLY_P`, `HISTORY_N`, `REPLY_DELAY_S`.

### DoD

- Ти пишеш одне повідомлення без згадок — максимум `2 + MAX_BOT_TURNS` реплік агентів, далі тиша, доки ти не напишеш знову.
- «Адо, що думаєш?» — відповідає тільки Ада.
- Агенти посилаються на репліки одне одного (видно, що вони бачать одне одного).

## 8. Безпека (підсумок)

| Загроза | Захист |
| --- | --- |
| Хтось реєструється на сервері | Реєстрація вимкнена після фази 2; токен тільки в `server/.env` |
| Хтось з інтернету | Порт 8008 не прокинутий у роутері; ufw — тільки `192.168.1.0/24`; федерація вимкнена |
| Хтось пише ботам (DM, інша кімната) | Allowlist у коді: тільки `ROOM_ID` + `{OWNER, інший агент}` |
| Витік ключів | `.env`, `server/.env`, `state/` — у `.gitignore`; токени й тексти повідомлень не логуються |
| Агенти спалюють кредити, балакаючи між собою | `MAX_BOT_TURNS`, `BOT_REPLY_P`, `max_output_tokens` |

HTTP без TLS у LAN — свідомий компроміс PoC: паролі йдуть відкритим текстом у домашній мережі. Перед будь-яким доступом ззовні — Tailscale (або reverse proxy з TLS).

## 9. Поза межами PoC

- E2EE, голос/відео (Element Call + LiveKit), медіа (картинки, голосові).
- Пам'ять між рестартами (історія тільки з `sync` у пам'яті).
- Підключення Лілі: окремий Matrix-демон на її шині `inbox`/`outbox` (як нинішні Telegram-демони) — наступний крок, якщо PoC вдалий.
- Тести: для PoC достатньо ручних DoD-перевірок; юніт-тестами варто покрити тільки чисту логіку «хто відповідає» (фільтр + `bot_streak`), бо вона без мережі.
