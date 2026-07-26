# Recall

On-call copilot with semantic incident memory, built for the
**CockroachDB × AWS — Build with Agentic Memory** hackathon.

It takes in incident tickets, diagnoses them with an LLM agent that queries a
vector memory of past incidents (CockroachDB + `VECTOR`), and closes the loop by
writing the postmortem back into that memory: every resolved incident improves
the diagnosis of the next one.

## Architecture

```
frontend (React + Vite, :5173)
        │  /api → proxy → :8000
backend FastAPI (:8000)
        │  agent loop (Claude via Bedrock) ── search_memory / query_incidents
        ▼
CockroachDB (incidents table with VECTOR(1024) + vector index)
```

- **Backend** (`backend/`): FastAPI + LLM agent. The agent loop is provider
  agnostic (Bedrock by default, Anthropic API as an alternative). Reads take a
  dual path: Cockroach Managed MCP Server with a psycopg fallback.
- **Frontend** (`frontend/`): React + Vite + TypeScript, no extra dependencies.
  Three views: ticket queue (manual creation or random generation, with editing
  and deletion), incident view (diagnosis with a **live SSE** evidence timeline)
  and memory explorer (edit, delete and supersede).
- Full reference (data model, API, design decisions):
  [`docs/recall-DOCUMENTATION.md`](docs/recall-DOCUMENTATION.md).

## Requirements

- Python 3.11+
- Node 18+
- A CockroachDB cluster (Cloud serverless is enough) with `VECTOR` support
- Bedrock access, either through AWS credentials (SigV4) or an API key in
  `BEDROCK_API_KEY`. **Titan embeddings are mandatory**: `ANTHROPIC_API_KEY` only
  replaces the LLM, not embedding generation, so without Bedrock you cannot seed
  or write to memory

## Getting started

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # fill in DATABASE_URL, Cockroach MCP and Bedrock access

.venv/bin/python -m app.db              # creates/updates the schema
.venv/bin/python -m seed.seed_memory    # example incidents + tickets (idempotent)
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173 (proxy /api → :8000)
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/health` | Health check (includes MCP status) |
| GET  | `/tickets` | Queue of open tickets |
| POST | `/tickets` | Manual ticket ingestion |
| POST | `/tickets/generate?n=1` | Generates `n` synthetic tickets |
| POST | `/tickets/seed` | Loads the example incidents and tickets (idempotent) |
| DELETE | `/tickets` | Empties the queue (only `status != 'resolved'`) |
| GET  | `/tickets/{id}` | Ticket detail |
| PATCH | `/tickets/{id}` | Edits title, symptom, area or severity |
| DELETE | `/tickets/{id}` | Deletes a ticket |
| POST | `/tickets/{id}/handle` | Runs the agent loop → diagnosis + evidence |
| GET  | `/tickets/{id}/handle/stream` | Same as `handle`, over SSE: `evidence`, `result`, `agent_error` events |
| GET  | `/tickets/{id}/diagnosis` | Last saved diagnosis, evidence included (404 if never diagnosed) |
| POST | `/incidents/{ticket_id}/resolve` | Writes the postmortem (memory grows) |
| POST | `/incidents/{ticket_id}/feedback` | 👍/👎 adjusts the quality of the cited incident |
| GET  | `/memory?service=...` | Memory inspection |
| PATCH | `/memory/{id}` | Edits an incident (re-embeds if title or symptom changes) |
| DELETE | `/memory/{id}` | Deletes an incident |
| DELETE | `/memory` | Wipes the whole memory |
| POST | `/memory/{id}/supersede` | Marks an incident as superseded by another |

## Demo flow

The example dataset is a computer and phone repair shop: the areas are
`hardware-pc`, `software-pc`, `hardware-phone` and `software-phone` (§9 of the
docs). The domain lives in `TEMPLATES`, in the seeds and in the agent prompt
(`agent/loop.py`, `agent/tools.py`); the rest of the system is agnostic.

1. **Memory** — starts with the seeded incidents.
2. **Generate random** (or **New ticket** to enter one by hand) — it shows up in the queue.
3. **Diagnose** — the timeline shows live which tools the agent uses and what it
   recalls; at the end, root cause + mitigation + confidence.
4. **Resolve** — the postmortem is embedded into memory.
5. **Feedback 👍** — raises the `quality_score` of the cited incident.
6. A second similar ticket now ranks better: that delta is the demo.

Product rule: if memory has no precedent, the agent says so with low confidence
instead of making up a root cause. `software-phone` deliberately has no seeded
incidents so that case can be shown.

### What **Load examples** puts in

One click loads 25 incidents and 12 tickets built to exercise the interesting
cases by hand:

- **Competing precedents** — 3-4 incidents per symptom family, so the top 5 has
  to actually discriminate.
- **Quality beats distance** — TKT-001 ("will not boot") has three candidates:
  `INC-007` carries `quality_score 0.8` and wins over the more recent `INC-008`,
  which sits at `-0.6`.
- **Superseded chain** — TKT-006 ("reboot loop") should surface `INC-015` and not
  `INC-004`, the obsolete procedure it replaced.
- **Expired knowledge** — TKT-007 only matches `INC-003`, which is past its
  `valid_until`: recall comes back empty and the agent has to say so.
- **No precedent** — the two `software-phone` tickets, plus TKT-009, whose symptom
  family has no seeded incident even though its area does.
- **Queue variety** — the four severities, one ticket with no service assigned
  (TKT-008, an ambiguous symptom) and one already in `handling` (TKT-011).

Seeding is idempotent: a second click changes nothing. The first one embeds 25
incidents sequentially, so it takes a few seconds.

### Migrating an older database

The service values used to be `hardware-celular` / `software-celular`. If you
have rows from before that rename:

```sql
UPDATE incidents SET service = replace(service, '-celular', '-phone') WHERE service LIKE '%-celular';
UPDATE tickets   SET service = replace(service, '-celular', '-phone') WHERE service LIKE '%-celular';
```

Severity used to be `sev1`..`sev4`. If you have rows from before that rename:

```sql
UPDATE incidents SET severity = CASE severity
    WHEN 'sev1' THEN 'critical' WHEN 'sev2' THEN 'high'
    WHEN 'sev3' THEN 'medium'   WHEN 'sev4' THEN 'low'
END WHERE severity LIKE 'sev_';
UPDATE tickets SET severity = CASE severity
    WHEN 'sev1' THEN 'critical' WHEN 'sev2' THEN 'high'
    WHEN 'sev3' THEN 'medium'   WHEN 'sev4' THEN 'low'
END WHERE severity LIKE 'sev_';
```

For a demo database, clearing both tables and pressing **Load examples** works too.

## Deploy on AWS

Four AWS services, all inside the always-free tier — the only thing you pay for
is Bedrock tokens.

```
browser
  ├─ GET /  ────────────→ CloudFront ──(OAC)──→ S3 (Vite bundle)
  └─ fetch + EventSource ─────────────────────→ Lambda Function URL
                                                  (InvokeMode: RESPONSE_STREAM)
                                                     ↓ Web Adapter → uvicorn → FastAPI
                                                     ├→ Bedrock (execution role, SigV4)
                                                     └→ CockroachDB (MCP + psycopg)
```

- **Lambda** runs the agent loop. The [AWS Lambda Web
  Adapter](https://github.com/awslabs/aws-lambda-web-adapter) is attached as a
  public layer, so the same FastAPI app runs unchanged; `AWS_LWA_INVOKE_MODE=response_stream`
  plus a Function URL in `RESPONSE_STREAM` mode keep the SSE evidence timeline
  streaming incrementally instead of buffering to the end.
- **S3 + CloudFront** serve the frontend. The bucket stays private: CloudFront
  reads it through an Origin Access Control.
- Bedrock is reached through the function's execution role, so no keys are
  deployed. `BEDROCK_API_KEY` stays empty.

Everything lives in `backend/template.yaml` (SAM) and deploys with one command.
Its parameters are read from `backend/.env`, so no secret is committed:

```bash
aws sts get-caller-identity   # credentials must be valid first
./deploy.sh                   # builds, deploys, uploads the frontend, invalidates the cache
```

The script prints the app URL and the API URL when it finishes. To check that
the stream really is incremental — the events must arrive with separate
timestamps, not all at once at the end:

```bash
FN=$(aws cloudformation describe-stacks --stack-name recall \
     --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text)
TID=$(curl -s "$FN/tickets" | jq -r '.[0].id')
curl -N --no-buffer "$FN/tickets/$TID/handle/stream" \
  | while IFS= read -r line; do echo "$(date +%s.%N) $line"; done
```

Notes:

- `AWS_REGION` is a reserved Lambda variable and cannot be set in the template;
  the function inherits the region it is deployed to. Since the default
  `BEDROCK_MODEL_ID` uses the `us.` inference profile prefix, deploy to a `us-*`
  region or override the parameter.
- The Lambda package is built for `arm64` / Python 3.13, so the `pip install`
  needs `--platform` (see `deploy.sh`): installing macOS wheels produces a
  function that dies importing `psycopg`.
- Schema creation and seeding are not part of the deploy. Run `python -m app.db`
  and `python -m seed.seed_memory` locally against the same `DATABASE_URL`, or
  use the **Load examples** button once the app is up.

## Tests

```bash
cd backend
.venv/bin/pytest        # pure unit tests: no DB or AWS needed
.venv/bin/ruff check .

cd ../frontend
npm run build           # type-check (tsc --noEmit) + build
```
