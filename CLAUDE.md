# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Everything runs from `backend/` with the local venv (`.venv/bin/...`):

```bash
.venv/bin/pip install -r requirements.txt ruff==0.15.22
.venv/bin/python -m app.db              # creates/updates the schema in Cockroach
.venv/bin/python -m seed.seed_memory    # loads example incidents + tickets (idempotent by external_id)
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/docs

.venv/bin/pytest                        # full suite (needs neither DB nor AWS)
.venv/bin/pytest tests/test_ranking.py::test_x   # a single test
.venv/bin/ruff check .
```

`ruff` is not in `requirements.txt`: it is installed alongside it, pinned to the
same version CI uses (`.github/workflows/deploy.yml`).

Frontend from `frontend/`:

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api → :8000
npm run build   # tsc --noEmit && vite build — this is the type-check gate
```

The tests are pure unit tests: they mock `db` and the providers, and
`tests/conftest.py` sets a dummy `DATABASE_URL`. They never start Cockroach or
call a model provider.

Deploying is a separate path — see `## Deploy` below.

## Architecture

FastAPI backend (Python 3.13, the runtime CI and Lambda pin) for an on-call
copilot: it receives incident tickets, diagnoses them with an LLM agent backed by
semantic memory of past incidents, and closes the loop by writing the postmortem
back into that memory.
The frontend (`frontend/`, React + Vite + TS, :5173) has three views — ticket
queue, incident view and memory explorer — with no router and no state manager:
everything is `useState`, `fetch` and the one shared hook in
`frontend/src/hooks.ts` (`useAsync`). The API base is
`import.meta.env.VITE_API_BASE ?? '/api'` (`frontend/src/api.ts`): in dev that
falls through to the Vite proxy `/api` → `:8000`, and `deploy.sh` injects the
Lambda Function URL at build time.

Core flow: `POST /tickets/{id}/handle` → `agent/loop.handle()` → the LLM calls
`search_memory` / `query_incidents` → it ends with `submit_diagnosis`. The router
persists the result with `diagnoses.save()`, so reopening the ticket does not run
the agent again. It also drives the ticket status: `handling` while the agent
runs, rolled back to `open` if it fails — both in the plain handler and in the
`finally` of the SSE one. `tests/test_ticket_status.py` is the gate. Then a human
calls `POST /incidents/{ticket_id}/resolve` (the path param is a **ticket** id,
not an incident id), which re-embeds the resolved incident into `incidents`
(`postmortem.write_postmortem`).

Streaming variant: `GET /tickets/{id}/handle/stream` (SSE, a GET because the
browser `EventSource` only supports GET). The core of the loop is the
`loop.handle_events()` generator, which emits `("evidence", EvidenceStep)` for
every tool executed and a final `("result", HandleResponse)`; `handle()` is a
wrapper that consumes it. The frontend (`IncidentView`) consumes the stream and
paints the evidence timeline live. When touching the loop, keep the event
contract: both endpoints share the same generator.

Layers and their boundaries:

- `app/api/*` — thin routers, no logic; validation via `app/models.py` (Pydantic).
  `app/api/deps.py` holds what they share: `get_ticket_or_404` and the error
  strings. The full route list lives in the `## API` table of `README.md` and in
  §5 of the docs; a new route goes in both.
- `app/config.py` — every environment variable and every tuning knob (ranking
  weights, `recall_top_k`, `agent_max_turns`), as one Pydantic `Settings`.
- `app/memory.py` — the **only** layer that talks to the `incidents` table: vector
  recall, ranking, citations, feedback, supersede.
- `app/tickets.py` — `TicketSource` is a `Protocol`; today the only implementation
  is `MockTicketSource` (DB + synthetic generator). Integrating Jira/PagerDuty
  means adding another implementation, not touching the rest.
- `app/diagnoses.py` — the **only** layer that talks to the `diagnoses` table: the
  last `HandleResponse` of each ticket, stored whole as JSONB. One row per ticket,
  upserted; the row dies with the ticket via `ON DELETE CASCADE`. Saving happens in
  the router, not in `loop.py`, so the agent loop stays free of DB writes.
- `app/agent/` — `tools.py` declares the `ToolSpec`s and executes them; `loop.py`
  runs the turn loop. The loop is provider agnostic: it speaks the dataclasses of
  `providers/base.py` (`Message`, `ToolUse`, `ToolResult`, `Turn`).
- `app/postmortem.py` — `write_postmortem()`: the only writer that closes the
  loop, turning a resolved ticket into a new row in `incidents`.
- `app/providers/` — `registry.py` resolves `LLM_PROVIDER` / `EMBEDDING_PROVIDER`
  to an implementation (lazy import, `lru_cache`). LLM: `bedrock | anthropic |
  gemini`. Embedder: `bedrock | gemini` — there is no Anthropic embedder. The
  dataclass defaults still say `bedrock`, but everything that actually runs
  (`backend/.env`, `template.yaml`, `deploy.sh`) is on `gemini`.
- `app/db.py` — psycopg pool + `fetch` / `execute` / `render` helpers.
- `app/mcp/cockroach_client.py` — client for the Cockroach Managed MCP Server.

### Dual read path (MCP with fallback)

`memory._read()` tries the MCP first (rendering the SQL with `db.render`) and, if
it is not configured or fails, falls back to psycopg. Every read returns
`(rows, via)` with `via` ∈ `"mcp" | "fallback"`, and that value travels all the
way to the `EvidenceStep` of the response. **Writes** always go through psycopg.
When touching `memory.py`, keep the SQL parameterized with `%s` — `render()`
depends on that.

### Ranking and validity

`rank_score = distance - w_quality*quality_score + w_age*age_penalty` (lower is
better). The `ORDER BY embedding <=> %s::VECTOR(n)` must stay textually like that
so the Cockroach vector index can accelerate it; the re-ranking happens in Python
over `recall_candidates` and is cut at `recall_top_k`.

An incident is current if `valid_until` is null or in the future and
`superseded_by` is null. That condition is duplicated on purpose in two places —
`CURRENT_SQL_FILTER` (SQL) and `validity_of()` (Python, for whatever comes back
from the MCP); if one changes, the other changes too. `is_recallable()` builds on
`validity_of()` and additionally requires the row to carry a `distance`. `tests/test_recall_sql.py`
and `test_recall_filters.py` are the gate.

### Agent contract

`Diagnosis` is validated with Pydantic against whatever `submit_diagnosis`
returns; if it does not validate, the error goes back to the model as a
`tool_result` with `is_error` and the loop continues. If `submit_diagnosis`
arrives in the same turn as other tools, it is discarded (the model has not seen
the results yet). Once `agent_max_turns` is exhausted, `NO_DIAGNOSIS` is returned
with `confidence=0.0`. The product rule: with no precedent in memory, the agent
has to say so, not invent a root cause.

## Deploy

The canonical path is the `Deploy` workflow (`.github/workflows/deploy.yml`):
`workflow_dispatch`, assumes an AWS role over OIDC, gates on `ruff check` +
`pytest`, and then runs `./deploy.sh` — the same script that can be run from a
laptop. `deploy.sh` builds an arm64 package, deploys the SAM stack in
`backend/template.yaml` (Lambda + Function URL in `RESPONSE_STREAM` + S3 +
CloudFront) and uploads the Vite bundle. `infra/github-oidc.yaml` creates the
OIDC provider and the deploy role once per account.

Things that only exist for the deploy, and are easy to break from the outside:

- **`backend/requirements-lambda.txt` is a second dependency file** that diverges
  from `requirements.txt`: it drops `anthropic` and `pytest`. A dependency the
  runtime needs has to go in both. Today, deploying with `LLM_PROVIDER=anthropic`
  fails on import because the SDK is not in the package.
- `backend/run.sh` is the Lambda entrypoint (the Web Adapter execs it; there is
  no Python handler), and `backend/certs/cockroach-root.crt` is the CA bundle
  `PGSSLROOTCERT` points at. Both are copied into the package by `deploy.sh`.
- `CORS_ORIGINS` is computed at deploy time from the CloudFront domain
  (`template.yaml`); locally it comes from `.env`.

The runbooks are the skills in `.claude/skills/`: `recall-deploy` (deploy,
diagnose a red run, read the logs), `recall-bootstrap-aws` (prepare an account
and a repo) and `recall-switch-llm-provider` (move the deployed app between
providers).

## Repo conventions

- Code, prompts, log messages, UI strings and test names are all in English.
  Follow that style.
- The embedding dimensions (`embedding_dims=1024`) have to match the
  `VECTOR(1024)` in `schema.sql`: changing the embedding model means migrating
  the table. Both embedders shipped today hit 1024 — Titan natively, Gemini via
  `output_dimensionality` plus a re-normalisation — so switching between them
  does not migrate the table, but it does mean re-embedding what is stored.
- `BEDROCK_MODEL_ID` requires an inference profile prefix matching `AWS_REGION`
  (`us.`, `eu.`, `au.`, `jp.`, `global.`); the bare ID fails. Embedding models,
  on the other hand, use the bare ID. Details in `.env.example` and §7 of the docs.
- `frontend/src/types.ts` mirrors the Pydantic models in `app/models.py`: if a
  model that travels over the API changes, update both sides. The file also
  holds UI-only state that mirrors nothing (`SERVICES`, `TicketFilters`); keep
  the two groups apart.
- `docs/recall-DOCUMENTATION.md` is the long-form reference (data model, API,
  environment variables, roadmap).
