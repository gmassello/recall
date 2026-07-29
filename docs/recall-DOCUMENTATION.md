# Recall

Incident response agent with **full agentic memory**: it takes in tickets, recalls
semantically similar past incidents, diagnoses while weighing recency and quality,
and **learns** from every resolution. A full-stack application, **agnostic of the
AI provider**.

Submission for the **CockroachDB × AWS — Build with Agentic Memory** hackathon.

> **Status: implemented.** Backend (`backend/`) and frontend (`frontend/`) are
> built according to this spec. Sections 4–7 describe what runs today.

---

## 1. Summary

When an incident ticket comes in, the agent:

1. **Decides what to query** (semantic + structured memory) using tools.
2. **Recalls** similar past incidents with vector search + temporal ranking.
3. **Diagnoses**: likely root cause + mitigation steps + the most relevant incident.
4. On **resolve**, it writes the postmortem → memory grows.
5. The engineer's **feedback** re-weighs that memory for next time.

That closed loop (read → reason → write → learn) is what makes the memory
"agentic" and not a plain vector search.

---

## 2. Stack and architecture decisions

| Layer | Choice | Note |
|-------|--------|------|
| Memory | **CockroachDB** | Distributed Vector Indexing + Managed MCP Server |
| AI | **Agnostic** layer (`LLMProvider`) | Gemini, Claude via Amazon Bedrock, or the Anthropic API |
| Embeddings | Gemini or Amazon Titan v2 | 1024 dims either way (matches `VECTOR(1024)`) |
| Backend | **FastAPI** (REST) | Automatic docs at `/docs` |
| Frontend | **React + Vite + TypeScript** | 3 views |
| Deploy | **Lambda + S3 + CloudFront** (SAM) | Web Adapter in `RESPONSE_STREAM`, so SSE stays incremental |

Principles that do not break:

- **Provider-agnostic AI**: everything goes through `providers/base.py`
  (`LLMProvider` / `EmbeddingProvider`). Switching models is one env var
  (`LLM_PROVIDER` / `EMBEDDING_PROVIDER`). The agent loop never knows the concrete
  provider. The LLM can be `gemini`, `bedrock` or `anthropic`; the embedder,
  `gemini` or `bedrock`. The deployed stack runs on Gemini (one free-tier key
  covers both roles); Bedrock is the path that satisfies AWS with an Anthropic
  model, through the Lambda execution role.
- **MCP at runtime (option b)**: the reads the agent decides to make with tools
  (`search_memory`, `query_incidents`) go through CockroachDB's Managed MCP Server
  — the same protocol used in dev with Claude Code. Everything else goes through a
  direct `psycopg` connection: the writes (postmortem, feedback, supersede) and the
  service reads that do not go through the agent (`GET /tickets`, `GET /memory`).
  If the MCP does not respond, the tools fall back to `psycopg` with the same SQL
  and the evidence trail marks `via: "fallback"` — the demo does not fall over
  because of a network dependency.
- **Temporal memory**: the `k` nearest neighbours are recalled by vector and
  re-ranked with

  ```
  score = cosine_distance − W_QUALITY·quality_score + W_AGE·(age_days / 365)
  W_QUALITY = 0.15    W_AGE = 0.10    k = 40 → top 5
  ```

  Lower score = better. `age_days` is `now() − created_at`; it is normalized to
  years and saturates at 1.0, so the age penalty never dominates semantic
  similarity. Stale knowledge is filtered out
  (`valid_until IS NULL OR valid_until > now()`) and contradictions chain through
  `superseded_by`.
- **Feedback → quality**: 👍 adds `+0.1` to `quality_score`, 👎 subtracts `0.15`,
  clamped to `[-1.0, 1.0]`. `times_cited` is incremented every time an incident
  enters the top 5 of a diagnosis and `times_helpful` with every 👍. Neither enters
  the score: they exist to explain in the UI *why* a memory weighs what it weighs,
  and to audit whether the ranking is working.
- **Swappable ticket source**: `TicketSource` interface; the mock persists to
  CockroachDB and a real `PagerDutyTicketSource` drops in without touching the
  rest. The mock feeds the queue in three ways, all behind the same interface:
  **fixture** (`tickets_seed.json`), **generated** (templates + `random`, §9) and
  **imported** (customer history, §10).

---

## 3. Diagram

```
Ticket Source (swappable mock)
        │ ingest
        ▼
FastAPI (REST)   /tickets · /handle · /resolve · /feedback · /memory
        │ handle()
        ▼
AGENT LOOP (model agnostic)
        │ picks tools: search_memory (vector) · query_incidents (SQL)
        ▼
MCP CLIENT (runtime)
        │
        ▼
CockroachDB Managed MCP Server  (read-only)
        │
        ▼
CockroachDB
        incidents          long-term memory: temporal + quality + VECTOR(1024)
        tickets
        ▲
        │ writes (postmortem · feedback · supersede) via direct psycopg
        │ + read fallback if the MCP does not respond
     FastAPI

AI: LLMProvider + EmbeddingProvider → Gemini (deployed default) · Bedrock (Claude + Titan) · Anthropic
```

---

## 4. Data model (CockroachDB)

Requires **CockroachDB v25.3+**: the index is declared with the `vector_cosine_ops`
opclass so it accelerates the `<=>` operator the recall uses, and that opclass does
not exist before v25.3 (in v25.2 only the L2 distance `<->` is accelerated).

Two limitations of the vector index shape how the recall query is written:

- The opclass has to match the operator in the query. The default is
  `vector_l2_ops`, which only accelerates `<->`.
- *"Index acceleration with filters is only supported if the filters match prefix
  columns."* That is why recall has two paths:
  - **Without `service`** (the common case): the query has no `WHERE` and the index
    accelerates it. The validity filters (`valid_until`, `superseded_by`) are
    applied in Python over the recalled candidates; putting them in the `WHERE`
    would disable the index.
  - **With `service`**: the service is not a prefix column of the vector index, so
    acceleration would not apply anyway. The query filters in SQL
    (`WHERE service = %s AND <validity>`) and orders by exact distance, bounded by
    `incidents_service_idx`. Acceleration is traded for exactness on purpose:
    filtering in Python over a global top-N can drop incidents from that service
    that rank below the cutoff, even when they are the only ones that exist.

  The ceiling of the `service` path is that it computes distance over every row of
  that service. At this project's scale that is irrelevant; if one service
  concentrated a lot of volume, an approximate scheme would be needed again.

```sql
-- severity : 'critical' | 'high' | 'medium' | 'low'
-- status   : tickets -> 'open' | 'handling' | 'resolved'

CREATE TABLE incidents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         STRING NOT NULL,
    symptom       STRING NOT NULL,
    root_cause    STRING,
    resolution    STRING,
    service       STRING,
    severity      STRING,
    created_at    TIMESTAMPTZ DEFAULT now(),
    resolved_at   TIMESTAMPTZ,
    valid_until   TIMESTAMPTZ,               -- NULL = knowledge still current
    superseded_by UUID,                      -- temporal chain (Zep style)
    quality_score FLOAT DEFAULT 0.0,         -- adjusted by feedback
    times_cited   INT DEFAULT 0,
    times_helpful INT DEFAULT 0,
    external_id   STRING UNIQUE,               -- ref from the source system; idempotent import
    source        STRING DEFAULT 'manual',     -- 'seed'|'generated'|'imported'|'manual'
    embedding     VECTOR(1024)
);
CREATE VECTOR INDEX incidents_embedding_idx ON incidents (embedding);
CREATE INDEX incidents_service_idx ON incidents (service, created_at);

CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id STRING UNIQUE, title STRING NOT NULL, description STRING,
    service STRING, severity STRING, status STRING DEFAULT 'open',
    source STRING DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- covers the queue filter by status plus the created_at ordering; the title
-- search is an ILIKE '%...%' and stays a scan (a leading wildcard cannot use it)
CREATE INDEX tickets_status_idx ON tickets (status, created_at);

-- last HandleResponse of each ticket, stored whole so reopening the incident
-- view does not have to run the agent again
CREATE TABLE diagnoses (
    ticket_id  UUID PRIMARY KEY REFERENCES tickets (id) ON DELETE CASCADE,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. REST API

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/health` | Health check; includes the state of the MCP (`probe()`) |
| GET  | `/tickets` | Queue. Filters: `?service=`, `?severity=`, `?status=`, `?search=` (free-text match on the title; the mock source implements it as `ILIKE`), `?order=asc\|desc`. Without `status` it keeps the historical behaviour and hides resolved tickets |
| POST | `/tickets` | Ingestion (manual mock or alert webhook) |
| POST | `/tickets/generate?n=1` | Generates `n` synthetic tickets and queues them (§9) |
| POST | `/tickets/seed` | Loads the example incidents and tickets (idempotent) |
| DELETE | `/tickets` | Empties the queue (only `status != 'resolved'`) |
| GET  | `/tickets/{id}` | Ticket detail |
| PATCH | `/tickets/{id}` | Edits title, symptom, service or severity |
| DELETE | `/tickets/{id}` | Deletes a ticket (its diagnosis goes with it, `ON DELETE CASCADE`) |
| POST | `/tickets/{id}/handle` | Runs the agent loop → diagnosis + evidence |
| GET  | `/tickets/{id}/handle/stream` | Same as `handle` but over SSE: `evidence` (one per tool), `result` (full response) and `agent_error` events |
| GET  | `/tickets/{id}/diagnosis` | Last saved diagnosis of the ticket, evidence included (404 if never diagnosed) |
| POST | `/incidents/{ticket_id}/resolve` | Writes the postmortem (memory grows) |
| POST | `/incidents/{ticket_id}/feedback` | 👍/👎 adjusts the quality of the memory |
| GET  | `/memory?service=...` | Memory inspection |
| PATCH | `/memory/{id}` | Edits an incident; re-embeds if the title or the symptom changed |
| DELETE | `/memory/{id}` | Deletes an incident and clears any dangling `superseded_by` pointing at it |
| DELETE | `/memory` | Wipes the whole memory |
| POST | `/memory/{id}/supersede` | Marks the incident as superseded by another |

Both `/incidents/...` paths take a **ticket** id, not an incident id: the resolve
is what turns a ticket into an incident, and the feedback hangs off the diagnosis
of that ticket.

`POST /tickets/{id}/handle` and its SSE variant also move the ticket to
`handling` while the agent runs, and roll it back to `open` if the agent fails or
the stream is cut short.

The `handle` response includes the **evidence trail** (which tools the agent used
and what it recalled), which feeds the live timeline in the frontend.

### Bodies of the non-trivial endpoints

`POST /tickets/{id}/handle` — no body.

```jsonc
// 200
{
  "ticket_id": "…",
  "diagnosis": {
    "root_cause": "Connection pool exhaustion in payments-api",
    "mitigation_steps": ["Raise max_connections to 200", "…"],
    "confidence": 0.82
  },
  "most_relevant_incident": { "id": "…", "title": "…", "score": 0.31 },
  "evidence": [
    { "tool": "search_memory",   "via": "mcp",
      "args": { "symptom": "…", "k": 20 },
      "returned": [ { "id": "…", "title": "…", "score": 0.31 } ] },
    { "tool": "query_incidents", "via": "fallback",
      "args": { "service": "payments-api" }, "returned": [] }
  ]
}
```

`POST /incidents/{ticket_id}/resolve` — writes the postmortem and embeds the symptom.

```jsonc
// request
{ "root_cause": "…", "resolution": "…", "supersedes": "uuid | null" }
// 201
{ "incident_id": "…", "embedded": true, "superseded": "uuid | null" }
```

`POST /incidents/{ticket_id}/feedback`

```jsonc
// request  — helpful=false subtracts more than true adds (see section 2)
{ "incident_id": "…", "helpful": true }
// 200
{ "incident_id": "…", "quality_score": 0.40, "times_helpful": 3 }
```

`POST /tickets/generate?n=1` — no body.

```jsonc
// 201
{ "generated": [ { "id": "…", "title": "…", "symptom": "…",
                   "service": "payments-api", "severity": "high",
                   "source": "generated" } ] }
```

---

## 6. Repo structure

```
backend/
  app/
    main.py                  # FastAPI app + CORS + GET /health
    config.py                # env vars and tuning knobs (one pydantic Settings)
    db.py                    # direct connection (writes) + init schema
    models.py                # pydantic: Ticket, Incident, Diagnosis, ...
    providers/
      base.py                # LLMProvider, EmbeddingProvider, ToolSpec (canonical)
      bedrock.py             # BedrockClaudeProvider + BedrockTitanEmbedder
      anthropic_provider.py  # LLM only, no embedder
      gemini_provider.py     # GeminiProvider + GeminiEmbedder (deployed default)
      registry.py            # factory from env
    mcp/
      cockroach_client.py    # runtime MCP client (service-account key)
    tickets.py               # TicketSource + MockTicketSource + TicketGenerator
    memory.py                # temporal recall, store, feedback, supersede
    diagnoses.py             # last HandleResponse per ticket (JSONB)
    postmortem.py            # write_postmortem()
    agent/
      tools.py               # ToolSpecs + handlers (resolved via MCP)
      loop.py                # tool-use loop, provider agnostic
    api/
      deps.py                # get_ticket_or_404 + shared error strings
      tickets.py  incidents.py  memory.py
  seed/
    tickets_seed.json      # ticket fixture
    seed_memory.py         # example memory
  certs/cockroach-root.crt # CA bundle shipped inside the Lambda package
  run.sh                   # Lambda entrypoint (the Web Adapter execs it)
  template.yaml            # SAM stack: Lambda + Function URL + S3 + CloudFront
  schema.sql   requirements.txt   requirements-lambda.txt   .env.example
frontend/
  package.json  vite.config.ts  tsconfig.json  index.html
  src/  main.tsx  App.tsx  api.ts  types.ts  hooks.ts  styles.css
        components/  TicketQueue.tsx  IncidentView.tsx  MemoryExplorer.tsx
deploy.sh                  # build + deploy + upload the bundle + invalidate
infra/github-oidc.yaml     # OIDC provider + deploy role (one-time bootstrap)
.github/workflows/deploy.yml
.claude/skills/            # runbooks: deploy, bootstrap, switch provider
```

---

## 7. Getting started

### Prerequisites
- **CockroachDB Cloud** (Basic plan, free): connection string + service account API key (for the MCP).
- **One model provider**, any of the three: a Google AI Studio key (`gemini`, free
  tier, covers LLM *and* embeddings — this is what the deployed stack uses),
  **AWS with Bedrock** (Claude + Titan Text Embeddings V2 enabled), or an Anthropic
  key for the LLM combined with Gemini or Bedrock for the embeddings.
- **Python 3.13** (what CI and Lambda pin; 3.11+ works locally) and **Node 18+**.

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # DATABASE_URL, COCKROACH_MCP_API_KEY, provider key
python -m app.db              # creates the schema
python -m seed.seed_memory    # example memory + tickets
uvicorn app.main:app --reload # http://localhost:8000/docs
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api → :8000)
```

### Environment variables

| Variable | Required | Default | What it is |
|----------|----------|---------|------------|
| `DATABASE_URL` | yes | — | CockroachDB connection string (writes + fallback) |
| `COCKROACH_MCP_API_KEY` | yes | — | Service account API key for the Managed MCP Server |
| `COCKROACH_MCP_URL` | yes | — | MCP Server endpoint (`https://cockroachlabs.cloud/mcp`) |
| `COCKROACH_MCP_CLUSTER_ID` | yes | — | Cluster ID, sent in the `mcp-cluster-id` header |
| `LLM_PROVIDER` | no | `bedrock` | `bedrock` \| `anthropic` \| `gemini` |
| `EMBEDDING_PROVIDER` | no | `bedrock` | `bedrock` \| `gemini`. Must produce 1024 dims (`VECTOR(1024)`) |
| `AWS_REGION` | if `bedrock` | `us-east-1` | Region with Bedrock access enabled |
| `BEDROCK_API_KEY` | no | — | Bedrock API key (`ABSK…`), alternative to SigV4. Propagated to `AWS_BEARER_TOKEN_BEDROCK` |
| `BEDROCK_MODEL_ID` | no | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Model via the Converse API. **Inference profile, not the bare ID** (see below) |
| `BEDROCK_EMBEDDING_MODEL_ID` | no | `amazon.titan-embed-text-v2:0` | Titan v2, 1024 dims. Bare ID: embedding models do not use inference profiles |
| `ANTHROPIC_API_KEY` | if `anthropic` | — | Only for the provider swap |
| `GEMINI_API_KEY` | if `gemini` | — | **Free** alternative to Bedrock (free tier): one key does LLM and embeddings |
| `GEMINI_MODEL` | no | `gemini-flash-latest` | Chat model with function calling |
| `GEMINI_EMBEDDING_MODEL` | no | `gemini-embedding-001` | `output_dimensionality=1024` → no table migration |
| `DEMO_API_KEY` | no | — | Shared key demanded on the destructive endpoints (`DELETE`, `PATCH`) as `X-API-Key`. Empty leaves them open |
| `MOCK_SEED` | no | — | Seed of the ticket generator → reproducible demo (§9) |

AWS credentials come from the standard boto3 chain (profile, env vars or role).

Bedrock also accepts **API keys** instead of SigV4: boto3 reads them from the
`AWS_BEARER_TOKEN_BEDROCK` environment variable and only from there. Putting it in
`BEDROCK_API_KEY` in `.env` is enough — `providers/bedrock._client()` propagates it
to that variable before building the client. If `AWS_BEARER_TOKEN_BEDROCK` already
comes from the environment, that one wins.

Careful with the diagnosis: without the key, boto3 signs with SigV4 and a role
without permissions returns `AccessDeniedException: not authorized to perform
bedrock:InvokeModel`. With a key in an invalid format the error is different —
`Invalid API Key format` — and that change of message is what tells "the key is
missing" apart from "the key does not work".

**The model ID prefix has to match `AWS_REGION`.** Claude Sonnet 4.5 does not allow
on-demand invocation with the bare ID (`In-Region ❌` in every region): an inference
profile is required.

| Region | Prefix |
|--------|--------|
| `us-*`, `ca-central-1` | `us.` |
| `eu-*` | `eu.` |
| `ap-southeast-2/4/6` | `au.` |
| `ap-northeast-1/3` | `jp.` |
| any commercial region | `global.` |

Regions without a geo profile (`ap-south-1`, `ap-southeast-1`, `sa-east-1`, `me-*`)
can only use `global.`. The IAM policy must allow `bedrock:InvokeModel` **over the
inference profile**, not over the foundation model.

### Switching the AI model (agnostic)
```
# backend/.env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```
The rest of the code does not change. `bedrock` is the one that satisfies AWS with
an Anthropic model, through the Lambda execution role and without deploying keys.

**Free** end-to-end alternative (LLM + embeddings) with no AWS account — and what
the deployed stack runs on:
```
# backend/.env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...   # https://aistudio.google.com/apikey
```
The embedder asks for `output_dimensionality=1024` and normalizes the vector, so it
fits `VECTOR(1024)` without a migration. They can be mixed: keep
`LLM_PROVIDER=anthropic` and use only `EMBEDDING_PROVIDER=gemini` to cover what the
corporate gateway does not provide (Titan).

Two things a switch does not do on its own. Changing the **embedder** leaves the
stored vectors as they are: they came out of another model, so the memory has to
be re-embedded or recall compares incomparable things. And changing the **LLM** on
a deployed stack needs its SDK inside `requirements-lambda.txt`, which is a
shorter list than `requirements.txt` — otherwise the function dies on import.

### Deploying

`.github/workflows/deploy.yml` (`workflow_dispatch`, OIDC, gated on `ruff` +
`pytest`) runs `deploy.sh`, which applies `backend/template.yaml`: Lambda behind a
Function URL in `RESPONSE_STREAM`, S3 and CloudFront for the bundle. The repo
secrets and variables it needs, the one-time `infra/github-oidc.yaml` bootstrap
and the per-stack gotchas are in the [Deploy on AWS](../README.md#deploy-on-aws)
section of the README; the step-by-step runbooks are the skills in
`.claude/skills/`.

---

## 8. How it meets the hackathon requirements

The full breakdown, and the one that goes into the submission form, is
[`SUBMISSION.md`](../SUBMISSION.md) at the root of the repo. In short:

- ✅ **CockroachDB #1** — Distributed Vector Indexing (semantic memory search).
- ✅ **CockroachDB #2** — Managed MCP Server at **runtime** (option b) + in dev with Claude Code.
- ✅ **CockroachDB #3** — `ccloud` CLI: cluster preflight in `deploy.sh` when deploying from a workstation, and cluster creation behind `CREATE_CLUSTER=1`.
- ✅ **AWS** — deployed on Lambda + Function URL + S3 + CloudFront (SAM) over GitHub OIDC, with Amazon Bedrock (Claude Converse + Titan) as one of the supported providers.
- ✅ **Anthropic model** — Claude via Bedrock or via the Anthropic API, behind an agnostic layer that allows the swap.
- ✅ Open-source repo (MIT) + live demo. Video pending.

---

## 9. Ticket generator

The mock does more than serve a fixture: it generates synthetic incidents on
demand, via `POST /tickets/generate` or the **Generate random** button in
`TicketQueue`.

The domain is a computer and phone repair shop, and the `service` field is the
**area**: `hardware-pc`, `software-pc`, `hardware-phone`, `software-phone`.

The templates are a list of `(area, symptom_template, severity)` in `tickets.py`,
with numeric placeholders (`pct`, `n`, `gb`) filled in with `random`:

```python
TEMPLATES = [
    ("hardware-pc",    "the laptop does not turn on and the charging led stays off", "critical"),
    ("software-pc",    "Windows goes into a reboot loop after the update",           "high"),
    ("hardware-phone", "the touchscreen does not respond on {pct}% of the display",  "high"),
    ("software-phone", "it has been stuck on the logo at boot for {n} days",         "high"),
]
```

No `faker` and no LLM generation: asking a model for text costs latency and money
to produce what a template solves just as well.

Two requirements on the templates, which are what makes the generator useful:

- **Cover the same areas and symptom families as `seed_memory.py`**, with varied
  wording. If the generated ticket does not semantically resemble anything in
  memory, recall comes back empty and the demo looks worse than the system is.
- **Include an area with no prior memory** (today `software-phone`), so the honest
  case can be shown: the agent finds nothing and says so, instead of inventing a
  diagnosis.

Both requirements are the gate of `tests/test_domain_generator.py`, which also
validates that every template produces a valid `TicketCreate`.

`MOCK_SEED` (optional env var) fixes the `random` seed → reproducible runs for
recording the video without surprises.

---

## 10. History ingestion — design, not implemented

> **Nothing in this section ships today.** `backend/seed/` only holds
> `seed_memory.py` and `tickets_seed.json`; `seed.import_history` and
> `seed.evaluate` do not exist. This is the design for taking the memory layer to
> a real customer, kept here because it is what the roadmap builds on.

Before putting the agent in production with a customer, their incident history
serves two purposes: **starting with real memory** instead of an empty one, and
**measuring whether the agent gets it right** before trusting it.

Input format, `history.jsonl` (one line per incident):

```jsonc
{ "external_id": "INC-1042", "title": "…", "symptom": "…",
  "root_cause": "…", "resolution": "…",       // if missing → skipped
  "service": "payments-api", "severity": "high",
  "created_at": "2025-03-11T04:12:00Z", "resolved_at": "2025-03-11T05:40:00Z" }
```

### Memory bootstrap

```bash
python -m seed.import_history history.jsonl [--dry-run] [--limit N]
```

1. Validates and maps every row. **Only resolved incidents get in**: without
   `root_cause`/`resolution` there is no knowledge to remember, they are counted as
   skipped.
2. Skips `external_id`s already present → reimporting is idempotent.
3. Embeds `title + symptom` and writes to `incidents` with `source='imported'`,
   **respecting the original `created_at`**. Temporal ranking depends on that date;
   using `now()` would make the whole history look like it just happened and would
   cancel out the age penalty.
4. `quality_score` starts at `0.0` — history does not come pre-validated, quality is
   built by usage feedback.
5. Reports imported / skipped / duplicates.

Embeddings are computed sequentially, checkpointing the last processed
`external_id` so an interrupted run can resume. Known limit: for large volumes it
has to be parallelized (see roadmap).

### Prior evaluation

```bash
python -m seed.evaluate history.jsonl --holdout 20
```

1. Sets aside `N` resolved incidents at random (fixed seed) and imports **only the
   rest**. Importing everything first would let every case find its own answer in
   memory: the result would look almost perfect and measure nothing.
2. Runs the agent loop over the `symptom` of every holdout.
3. Metric: **recall@5** — it counts as a hit if some incident in the top 5 shares
   the `service` and its `root_cause` matches the real one. Objective, no LLM judge.
4. Prints `recall@5`, `recall@1` and the list of failed cases for manual inspection.

That list of failures is the real deliverable: it says whether the problem is the
memory (the right incident was not there), the embedding (it was there but was not
recalled) or the ranking (it was recalled but ended up below the cut).

---

## 11. Demo script (< 3 min)

The sequence that has to run end to end. The point is showing the closed loop: the
same symptom diagnosed twice gives a better result the second time, because in
between the system learned.

1. **Initial state** — `MemoryExplorer` with the seeded memory (`seed_memory.py`).
   Show that there are old incidents, one of them with an expired `valid_until`.
2. **A ticket comes in** — **Generate random** button (§9). A synthetic incident
   shows up in the queue, e.g. *"[software-pc] Windows goes into a reboot loop
   after the last update"*. With a fixed `MOCK_SEED`, it is always the same one.
3. **Handle** — the timeline shows the agent picking `search_memory`, the recalled
   evidence and the diagnosis. Point out that the stale incident was **not** recalled.
4. **Resolve** — the postmortem is written. Memory grows: the new incident shows up
   in `MemoryExplorer` with `quality_score = 0.0`.
5. **Feedback 👍** on the incident that did help → its `quality_score` goes up.
6. **Second ticket, similar symptom** → handle again. Now the top 1 is the
   postmortem just written, and the `score` of the one that got a 👍 improved. That
   delta *is* the demo.

7. **Closing** — back in `MemoryExplorer`, the memory has one incident more than it
   started with and the score of the cited one moved. That delta is the whole
   argument: the loop is closed.

Fix `MOCK_SEED` so steps 2 and 6 are reproducible while recording.

---

## 12. Roadmap / prioritized tasks

1. ~~**SSE** on `/tickets/{id}/handle/stream` + consumption in the frontend to watch the agent reason live.~~ **Done**: the frontend consumes the stream with `EventSource` and paints the evidence timeline live.
2. **Contradiction detection** that triggers `supersede()` automatically.
3. ~~**Deploy** on AWS (Lambda/ECS + S3) — adds "production readiness".~~ **Done**: SAM stack (Lambda + Function URL + S3 + CloudFront) shipped by a GitHub Actions workflow over OIDC.
4. **Auth on the Function URL** — it is `AuthType: NONE` today, which leaves the destructive endpoints open to anyone with the link.
5. **OpenAIProvider** following `providers/base.py` (demonstrates the agnosticism).
6. **Parallelize the embeddings** of `import_history` for large histories.
7. **LLM judge** in `evaluate` over the quality of the written `root_cause`, on top
   of the `recall@k` that already measures retrieval.

---

## License
MIT.
