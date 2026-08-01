# How to record the video

> Local working note. **Does not go to git.**
> The *what* to show lives in [`docs/video-script.md`](docs/video-script.md) — a
> shot list with timings and the texts of the three tickets. This file is the *how*.

It is the only mandatory deliverable still missing. Under 3 minutes, public on
YouTube or Vimeo, showing the app running and the CockroachDB memory layer
working. **Deadline: Aug 18, 2026, 5pm EDT.**

---

## The shape of it

Synthetic voice-over plus subtitles burned into the picture. Both in English.

This inverts the old plan in this file, which was captions and no voice. The
reason for that plan was that recording narration means ten takes to get one
clean one. Synthesising it removes that cost entirely — and it removes the worse
problem too, which is that a caption-only video forces the viewer to read and
watch the evidence timeline at the same time, and they can only do one.

With a voice track the narration in `docs/video-script.md` stays as written. The
captions become a second channel carrying the same words, so a judge scrubbing
the video muted on a phone still gets everything.

**The subtitles are burned into the picture, not only a YouTube `.srt` track.**
YouTube captions are off by default; a judge who hits play on a muted video and
never touches CC reads nothing and leaves. We ship both — burned in for the
person who does nothing, `.srt` for search and accessibility.

**The audio is authoritative and it gets built first.** Voice-over is easy to
generate and impossible to stretch convincingly; screen recording is the
opposite. So: build the track, read off the per-beat timings it produces, then
record the screen against those. Not the other way round.

---

## What you need

| Tool | For | Check |
|---|---|---|
| `say` | the voice. Ships with macOS | `say -v '?' \| grep en_` |
| **A Premium voice** | not sounding like 2009 | see below |
| `ffmpeg` | everything else | `brew install ffmpeg` |
| `Cmd+Shift+5` | the screen recording, **muted** | native |

Samantha and Alex are the stock voices and they give the game away in the first
sentence. Install a good one: **System Settings → Accessibility → Spoken Content
→ System Voice → Manage Voices**, download **Ava (Premium)**, and try
**Zoe (Premium)** and **Evan (Premium)** while you are there. The build script
defaults to Ava and refuses to run if the voice is not installed, rather than
silently falling back to Samantha.

OBS is not needed. It only buys system audio and scene switching, and we want
neither.

**Claude cannot record video** — no screen or audio capture. What Claude can do
is drive Chrome during the take, which is worth more (see *Cast*).

---

## The files

Everything lives in `video/`:

```
video/
  narration.tsv     the script, split into caption-sized lines   <- the only file you edit
  build-audio.sh    say + ffmpeg -> narration.wav + captions.srt + timing.txt
  build-video.sh    raw.mov + those two -> recall-demo.mp4
  out/              generated. gitignore it.
```

### `narration.tsv`

One row = one caption on screen = one TTS clip. That equivalence is the whole
trick: because every caption is rendered as its own audio file, the subtitle
timings come out exact by construction. No forced alignment, no nudging things
in a timeline, no drift by the end.

Columns, tab separated:

| Column | Meaning |
|---|---|
| `beat` | the label from `docs/video-script.md`. Only used for the timing report |
| `gap` | seconds of silence **before** this line. A row with an empty caption is a pure pause |
| `caption` | what the viewer reads. Max ~10 words. Numbers as digits |
| `speak` | what the voice says. Empty = say the caption verbatim |

That last column is what makes `via: mcp` readable on screen and pronounceable
out loud at the same time — the caption says `via: mcp — the Cloud Managed MCP
Server`, the voice says `via M C P. The CockroachDB Cloud Managed M C P Server.`
Same for `1,024-dimension` and `confidence 0.1`.

The `gap` column is where the old rule about not putting a caption on top of the
key moment now lives. Before `via: mcp` paints there is a **3.5 s** pause with
nothing said and nothing written; same before the *current procedure* reveal at
1:12, and a 5.5 s hole at 1:50 that covers the second `Diagnose` run. Those
holes are also the budget for the ~10 s each diagnosis takes against the
deployed Lambda.

---

## Step by step

### 1. Build the audio

```bash
cd video
./build-audio.sh                      # defaults: Ava (Premium), 172 wpm
./build-audio.sh 'Zoe (Premium)' 165  # slower, different voice
afplay out/narration.wav
```

It prints a table like this and refuses to ship if the captions and the track
have drifted apart by more than 250 ms:

```
  beat    starts      ends   length
  0:00       0.0      12.8     12.8
  0:12      12.8      33.0     20.3
  ...
TOTAL 162.0 s  =  2:42.0
HARD CAP 3:00 — OK
```

**Listen to the whole thing before you record anything.** Every fix at this
stage is a text edit; every fix after you have recorded costs a re-record. What
to listen for: a mangled number, a sentence the voice rushes, a pause that feels
like the file ended. Edit `narration.tsv`, run it again, it takes seconds.

If the total runs long, the script in `docs/video-script.md` already names the
cuts: drop the 2:15 beat first (it also saves a full 10-second agent run), then
trim the memory tour at 0:12.

### 2. Set up the demo

1. **Permissions**: enable `d2n13wfb8jv9v.cloudfront.net` in the Claude in
   Chrome extension, or it cannot touch the page.
2. **Demo state**: *Ticket queue* → **Delete all** → **Load examples**. This
   **deletes the tickets** of the deployed app; the 25 incidents in memory stay.
3. **Window**: 1280×800, 110 % zoom, no bookmarks bar, incognito so no login
   shows. The evidence timeline is the star and it has to be legible.
4. **Never *Generate random***: `MOCK_SEED` is not in the deployed stack, so the
   generator is genuinely random and cannot be rehearsed. The three fixed ticket
   texts are in the script.

### 3. Rehearse against the real audio

Put on **headphones** and play `out/narration.wav` while you walk the sequence.
The recording is muted, so nothing leaks into it, and you get to feel exactly
how much room each beat has instead of guessing. Do this at least once end to
end — a cold Lambda can add a few seconds to the first `Diagnose`.

### 4. Record

`Cmd+Shift+5`, selected window, **microphone off**. Save it as `video/raw.mov`.

Do not chase perfection on length. A recording anywhere from about 2:10 to 3:30
is fine: the assembly step rubber-bands it onto the audio, and on a screencast a
1.1× speed change is invisible. Beyond ±25 % it refuses, because at that point
the mouse starts to look wrong.

### 5. Assemble

```bash
./build-video.sh raw.mov                        # simplest case
START=3.5 END=170 ./build-video.sh raw.mov      # trim the dead head and tail
BED=bed.m4a ./build-video.sh raw.mov            # with a music bed under the voice
FONTSIZE=16 ./build-video.sh raw.mov            # bigger subtitles
```

Out comes `out/recall-demo.mp4` — 1920×1080, voice mixed and loudness
normalised, subtitles burned in — and `out/recall-demo.en.srt` to upload
alongside it.

A soft bed from the YouTube Audio Library is optional and cheap: it is mixed at
6 % under the voice with a fade at each end, and it stops the quiet stretches
from reading as a broken file. No rights issues from that library.

### 6. Watch it once on your phone, muted

That is the actual test. If a caption cannot be read in the time it is on
screen, there is too much text in that row of `narration.tsv`.

---

## Cast

| Who | What |
|---|---|
| Claude | Drives Chrome: navigates, types the three tickets, does the clicks |
| `build-audio.sh` | The voice and the subtitle timings |
| You | Record muted with `Cmd+Shift+5`, then run `build-video.sh` |

Having Claude drive the browser spares you typing on camera, hunting for a
button, or a click landing crooked in the good take. Nobody overlays captions by
hand.

---

## The moment that cannot be missed

It is literally what the rules ask to see:

ticket comes in → the timeline shows `search_memory` with **`via: mcp`** → it
cites the **current** procedure, not the superseded one → a human resolves → the
postmortem goes back into memory → the next similar ticket already cites it.

Both evidence steps should read `via: mcp`. If one ever shows `fallback` on
camera, that is the real behaviour of the fallback path, not a glitch — say so
rather than re-recording. See *Two things not to overclaim* in
`docs/video-script.md`.

---

## Afterwards

- Upload to YouTube **public or unlisted**, never private: judges have to be
  able to watch it without requesting access.
- Upload `out/recall-demo.en.srt` as the English caption track.
- Paste the link into the *Video* row of [`SUBMISSION.md`](SUBMISSION.md), which
  today says *pending*, and into the block at the top of [`README.md`](README.md).
- File the submission on Devpost.

---

## Final checklist

- [ ] Runs **under 3:00**. `build-audio.sh` says so out loud; Devpost rejects it
      if it goes over.
- [ ] The voice does not sound like Samantha.
- [ ] Captions land on the word being spoken, all the way to the last beat.
- [ ] Opens in incognito, no login.
- [ ] `via: mcp` is readable in the evidence steps.
- [ ] The CloudFront URL is visible in the address bar — that is what proves it
      is deployed.
- [ ] Readable **on a phone, muted, without touching CC**.
