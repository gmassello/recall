# Recall — hackathon submission

**CockroachDB × AWS — Build with Agentic Memory**

An on-call copilot whose memory *is* CockroachDB. It takes in incident tickets,
diagnoses them with an LLM agent that searches a vector memory of past incidents,
and closes the loop by writing the postmortem back into that memory — every
resolved incident improves the diagnosis of the next one.

| | |
|---|---|
| **Live demo** | https://d2n13wfb8jv9v.cloudfront.net |
| **Video** | _pending_ |
| **Repo** | https://github.com/gmassello/recall |
| **License** | [MIT](LICENSE) |
| **Reference docs** | [`docs/recall-DOCUMENTATION.md`](docs/recall-DOCUMENTATION.md) |

---

## Requirements checklist

| Requirement | Status | Evidence |
|---|---|---|
| Agentic app using CockroachDB as its memory layer | ✅ | `backend/app/agent/loop.py` runs the turn loop; `backend/app/memory.py` is the only layer that talks to the `incidents` table |
| At least 2 CockroachDB tools | ✅ 3 of 4 | Managed MCP Server, Distributed Vector Indexing, `ccloud` CLI — detailed below |
| At least 1 AWS service | ✅ 5 | Lambda, Function URL, S3, CloudFront, IAM/OIDC — detailed below |
| Public open-source repository | ✅ | https://github.com/gmassello/recall |
| OSS license visible at the top of the repo | ✅ | [`LICENSE`](LICENSE), MIT |
| Project newly created during the submission period | ✅ | First commit 2026-07-19; the period opened 2026-06-30. No prior history |
| README with dependencies and setup instructions | ✅ | [`README.md`](README.md) |
| Functional demo URL, free and unrestricted | ✅ | CloudFront link above; `GET /health` reports MCP status |
| Demo video under 3 minutes | ⬜ | Script in `docs/recall-DOCUMENTATION.md` §11 |
| Identify which CockroachDB tools were used | ✅ | This file |
| Identify which AWS services were used | ✅ | This file |
| Architecture diagram (optional) | ✅ | `README.md` and `docs/recall-DOCUMENTATION.md` §3 |

---

## CockroachDB tools used

### 1. Cloud Managed MCP Server — at runtime, not just in the IDE

Most projects wire the MCP server into their editor. Here it is a **production read
path**: the deployed Lambda queries CockroachDB through the Managed MCP Server, and
falls back to psycopg only when the MCP is unavailable.

- `backend/app/mcp/cockroach_client.py` — `streamablehttp_client` with a bearer
  token and the `mcp-cluster-id` header. It discovers the SQL tool at runtime
  (`select_query`, or any tool whose name contains `sql`/`quer`) and infers both
  the argument name (`query` / `sql` / `statement`) and whether a `database`
  argument is required, so a change on the server side does not break the client.
- `backend/app/memory.py` — `_read()` renders the parameterized SQL with
  `db.render` and tries the MCP first. Every read returns `(rows, via)` with
  `via ∈ {"mcp", "fallback"}`.
- That `via` travels all the way to the `EvidenceStep` of the API response and is
  painted in the frontend timeline: while the agent reasons, you can see which of
  its lookups went through the MCP.
- `probe()` is exposed in `GET /health`, so the deployed app reports MCP health.
- **Writes always go through psycopg** — a deliberate boundary, not an oversight.

### 2. Distributed Vector Indexing — the semantic memory itself

- `backend/schema.sql:18,21` — `incidents.embedding VECTOR(1024)` and
  `CREATE VECTOR INDEX incidents_embedding_idx ON incidents (embedding vector_cosine_ops)`.
- `backend/app/db.py:56` enables `feature.vector_index.enabled` before applying
  the schema.
- Recall selects `embedding <=> %s::VECTOR(n) AS distance` and orders by that
  alias — `EXPLAIN` shows it planning as `vector search →
  incidents@incidents_embedding_idx`, same as repeating the expression, while
  keeping the query under the 16 KB the Managed MCP Server accepts. It
  over-fetches `recall_candidates=40`, then re-ranks in Python:
  `rank_score = distance - 0.15*quality_score + 0.10*age_penalty` (lower is
  better), cut at `recall_top_k=5`.
- Validity is enforced in SQL: an incident is recallable only while
  `valid_until IS NULL OR valid_until > now()` and `superseded_by IS NULL`.
  Superseded knowledge stops being recalled without being deleted.
- Embeddings and transactional data live in the same database — the tickets,
  the diagnoses (JSONB) and the vector memory are one system, one transaction
  boundary, no separate vector store to keep in sync.

### 3. `ccloud` CLI — cluster preflight in the deploy

`deploy.sh` already refused to deploy with invalid AWS credentials; it now refuses
to deploy against a cluster that is not up. Without this, a paused or deleted
cluster produces a green deploy and a Lambda that only fails at runtime.

- `deploy.sh` runs `ccloud cluster list` and checks the configured cluster is
  present and in `CLUSTER_STATE_CREATED` before building anything.
- Skipped silently when `ccloud` is not installed, so deploying from a laptop
  without it behaves exactly as before.
- `CREATE_CLUSTER=1 ./deploy.sh` creates the free-tier Basic cluster
  (`ccloud cluster create basic`) and stops — cluster creation is a one-time
  bootstrap, not something a deploy script should do on every run.
- **This runs on a workstation, not in CI.** `ccloud` 0.6.12 has no
  non-interactive authentication: no `--api-key` flag and no environment
  variable, only the browser flow of `ccloud auth login`. A service-account key
  authenticates against the Cloud REST API, not against the CLI. Rather than
  pretend otherwise, the GitHub Actions deploy skips the check and the script
  degrades to exactly its previous behaviour. This is the one piece of feedback
  we have on the CockroachDB tooling: a headless login would make `ccloud`
  usable from a pipeline.

### Not used

**Agent Skills Repo.** The minimum is 2 tools; this submission uses 3. The repo
does ship its own operational skills under `.claude/skills/` (`recall-deploy`,
`recall-bootstrap-aws`, `recall-switch-llm-provider`).

---

## AWS services used

| Service | How |
|---|---|
| **Lambda** | Python 3.13 on arm64, 1024 MB. No Python handler: the AWS Lambda Web Adapter layer execs `backend/run.sh`, which starts the FastAPI app unchanged — the same process runs locally and in production |
| **Lambda Function URL** | `InvokeMode: RESPONSE_STREAM` plus `AWS_LWA_INVOKE_MODE=response_stream`. This is what makes the SSE evidence timeline arrive incrementally instead of buffering until the agent finishes |
| **S3** | Private bucket holding the Vite bundle, with every public-access block on |
| **CloudFront** | Distribution in front of S3 with an Origin Access Control; its domain is what `CORS_ORIGINS` is computed from at deploy time |
| **IAM + GitHub OIDC** | `infra/github-oidc.yaml` creates the provider and the deploy role. The Deploy workflow assumes it over OIDC — there are no long-lived AWS keys anywhere in the repo or in GitHub |
| **CloudFormation / SAM** | `backend/template.yaml` is the whole stack; `deploy.sh` is the same script CI runs |
| **Bedrock** | Supported LLM and embedding provider (Claude via the Converse API, Titan for embeddings), behind the provider abstraction. The stack ships an `bedrock:InvokeModel` policy scoped to inference profiles and the two model families |

The deployed stack currently runs Gemini as the model provider because it is free
to operate for a public demo. Switching to Bedrock is two variables — see
`.claude/skills/recall-switch-llm-provider`.

---

## Deliverables

| Deliverable | Status | Link |
|---|---|---|
| Public repository | ✅ | https://github.com/gmassello/recall |
| MIT license file | ✅ | [`LICENSE`](LICENSE) |
| Deployed demo | ✅ | https://d2n13wfb8jv9v.cloudfront.net |
| README with setup | ✅ | [`README.md`](README.md) |
| Long-form documentation | ✅ | [`docs/recall-DOCUMENTATION.md`](docs/recall-DOCUMENTATION.md) |
| Architecture diagram | ✅ | `docs/recall-DOCUMENTATION.md` §3 |
| Tool identification (this file) | ✅ | `SUBMISSION.md` |
| Destructive endpoints protected | ✅ | `backend/app/api/deps.py`, `tests/test_api_auth.py` |
| Demo video < 3 min | ⬜ | Script in §11 |
| Devpost form submitted | ⬜ | Deadline 2026-08-18, 5pm EDT |

---

## Judging criteria

**Agentic memory design.** Memory here is not a transcript buffer. It is a curated
store with a lifecycle: incidents are written by `postmortem.write_postmortem()`
only when a human resolves a ticket, they accumulate `quality_score` from thumbs
up/down feedback, they age out through `valid_until`, and they are chained through
`superseded_by` when newer knowledge replaces them. Ranking combines all three —
semantic distance, earned quality, and age. That is what a memory layer has to do
to survive contact with a real on-call rotation, where last year's runbook is worse
than useless.

**Technical implementation.** The MCP read path is real and falls back cleanly.
The agent loop is provider-agnostic at the dataclass level (`providers/base.py`),
so Gemini, Bedrock and Anthropic are one environment variable apart. 89 unit tests
run with no database and no cloud credentials. `ruff` and `pytest` gate the deploy.

**Real-world impact.** On-call knowledge dies in Slack threads and closed tickets.
The loop this closes — diagnose from precedent, resolve, write the postmortem back
as precedent — is the thing every incident retro promises and no team actually does.

**Production readiness.** Deployed over OIDC with no static credentials; TLS to
CockroachDB with a pinned CA bundle; destructive endpoints behind a shared key;
the evidence timeline is observability the operator can read while the agent is
still thinking; ticket status rolls back to `open` if the agent fails, in both the
plain and the streaming handler.

**Creativity.** Using the Managed MCP Server as a production read path with a
psycopg fallback — and surfacing which path each lookup took in the UI — is not
what the tool is normally used for.

---

## Known limitations

- **`MockTicketSource`** is the only `TicketSource` implementation. Jira and
  PagerDuty are a `Protocol` away (`backend/app/tickets.py`), but not written.
- **The Function URL is `AuthType: NONE`.** Reads and the agent loop are open on
  purpose so judges can drive the demo without credentials; only the destructive
  endpoints demand `X-API-Key`. And that key ships inside the JavaScript bundle,
  because the memory explorer has to be able to edit and delete — so it stops
  drive-by requests and crawlers, not anyone willing to open devtools. Real auth
  here means a session in front of the app (Cognito, or an authorizer on the
  Function URL), which is worth doing the moment this stops being a demo.
- **`docs/recall-DOCUMENTATION.md` §10** describes history ingestion and offline
  evaluation. That section is design, not shipped code, and says so.
- **No changefeeds and no multi-region.** Both are natural next steps for this
  data model and neither is faked here.
