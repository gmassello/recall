---
name: recall-record-video
description: >
  Record or re-record the recall submission video: prepare the demo state, verify the
  three-ticket story end to end, drive Chrome through the choreography against the
  narration timings, and clean up between takes. Covers the traps this has already hit
  (Gemini free-tier quota exhaustion showing up as agent_error, the quality-score tuning
  that decides whether ticket 2 cites the fresh postmortem, clicking queue rows by
  coordinates, RTK contaminating a gh secret). Use it to record a take, to prepare or
  reset the demo, or when the deployed agent starts answering agent_error during a demo.
---

# Recording the recall demo video

`VIDEO.md` (repo root, not in git) is the *human* guide: tooling, audio pipeline, upload.
`docs/video-script.md` is the shot list. This skill is the *operational* runbook for the
Claude side: exact state resets, verification, choreography and the failure catalogue.
Read those two files first; this one assumes their content.

Division of labour: **Claude cannot capture video or audio.** The human records
(`Cmd+Shift+5`, window mode, mic off) and plays `video/out/narration.wav` on headphones;
Claude drives Chrome. Window-mode capture records only the Chrome window — the terminal
and this chat never appear on camera, so the human can type mid-take.

## Prerequisites (check before promising anything)

| What | Check | Fix |
|---|---|---|
| ffmpeg | `which ffmpeg` | `brew install ffmpeg` |
| Ava (Premium) voice | `say -v '?' \| grep Ava` | System Settings → Accessibility → Spoken Content → Manage Voices (human does it, ~1 GB) |
| Chrome extension permission | drive any click on the CloudFront page | human enables the domain in the extension |
| **Gemini quota** | see below | paid/prepaid key, or wait for the daily reset (midnight PT) |

### The Gemini quota trap

The free tier allows **20 generate requests per day per model per project**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). One `Diagnose` ≈ 3 requests, so a
rehearsal plus a take plus verification burns the day. Symptoms: the SSE stream ends in
`agent_error` after the first evidence step; plain `POST /handle` returns 500. Confirm in
CloudWatch **Logs Insights** (the log-events console view often fails with "Unable to load
content"; Insights works):

```
SOURCE logGroups(namePrefix: ["/aws/lambda/recall-api"], class: "STANDARD") START=-3600s END=0s
| fields @timestamp, @message | filter @message like /Error/ | sort @timestamp desc | limit 40
```

`429 RESOURCE_EXHAUSTED` → quota. The deployed key lives in the repo secret
`GEMINI_API_KEY`; the paid key (US$10 prepaid, hard-capped) belongs to the AI Studio
project `gen-lang-client-0910002935` (key suffix `t6yA`, same one as `backend/.env`).

**Never set the secret through a grep pipeline.** The RTK hook rewrites `grep` and its
"N matches in M files" banner ends up *inside* the secret, which the Lambda then sends as
an HTTP header → `httpx.LocalProtocolError: Illegal header value` on every Gemini call.
Use Python:

```bash
cd backend && .venv/bin/python -c "
import re, sys
key = re.search(r'^GEMINI_API_KEY=(.*)$', open('.env').read(), re.M).group(1).strip().strip('\"')
sys.stdout.write(key)" | gh secret set GEMINI_API_KEY -R gmassello/recall
gh workflow run deploy.yml --ref main   # the secret only takes effect on deploy
```

## Keys and URLs

- App: `https://d2n13wfb8jv9v.cloudfront.net` · API: the Lambda Function URL from the last
  deploy log (`gh run view <id> --log | grep -o 'https://[a-z0-9]*\.lambda-url[^ ]*'`).
- The demo API key ships in the public JS bundle by design. `video/reset-demo.py` has a
  `discover()` that extracts both the API base and the key — reuse it instead of
  hand-rolling regexes. Beware: the bundle shape has already changed once (object-literal
  headers → `Headers.set("X-API-Key",…)`) and stale regexes fail *silently* as 401s on
  every protected call.

- The SSE endpoint takes the key as `?key=<demo key>` (EventSource cannot send headers).

## Demo state reset (idempotent, run before any take)

**Use the script — it implements everything below and verifies it:**

```bash
backend/.venv/bin/python video/reset-demo.py            # reset + verify (green/red report)
backend/.venv/bin/python video/reset-demo.py --check    # verify only, change nothing
```

Do not record until its report is all green. The rest of this section explains what it
does and why, and doubles as the manual fallback (API calls carry the demo key as
`-H "X-API-Key: $KEY"`; the quality tuning is direct SQL via psycopg + `backend/.env`).

1. **Memory = 25 seed incidents.** `GET /memory`, delete every row with `source != "seed"`
   (`DELETE /memory/{id}`). Verify: 25 rows, all seed.
2. **Quality tuning — this decides the ticket-2 beat.** With `w_quality = 0.15`, the
   "current procedure" incident beats the freshly written postmortem whenever its
   `quality_score` ≳ 0.34 (the postmortem lands ~0.025 closer in distance but carries no
   quality). Feedback votes during testing had inflated it to 0.6 and the beat failed.
   Verified working value: **0.1**.

   ```bash
   cd backend && set -a && source .env && set +a && .venv/bin/python -c "
   import psycopg, os
   with psycopg.connect(os.environ['DATABASE_URL']) as conn:
       conn.execute(\"UPDATE incidents SET quality_score = 0.1 WHERE title = 'Reboot loop after an update: current procedure'\")
       conn.execute(\"UPDATE incidents SET quality_score = 0.0, times_helpful = 0 WHERE title = 'Everything slow because of browser adware'\")"
   ```
3. **Tickets.** Delete leftovers from previous takes: any ticket titled
   `PC restarts over and over…` (ticket 1 is created ON CAMERA only) and any duplicates of
   tickets 2/3. Then make sure exactly one of each exists (create via `POST /tickets`,
   no key needed):

   - **Ticket 2** — service `software-pc`, severity `high`
     - title: `Another PC in an endless restart loop after the same update`
     - description: `Boots to the logo and restarts, over and over. Same as the one we fixed earlier today.`
   - **Ticket 3** — service `software-phone`, severity `medium`
     - title: `Android app keeps closing right after the latest OS update`
     - description: `Since updating the phone OS, the banking app closes by itself a few seconds after opening. Reinstalling did not help.`

   Tickets 2/3 must have **no saved diagnosis** — if a previous take diagnosed them,
   delete and recreate them (deleting a ticket cascades its diagnosis).

   **Ticket 1** (typed on camera at the 0:42 beat) — service `software-pc`, severity `high`
   - title: `PC restarts over and over after last night's Windows update`
   - symptom: `It boots, shows the logo, restarts. Loops forever. Started right after the update installed.`

## Story verification (~US$0.10, run once per recording session)

Proves the three beats before anyone records. Temp ticket A gets ticket-1's text, temp
ticket B gets ticket-2's text; both run through the SSE endpoint exactly like the UI does.

Expected: **A** → top hit `Reboot loop after an update: current procedure`, both evidence
steps `via: mcp`, confidence ≥0.9. Resolve A via `POST /incidents/{A}/resolve` (any short
root cause/resolution). **B** → top hit is **A's postmortem** (`PC restarts over and
over…`). Ticket 3's beat (confidence 0.1, "no relevant past repairs") is stable and does
not need re-verification every time.

Cleanup is mandatory: delete tickets A and B, delete A's postmortem from memory, confirm
memory is back to 25 all-seed. Parse the stream by splitting on blank lines; the `result`
event's `data` is the `HandleResponse` JSON.

## The take

Window: `resize_window` to **1280×800**, human presses `Cmd +` once (110% zoom — zoom
shortcuts do not work through the extension). The app tab MUST start on the ticket queue:
navigate to `/` as the very first action of the take.

**Do not act against the clock.** `video/fit-to-audio.py` post-processes the recording:
it finds the moments where the screen changes, keeps them at 1x with readable dwell, and
compresses the dead waiting (Lambda round-trips, tool latency) onto the narration length.
So the take only needs the right ORDER and generous dwells on the money shots — natural
pace everywhere else. Playing `afplay out/narration.wav` during the take is OPTIONAL:
the recording is muted and fit-to-audio ignores start times entirely — its only value is
letting the human QA the story live (hear the narration drift from what the screen shows).

Sequence (same order as `docs/video-script.md`; dwell ≈4 s wherever marked 📌):

1. Navigate to `/`, rest on the queue a few seconds.
2. **Memory** tab, two or three slow scrolls; 📌 the `superseded`/`current`
   reboot-loop pair.
3. Back to **Ticket queue** → **New ticket** → `read_page` for refs → fill the 4 fields
   with `form_input` (ticket 1's exact text) → **Create ticket**.
4. Open ticket 1 — **`find` the row by its title, never by coordinates** (take 1 died
   clicking a stale coordinate after the queue re-ordered) — **Diagnose**, let the
   evidence paint; 📌 the `via: mcp` badges.
5. Scroll to the diagnosis; 📌 **Most relevant incident** = the current procedure.
6. **Resolve and write postmortem** (form is prefilled) → **Memory** tab; 📌 the new row
   on top, 26 total.
7. Queue → find ticket 2 by title → **Diagnose**; 📌 Most relevant = the postmortem just
   written.
8. Queue → find ticket 3 by title → **Diagnose**; 📌 **Confidence: 10%** and the
   root-cause sentence.
9. `navigate` the SAME tab to `https://github.com/gmassello/recall` (the tab strip is
   browser chrome — unclickable) and leave it a few seconds.

If an evidence step shows `via: fallback` on camera, that is the real dual-path behaviour
— per `docs/video-script.md`, own it, do not re-record for that alone.

When done the human stops the recording and saves it as `video/raw.mov`; then the
assembly pipeline (the exact invocation that shipped, with the beat marks of the
2026-08-01 take — a new take needs new marks, found via a timestamped contact sheet of
raw.mov plus single-frame probes at the candidate boundaries):

```bash
cd video
./make-slides.sh                     # the 4 stills (intro, CockroachDB, AWS, close)
./fit-to-audio.py raw.mov --beats 0,40,55,114,166,203,240,320,412 \
    --timing out/timing-noslide.txt  # timing.txt minus the 0:00 row (slide covers beat 1)
END=128.8 SLIDE=out/slide.png SLIDE_DUR=18.9 \
  OUTRO="out/slide-crdb.png:10.4,out/slide-aws.png:10.4,out/slide-close.png:8" \
  OUTRO_REPLACE=20.8 ./build-video.sh out/raw-fitted.mov
```

- `SLIDE` covers beat 1 (`SLIDE_DUR` = beat 1's length in `out/timing.txt`); the fit
  therefore uses a timing file WITHOUT that first row, and its marks start at beat 2.
- `OUTRO` slides replace the last narration beat (`OUTRO_REPLACE` = its length; `END=`
  trims the fitted recording just before that beat) and the closing still extends past
  the audio with padded silence. Keep total ≤ 3:00 — `build-video.sh` prints it.
- **`build-audio.sh` wipes `out/`**: after any narration edit, rerun `make-slides.sh`
  AND `fit-to-audio.py`, not just `build-video.sh`.
- `build-video.sh` needs the `subtitles` filter: the default brew ffmpeg 8 lacks libass,
  the script auto-prefers `/opt/homebrew/opt/ffmpeg@7/bin` (`brew install ffmpeg@7`).

## Between takes

Run `backend/.venv/bin/python video/reset-demo.py` again — it cleans everything a take
leaves behind (the postmortem in memory, ticket 1 whatever its status, tickets 2/3 with
saved diagnoses) and verifies. Note it sweeps `GET /tickets` **and**
`GET /tickets?status=resolved`: a finished take leaves ticket 1 resolved, and the plain
listing hides resolved tickets. Also delete the old `video/raw.mov` before recording over
it. A seed ticket diagnosed by mistake keeps a stale diagnosis — harmless as long as the
camera never opens it.

## Afterwards

Follow `VIDEO.md` § Afterwards: upload public/unlisted to YouTube, attach the `.srt`,
paste the link into `SUBMISSION.md` and `README.md`, file on Devpost. Hard checks: under
3:00, readable on a muted phone, `via: mcp` legible, CloudFront URL visible in the
address bar.
