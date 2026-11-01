# fal.ai — the key for Кіра's кружечок (v5.18)

From v5.18 Кіра records a кружечок (Telegram's round video message) in which she says her answer in her own voice.
The video is made by **VEED Fabric 1.0 on fal.ai**: her selfie and the audio of her answer go in, a video of her
face speaking that audio comes out, in about 40 s. The clips without speech run on Google's key and need nothing here.

**The price and the choice** (`VIDEO_NOTE_MODEL`):
- `veed/fabric-1.0` is $0.08 a second of video (the default, the owner's choice after the live test of 2026-11-01);
- Kling AI Avatar v2 stays a choice: `fal-ai/kling-video/ai-avatar/v2/standard` at $0.056 a second and `…/v2/pro` at
  $0.115. It took about 10 minutes for 18 s of her voice, past the agent's 10-minute wait, so most of its кружечки
  never came;
- a кружечок is at most 30 s (`VIDEO_NOTE_MAX_S`), so at most $2.40 on Fabric; one of 15 s costs about $1.20.

## 1. The account

1. Open [fal.ai](https://fal.ai) and sign up with one of the accounts it offers.
2. Agree to the terms. No team is needed: the key belongs to the account that creates it.

## 2. Credits

fal works on **prepaid credits**. Each call draws them down, and credits also set how many calls may run at once.

1. Open [fal.ai/dashboard/billing](https://fal.ai/dashboard/billing).
2. Add a card and buy credits. **$10 is enough to start:** about eight кружечки of 15 s.
3. Leave any automatic top-up off at first. When the credits run out, her кружечок fails and her usual voice note goes
   instead, so nothing is lost.

The same page shows the overall spend and the invoices. From v5.18 our token report shows the kind `video_note`, with
its seconds and cost.

## 3. The key

1. Open [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys).
2. Click **Create Key** and name it `matrix-agora-kira`.
3. Pick the preset **API**: it calls models and nothing else.
4. Copy the key at once. The page shows it only this one time.

## 4. Into `server/kira.env`

`server/kira.env` is gitignored, and `server/deploy.sh` syncs it to the host as 0600. Only the `kira` service reads it.

1. Open `server/kira.env` in the editor and add at the end:

   ```
   # v5.18: her кружечок — VEED Fabric 1.0 on fal.ai (fal.ai/dashboard/keys, preset API). Unset: no кружечок.
   FAL_KEY=<the key>
   ```

2. Save. Never paste the key into a chat, a terminal command, an issue or a commit.
3. Check that it is set, without showing it:

   ```bash
   grep -q '^FAL_KEY=.' server/kira.env && echo set
   ```

## 5. Check the key (free)

This asks fal for the model's price, so it spends nothing. `printf` is a shell builtin and curl reads the header from
a file descriptor, so the key never appears in a process's argv:

```bash
curl -s -H @<(printf 'Authorization: Key %s\n' "$(sed -n 's/^FAL_KEY=//p' server/kira.env)") \
  "https://api.fal.ai/v1/models/pricing?endpoint_id=veed/fabric-1.0"
```

- **The key works:** a JSON answer with the billing unit and the unit price.
- **The key is wrong:** `{"error":{"type":"authorization_error",…}}` (HTTP 401). Copy it again, or create a new one.

## 6. The deploy

Nothing to do now. No code reads `FAL_KEY` before v5.18, and the v5.18 deploy syncs `server/kira.env` to the host.

## What fal receives and keeps

- **What it receives,** for each кружечок:
  - her selfie, made for it;
  - the audio of her answer.
- **What it never receives:**
  - the owner's words;
  - her archive;
  - the backup's talk.
- **How it receives them:** Fabric takes no data inside the request, so both files are put on fal's storage first,
  each under a long unlisted link, and the job names those links. The key goes to fal's queue and upload hosts only,
  never to the storage itself, and no link goes into a log.
- **What it returns:** the video as a link on fal's storage. The agent downloads it at once and keeps the file in
  `state/kira.videos/` (0600). The link never goes into a log.
- **The safety checker:** fal's checker is on by default, and turning it off needs fal's approval. A blocked кружечок
  turns into her voice note.

## If the key leaks

1. Delete it at [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys).
2. Create a new one (step 3).
3. Replace the line in `server/kira.env` and deploy (`server/deploy.sh --dry-run`, then `server/deploy.sh`).
