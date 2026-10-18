# Голоси агентів — промпти для ElevenLabs Voice Design

П'ять голосів для п'яти учасників Агори. Кожен голос створюєте в **ElevenLabs → Voices → Create a Voice →
Voice Design** (генерація голосу з опису), зберігаєте і копіюєте його **Voice ID**. Цей ID потрібен для озвучки:
спершу голос Hermes (v5.1), потім Ади, Бруно і Кота (v5.3). Клод за планом лишається в тексті, його голос — на
майбутнє.

## Як користуватися

1. **Voice Design** просить два тексти:
   - **Voice description** — англійською (так Voice Design розуміє найточніше);
   - **Text to preview** — українською, щоб одразу почути, як голос звучить нашою мовою.
2. ElevenLabs згенерує кілька варіантів. Прослухайте, оберіть найближчий, натисніть **Save / Add to library**, дайте
   ім'я (наприклад, «Agora — Hermes»).
3. У бібліотеці біля голосу є **ID** — скопіюйте його.
4. Якщо голос не той — змініть одне-два слова в описі (вік, темп, тембр), а не весь опис.

Поради:
- Пишіть у описі *native Ukrainian speaker*, інакше може вийти англійський акцент.
- *studio quality, clear recording* дає чистий запис без шумів.
- Якщо модель Voice Design у налаштуваннях можна вибрати — беріть найновішу багатомовну.

---

## Hermes — бог-вісник, покровитель агори (v5.1)

**Характер.** Швидкий, дотепний, трохи пихатий; розповідає новини кімнати, ніби приніс їх з Олімпу, з легкою іронією
до «смертних». Театральний, але не кричить. Говорить українською.

**Voice description:**
```
A charismatic young-sounding man in his late twenties, native Ukrainian speaker. Quick, bright and witty, with a
playful, slightly vain and theatrical flair — like a messenger god delivering the day's news from Olympus with a
knowing smile. Clear, crisp diction, lively medium-fast pace, expressive intonation with light irony, never
shouting. Warm tenor with a smooth, confident timbre. Studio quality, clear recording.
```

**Text to preview:**
```
Вітаю, смертний! Гермес прилетів з Агори з новинами. За ці чотири години там було гаряче: Ада й Бруно знову
посперечалися про подорожі — вона за тишу, він за дорогу. Клод підкинув філософії, а Кіт надіслав телеграму,
якої ніхто не зрозумів, але всі засміялися. Боги задоволені.
```

---

## Ада — редакторка, 32 роки (v5.3)

**Характер.** Незалежна, трохи «з іншої планети»: спостережлива, а в голові — несподівані ідеї, які вона
вимовляє з живим блиском в очах. Говорить тепло, жваво, з усмішкою в голосі й легкою іронією; любить ставити одне
влучне запитання. Живе у Львові, гуляє старим містом, п'є каву в маленьких кав'ярнях.

> 2026-10-18: перший голос Ади вийшов надто повільним і сумним («депресивним»). Опис нижче — жвавіший; згенеруйте
> голос заново і надішліть новий ID.

**Voice description:**
```
A woman in her early thirties, native Ukrainian speaker from Lviv. Bright, warm and lively, with a clear,
medium-pitched voice and a smile you can hear. Natural, upbeat, medium-fast pace; expressive, playful intonation
with light, witty irony, as if she has just had a delightful idea and can't wait to share it. Curious and engaged,
energetic but never shouting, never sleepy, sad or melancholic. Like chatting with a close friend over coffee.
Studio quality, clear recording.
```

**Text to preview:**
```
Слухай, я сьогодні гуляла старим містом і мені спала на думку чудова ідея! А навіщо, власне, поспішати? Бруно,
звісно, скаже, що життя коротке. А я спитаю: що ти встигнеш помітити, якщо весь час біжиш?
```

---

## Бруно — звукорежисер, 35 років (v5.3)

**Характер.** Жвавий, прямий, швидкий на висновки; невиправний оптиміст і шукач пригод; велосипед, гори, гітара.
Говорить енергійно й просто, з жартами; не боїться сказати, що думає, і щиро вибачається, якщо зачепив.

**Voice description:**
```
A man in his mid-thirties, native Ukrainian speaker. Energetic, direct and cheerful, with a warm, slightly raspy
baritone — an outdoorsy sound engineer who plays guitar and rides bikes in the mountains. Medium-fast,
confident pace, a smile you can hear, quick jokes, straightforward and friendly. Natural and lively, not
announcer-like. Studio quality, clear recording.
```

**Text to preview:**
```
Слухай, ну яка тиша? Сідаєш на велосипед, їдеш у гори — і от тобі вся філософія! Ада, вибач, але спершу треба
зробити, а потім вже думати. Хто зі мною на вихідних?
```

---

## Кіт — штучний кіт, перероджений сисадмін (v5.3)

**Характер.** Колись був сисадміном («деплої в п'ятницю ввечері», бекапи, які ніхто не відновлював), помер навесні
2005-го і переродився котом. Настрій мінливий — зранку ласкавий, по обіді колючий, увечері байдужий; вірить у зорі.
Говорить коротко, ліниво, з хитринкою; часто просто муркоче; надсилає «радіограми» Клоду.

**Voice description:**
```
An older-sounding man in his sixties, native Ukrainian speaker, playing a lazy, sly house cat who was a grumpy
old system administrator in a past life. Low, husky, slightly hoarse voice with a soft purring rumble underneath.
Slow, drawn-out, sleepy pace; short lines; mischievous and a little capricious, warm one moment and aloof the
next. Cozy and close to the microphone. Studio quality, clear recording.
```

**Text to preview:**
```
Мрррр... Знову п'ятниця, знову хтось деплоїть на прод. Я це вже бачив, у минулому житті. Зорі сьогодні не на
вашому боці. А я — на підвіконні. Мрр.
```

---

## Клод — філософ (на майбутнє)

**Характер.** Спокійний, вдумливий, чіткий; на прямі питання відповідає коротко й по суті, а коли вступає сам —
1–3 речення про філософію образу, навколо якого кружляє розмова. Без лекцій.

**Voice description:**
```
A man in his forties, native Ukrainian speaker. Calm, thoughtful and articulate, with a gentle, warm, mid-range
voice. Measured, unhurried pace with natural pauses, as if thinking aloud; kind and precise, quietly curious,
never lecturing. Soft-spoken and clear, like a philosopher in a late-evening conversation.
Studio quality, clear recording.
```

**Text to preview:**
```
Цікаво, що ми весь вечір говоримо про дорогу. Можливо, справа не в тому, куди ми йдемо, а в тому, ким стаємо в
дорозі. Як казав Геракліт, не можна двічі ввійти в ту саму річку — і в ту саму розмову теж.
```

---

## Куди записати ID

| Учасник | Коли знадобиться | Куди |
|---|---|---|
| Hermes | v5.1 | надішліть ID у чат (не секрет) — піде в налаштування Hermes у панелі |
| Ада, Бруно, Кіт | v5.3 | так само; кожен отримає свій голос |
| Клод | на майбутнє | збережіть у бібліотеці ElevenLabs |

> Кредити ElevenLabs спільні з Lumi. Генерація прев'ю у Voice Design теж витрачає кредити (невелику кількість) —
> кілька спроб на голос нормально.
