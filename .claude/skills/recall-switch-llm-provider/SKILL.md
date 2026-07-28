---
name: recall-switch-llm-provider
description: >
  Switch the deployed recall backend between Gemini, Bedrock and Anthropic. Covers the repo
  variables and secrets, the stack parameters that carry them, the SDK that has to be in the
  Lambda requirements, and the embedding migration a provider change can force. Use it to move
  the deployed app to another LLM or embedder, or to check what a given provider still needs.
argument-hint: "<gemini | bedrock | anthropic>"
allowed-tools: Bash, Read, Grep, Glob
---

# Switching the LLM provider

No application code changes. `app/providers/registry.py` resolves `LLM_PROVIDER` and
`EMBEDDING_PROVIDER` at runtime with a lazy import, so a switch is pure deploy wiring.

## The four places a provider lives

1. **Repo variables** — `LLM_PROVIDER`, `EMBEDDING_PROVIDER` (`gh variable set`).
2. **Repo secret** — the provider's credential (`gh secret set`).
3. **Stack parameters** — `backend/template.yaml` turns each one into a Lambda environment variable;
   `deploy.sh` passes them as `--parameter-overrides`; `.github/workflows/deploy.yml` passes them to
   `deploy.sh` as `env:`. All three files have to agree.
4. **`backend/requirements-lambda.txt`** — a deliberate *subset* of `requirements.txt`. A missing SDK
   here builds fine and dies at runtime, which is the slowest possible way to find out.

Read the values from `backend/.env` rather than asking for them, and never echo a key:

```bash
bash -c 'set -a; source backend/.env; set +a
  gh secret   set GEMINI_API_KEY --body "$GEMINI_API_KEY"
  gh variable set LLM_PROVIDER   --body gemini'
```

Then deploy — these are stack parameters, so they only take effect through a deploy (see
`recall-deploy`).

## State of each provider

### `gemini` — current, working end to end

`google-genai` is in `requirements-lambda.txt`; parameters `GeminiApiKey`, `GeminiModel`,
`GeminiEmbeddingModel` exist. Defaults `gemini-flash-latest` and `gemini-embedding-001`. Nothing to
add.

### `bedrock` — wired, but needs the account prepared

Parameters and the `bedrock:InvokeModel` policy are still in the template, and `boto3` is still in
the Lambda requirements, so switching back is two variables. Two account-level catches:

- Model access for the chosen models has to be enabled in the Bedrock console for the region.
- `BEDROCK_MODEL_ID` needs an inference-profile prefix matching `AWS_REGION` (`us.`, `eu.`, `au.`,
  `jp.`, `global.`); the bare ID fails. Embedding model IDs are the bare ID. Table in `.env.example`.

### `anthropic` — registry only

`get_llm()` handles it, but `backend/template.yaml` has **no** `AnthropicApiKey` / `AnthropicModel`
parameters and `anthropic` is **not** in `requirements-lambda.txt`. Both have to be added, mirroring
the Gemini ones, before it can be deployed. It has no embedder — pair it with `EMBEDDING_PROVIDER`
set to something else.

## Changing the embedder is a migration, not a switch

`backend/schema.sql` declares `VECTOR(1024)` and `settings.embedding_dims` matches it. Vectors from
different models are not comparable even at equal dimensions, so flipping `EMBEDDING_PROVIDER`
leaves every stored row's `embedding` meaningless: recall keeps returning rows, just wrong ones —
silent, not an error.

Switching the embedder means re-embedding `incidents`, and if the new model does not emit 1024 dims,
migrating the column too. Gemini's `gemini-embedding-001` is configured with
`output_dimensionality=1024` precisely to avoid that.

Changing only `LLM_PROVIDER` is safe: it does not touch stored vectors.
