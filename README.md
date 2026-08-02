# Recall

On-call copilot with semantic incident memory, built for the
**CockroachDB × AWS — Build with Agentic Memory** hackathon.

It takes in incident tickets, diagnoses them with an LLM agent that queries a
vector memory of past incidents (CockroachDB + `VECTOR`), and closes the loop by
writing the postmortem back into that memory: every resolved incident improves
the diagnosis of the next one.

> **Live demo**: https://d2n13wfb8jv9v.cloudfront.net
> **Demo video** (2:57): https://youtu.be/L3CkZax88dU
> **Submission**: [`SUBMISSION.md`](SUBMISSION.md) — which CockroachDB tools and
> AWS services this uses, and how.

## Architecture

```
frontend (React + Vite, :5173)
        │  /api → proxy → :8000
backend FastAPI (:8000)
        │  agent loop (provider agnostic) ── search_memory / query_incidents
        ▼
CockroachDB (incidents table with VECTOR(1024) + vector index)
```

- **Backend** (`backend/`): FastAPI + LLM agent. The agent loop is provider
  agnostic — Gemini, Bedrock or the Anthropic API, see [Providers](#providers).
  Reads take a dual path: Cockroach Managed MCP Server with a psycopg fallback.
- **Frontend** (`frontend/`): React + Vite + TypeScript, no extra dependencies.
  Three views: ticket queue (manual creation or random generation, with editing
  and deletion), incident view (diagnosis with a **live SSE** evidence timeline)
  and memory explorer (edit, delete and supersede).
- Full reference (data model, API, design decisions):
  [`docs/recall-DOCUMENTATION.md`](docs/recall-DOCUMENTATION.md).

## Requirements

- Python 3.13 (what CI and Lambda pin; 3.11+ works locally)
- Node 18+
- A CockroachDB cluster (Cloud serverless is enough) with `VECTOR` support
- One model provider — a `GEMINI_API_KEY` is enough on its own and is what the
  deployed stack uses by default. See [Providers](#providers)

## Providers

Two independent switches, both in `backend/.env`:

| Variable | Accepts | Default in `config.py` | What the stack deploys |
|---|---|---|---|
| `LLM_PROVIDER` | `gemini`, `bedrock`, `anthropic` | `bedrock` | `gemini` |
| `EMBEDDING_PROVIDER` | `gemini`, `bedrock` | `bedrock` | `gemini` |

- **Gemini** (`GEMINI_API_KEY`) covers both roles with a single key, on the free
  tier. This is the cheapest way to run the project end to end.
- **Bedrock** covers both roles too (Claude + Titan), through AWS credentials
  (SigV4) or an API key in `BEDROCK_API_KEY`.
- **Anthropic** (`ANTHROPIC_API_KEY`) only replaces the LLM. There is no Anthropic
  embedder, so `EMBEDDING_PROVIDER` still has to be `gemini` or `bedrock`.

Both embedders produce 1024 dimensions — Titan natively, Gemini through
`output_dimensionality` plus a re-normalisation — so switching between them does
not force a migration of the `VECTOR(1024)` column. It *does* mean the vectors
already stored were produced by another model: re-embed the memory (wipe it and
press **Load examples**, or edit each incident) or recall will compare apples to
oranges.

## Getting started

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # fill in DATABASE_URL, Cockroach MCP and your provider key

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
| GET  | `/tickets` | Queue. Filters: `?service=`, `?severity=`, `?status=`, `?search=` (title substring), `?order=asc\|desc`. Without `status` it hides resolved tickets |
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

If a database is left over from an older schema, or from another embedding model,
the shortest fix is to clear both tables and press **Load examples** again.

## Deploy on AWS

Four AWS services, all inside the always-free tier — the only thing you pay for
is model tokens, and with Gemini on the free tier that is nothing either.

```
browser
  ├─ GET /  ────────────→ CloudFront ──(OAC)──→ S3 (Vite bundle)
  └─ fetch + EventSource ─────────────────────→ Lambda Function URL
                                                  (InvokeMode: RESPONSE_STREAM)
                                                     ↓ Web Adapter → uvicorn → FastAPI
                                                     ├→ LLM provider (Gemini API by default,
                                                     │   Bedrock via the execution role)
                                                     └→ CockroachDB (MCP + psycopg)
```

- **Lambda** runs the agent loop. The [AWS Lambda Web
  Adapter](https://github.com/awslabs/aws-lambda-web-adapter) is attached as a
  public layer, so the same FastAPI app runs unchanged; `AWS_LWA_INVOKE_MODE=response_stream`
  plus a Function URL in `RESPONSE_STREAM` mode keep the SSE evidence timeline
  streaming incrementally instead of buffering to the end.
- **S3 + CloudFront** serve the frontend. The bucket stays private: CloudFront
  reads it through an Origin Access Control.
- If you deploy on Bedrock, it is reached through the function's execution role,
  so no keys are deployed and `BEDROCK_API_KEY` stays empty. Gemini and Anthropic
  do need their key as a stack parameter.

The stack lives in `backend/template.yaml` (SAM) and is applied by `deploy.sh`,
which builds the Lambda package, deploys, uploads the Vite bundle to S3 and
invalidates CloudFront.

> The Function URL is `AuthType: NONE`, so the reads and the `handle` endpoints
> are open to anyone with the link. Set `DEMO_API_KEY` and the destructive ones
> (`DELETE /memory`, `DELETE /tickets`, the `PATCH`es) start demanding an
> `X-API-Key` header; leave it empty and they stay open, which is only fine
> locally. The frontend picks the key up from `VITE_DEMO_API_KEY`, which
> `deploy.sh` injects at build time.

If `ccloud` is on the `PATH` and logged in, `deploy.sh` checks the cluster is up
before building anything: a paused cluster would otherwise produce a green deploy
and a Lambda that fails at runtime. Without `ccloud` the check is skipped.
`CREATE_CLUSTER=1 ./deploy.sh` creates the free-tier Basic cluster and stops.
This only works from a workstation — `ccloud` has no non-interactive login, so
the CI deploy skips it.

### From CI (the usual path)

The `Deploy` workflow (`.github/workflows/deploy.yml`) is a `workflow_dispatch`:
it runs `ruff` and `pytest`, assumes an AWS role over OIDC — no long-lived keys
in GitHub — and then runs the same `deploy.sh`. If the stack fails it prints the
failing CloudFormation events.

One-time bootstrap: deploy `infra/github-oidc.yaml`, which creates the OIDC
provider and the `recall-github-deploy` role, and take its `RoleArn` output.
Then configure the repo:

| Secrets | Variables |
|---|---|
| `AWS_ROLE_ARN` | `AWS_REGION` |
| `DATABASE_URL` | `COCKROACH_MCP_URL`, `COCKROACH_MCP_CLUSTER_ID` |
| `COCKROACH_MCP_API_KEY` | `LLM_PROVIDER`, `EMBEDDING_PROVIDER` |
| `GEMINI_API_KEY` | `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` |
| `DEMO_API_KEY` | `BEDROCK_MODEL_ID`, `BEDROCK_EMBEDDING_MODEL_ID` |

The trust policy is matched against the `sub` claim GitHub emits, which carries
the immutable numeric IDs of the owner and the repo, not their names — copying a
`repo:owner/name:ref:...` subject by hand does not work.

### From your machine

`deploy.sh` reads both the stack parameters and the AWS credentials from
`backend/.env`, so nothing has to be exported by hand:

```bash
# backend/.env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...      # only for temporary credentials

./deploy.sh                # builds, deploys, uploads the frontend, invalidates the cache
```

> If you already have `AWS_ACCESS_KEY_ID` and friends exported in your shell,
> unset them. The backend gives precedence to the real environment variable over
> the `.env` file, so a stale export silently wins over the file.

### Checking the deploy

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

- The Lambda package is built from `backend/requirements-lambda.txt`, not from
  `requirements.txt`: it is the same list minus `pytest` and minus the SDKs the
  deployed provider does not need. Switching `LLM_PROVIDER` to a provider whose
  SDK is not in that file produces a function that dies on import.
- The package is built for `arm64` / Python 3.13, so the `pip install` needs
  `--platform` (see `deploy.sh`): installing macOS wheels produces a function that
  dies importing `psycopg`.
- `backend/certs/cockroach-root.crt` travels inside the package and
  `PGSSLROOTCERT` points at it. `sslmode=verify-full` needs a CA and
  `sslrootcert=system` does not provide one here: the OpenSSL bundled in the
  `psycopg[binary]` wheel looks in the `OPENSSLDIR` of its own build, which does
  not exist on Lambda. Point at the CA with the environment variable, not with a
  parameter in `DATABASE_URL` — the URL parameter wins over the variable.
- The Web Adapter layer is pinned to a specific version in `template.yaml`. AWS
  retires old ones: if the deploy fails resolving the layer ARN, bump it.
- `AWS_REGION` is a reserved Lambda variable and cannot be set in the template;
  the function inherits the region it is deployed to. If you deploy on Bedrock,
  the `BEDROCK_MODEL_ID` inference profile prefix has to match that region
  (`us.` for `us-*`, and so on).
- Schema creation and seeding are not part of the deploy. Run `python -m app.db`
  and `python -m seed.seed_memory` locally against the same `DATABASE_URL`, or
  use the **Load examples** button once the app is up.

Runbooks for all of this live in `.claude/skills/`: `recall-deploy`,
`recall-bootstrap-aws` and `recall-switch-llm-provider`.

## Tests

```bash
cd backend
.venv/bin/pip install ruff==0.15.22    # not in requirements.txt; same pin as CI
.venv/bin/pytest        # pure unit tests: no DB, no AWS, no model calls
.venv/bin/ruff check .

cd ../frontend
npm run build           # type-check (tsc --noEmit) + build
```
