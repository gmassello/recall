# Demo video — shooting script (2:50 / hard cap 3:00)

Timed version of the sequence in `recall-DOCUMENTATION.md` §11. Every number and
label below was checked against the deployed app on 2026-07-28.

Record against **https://d2n13wfb8jv9v.cloudfront.net**, not localhost: the rules
ask for the project running, and a CloudFront URL in the address bar proves it is
deployed.

---

## Before recording

1. **Reset the demo state.** *Ticket queue* → **Delete all**, then **Load
   examples**. Memory should hold 25 incidents.
2. **Do not use "Generate random".** `MOCK_SEED` is not set on the deployed stack,
   so the generator is genuinely random and you cannot rehearse it. Use **New
   ticket** with the exact text below.
3. **Dry run once, end to end.** Diagnosing takes about **10 s** against the
   deployed Lambda. The script budgets for that; a cold start can add a few
   seconds.
4. Browser at 1280×800, zoom 110 %, no bookmarks bar. The evidence timeline is the
   star and it needs to be legible.
5. Have the second and third tickets on the clipboard or in a scratch file — you
   do not want to be typing on camera.

---

## The story

Memory holds two incidents about the same failure: **"Windows reboot loop after an
update"**, whose validity expired and which was superseded, and **"Reboot loop
after an update: current procedure"** (quality 0.5, cited 6 times). A ticket about
a reboot loop recalls the current one and never sees the stale one. That single
frame proves vector recall, quality ranking and the validity filter at once.

---

## Shot list

| Time | Dur | On screen | Narration |
|---|---|---|---|
| 0:00 | 12 s | App open on *Ticket queue* | "On-call teams solve the same incident twice, because last quarter's fix is buried in a closed ticket. Recall is an agent whose memory is CockroachDB." |
| 0:12 | 20 s | *Incident memory* tab. Scroll slowly. Rest on **"Dead laptop caused by a counterfeit charger"** — quality 0.8, cited 9 | "This is the memory: twenty-five resolved incidents, each embedded as a thousand-and-twenty-four-dimension vector in CockroachDB, sitting next to the tickets in the same database. Quality score, times cited, and a validity window — memory that ages." |
| 0:32 | 10 s | Scroll to the pair: **"Windows reboot loop after an update"** (expired, superseded) and **"Reboot loop after an update: current procedure"** | "This procedure expired and was superseded by this one. Watch what the agent does with that." |
| 0:42 | 13 s | *Ticket queue* → **New ticket** → paste ticket 1 → create | "A ticket comes in: a PC stuck in a reboot loop after a Windows update." |
| 0:55 | 17 s | Open it, hit **Diagnose**. Let the evidence timeline paint live | "The agent picks its own tools. This is live — server-sent events straight from Lambda. It searches memory semantically, then queries the incident table. And every step reports how it reached the database: `via mcp` — the CockroachDB Cloud Managed MCP Server, in the request path, not just in my editor." |
| 1:12 | 18 s | Diagnosis panel, then **Most relevant incident** | "Root cause, mitigation steps, high confidence. And the incident it leaned on is the *current* procedure — not the superseded one. That filter runs in SQL, so stale knowledge is never even a candidate." |
| 1:30 | 20 s | Fill Root cause / Resolution → **Resolve and write postmortem** → back to *Incident memory*, the new row on top | "A human confirms and resolves. The postmortem is embedded and written straight back into memory. Twenty-six now. That is the loop." |
| 1:50 | 25 s | *Ticket queue* → ticket 2 → **Diagnose** → point at **Most relevant incident** | "Same class of problem again. This time the top hit is the postmortem we wrote sixty seconds ago. The system got better between two tickets." |
| 2:15 | 17 s | Ticket 3 (`software-phone`) → **Diagnose** → hold on **confidence 0.1** and the root-cause text | "And when there is no precedent, it says so — confidence zero-point-one — instead of inventing a root cause." |
| 2:32 | 18 s | Architecture diagram or the repo page | "CockroachDB does two jobs here: distributed vector indexing for the recall, and the Cloud Managed MCP Server as a live read path. It runs on AWS Lambda with response streaming, behind CloudFront. One database for the vectors and the transactions." |

**If you run long, cut the 2:15 beat** (17 s) — it is the most expendable and it
costs a full 10-second agent run. Second cut: trim the memory tour at 0:12 to 12 s.

---

## Ticket texts

**Ticket 1** — `software-pc`, severity `high`

> **Title:** PC restarts over and over after last night's Windows update
> **Symptom:** It boots, shows the logo, restarts. Loops forever. Started right after the update installed.

Verified result: most relevant incident **"Reboot loop after an update: current
procedure"** (score ~0.13), both evidence steps `via: mcp`, confidence **0.9–0.95**.
The recalled incident is stable across runs; the exact confidence is not, since
it comes from the model — so the narration says "high confidence", not a number.
Read whatever is on screen.

**Ticket 2** — `software-pc`, severity `high`. Run it *after* resolving ticket 1.

> **Title:** Another PC in an endless restart loop after the same update
> **Symptom:** Boots to the logo and restarts, over and over. Same as the one we fixed earlier today.

**Ticket 3** — `software-phone`, severity `medium`

> **Title:** Android app keeps closing right after the latest OS update
> **Symptom:** Since updating the phone OS, the banking app closes by itself a few seconds after opening. Reinstalling did not help.

Verified result: confidence **0.1**, root cause *"No relevant past repairs or
precedents were found in memory…"*. Here the low confidence is the whole point,
so this one is worth reading out loud. On this one, do **not** linger on the *Most
relevant incident* panel — it still shows the nearest neighbour even though the
agent correctly reports no precedent. Keep the camera on the confidence and the
root-cause sentence.

---

## Two things not to overclaim

- **Both steps should read `via: mcp`.** They do since the recall SQL stopped
  inlining the embedding twice — it used to render at ~22,000 characters and the
  Managed MCP Server rejects anything over 16,384, so every semantic search
  silently fell back to the direct connection. If you ever see `fallback` on
  camera, that is the real behaviour of the fallback path, not a glitch: say so
  rather than re-recording, it is the point of having two paths.
- **Do not say "no static credentials" over a UI shot.** It is true of the deploy
  (GitHub OIDC), not of the browser, which carries the demo key in its bundle.
