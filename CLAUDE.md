# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos

Todo se corre desde `backend/` con el venv local (`.venv/bin/...`):

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.db              # crea/actualiza el schema en Cockroach
.venv/bin/python -m seed.seed_memory    # carga incidentes + tickets de ejemplo (idempotente por external_id)
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/docs

.venv/bin/pytest                        # suite completa (no necesita DB ni AWS)
.venv/bin/pytest tests/test_ranking.py::test_x   # un solo test
.venv/bin/ruff check .
```

Frontend desde `frontend/`:

```bash
npm install
npm run dev     # http://localhost:5173, proxy /api → :8000
npm run build   # tsc --noEmit && vite build — es el gate de type-check
```

Los tests son unitarios puros: mockean `db` y los providers, y `tests/conftest.py`
setea un `DATABASE_URL` dummy. No levantan Cockroach ni llaman a Bedrock.

## Arquitectura

Backend FastAPI (Python 3.11+) de un copiloto de guardia: recibe tickets de
incidente, los diagnostica con un agente LLM apoyado en memoria semántica de
incidentes pasados, y cierra el ciclo escribiendo el postmortem de vuelta en esa
memoria. El frontend (`frontend/`, React + Vite + TS, :5173) tiene tres vistas —
cola de tickets, vista de incidente y explorador de memoria — sin router ni
state manager: todo con `useState` y `fetch`, proxy `/api` → `:8000`.

Flujo central: `POST /tickets/{id}/handle` → `agent/loop.handle()` → el LLM llama
`search_memory` / `query_incidents` → termina con `submit_diagnosis`. Luego un
humano hace `POST /incidents/{id}/resolve`, que vuelve a embeber el incidente
resuelto en `incidents` (`postmortem.write_postmortem`).

Variante streaming: `GET /tickets/{id}/handle/stream` (SSE, es GET porque el
`EventSource` del browser solo soporta GET). El nucleo del loop es el generador
`loop.handle_events()`, que emite `("evidence", EvidenceStep)` por cada tool
ejecutada y un `("result", HandleResponse)` final; `handle()` es un wrapper que
lo consume. El frontend (`IncidentView`) consume el stream y pinta el timeline
de evidencia en vivo. Al tocar el loop, mantener el contrato de eventos: ambos
endpoints comparten el mismo generador.

Capas y sus límites:

- `app/api/*` — routers finos, sin lógica; validación vía `app/models.py` (Pydantic).
- `app/memory.py` — **única** capa que habla con la tabla `incidents`: recall
  vectorial, ranking, citas, feedback, supersede.
- `app/tickets.py` — `TicketSource` es un `Protocol`; hoy la única implementación
  es `MockTicketSource` (DB + generador sintético). Al integrar Jira/PagerDuty se
  agrega otra implementación, no se toca el resto.
- `app/agent/` — `tools.py` declara los `ToolSpec` y los ejecuta; `loop.py` corre
  el bucle de turnos. El loop es agnóstico del proveedor: habla en los dataclasses
  de `providers/base.py` (`Message`, `ToolUse`, `ToolResult`, `Turn`).
- `app/providers/` — `registry.py` resuelve `LLM_PROVIDER` / `EMBEDDING_PROVIDER`
  a una implementación (import perezoso, `lru_cache`). Bedrock es el default.
- `app/db.py` — pool psycopg + helpers `fetch` / `execute` / `render`.
- `app/mcp/cockroach_client.py` — cliente del Managed MCP Server de Cockroach.

### Doble ruta de lectura (MCP con fallback)

`memory._read()` intenta primero el MCP (renderizando el SQL con `db.render`) y si
no está configurado o falla, cae a psycopg. Cada lectura devuelve `(rows, via)` con
`via` ∈ `"mcp" | "fallback"`, y ese valor viaja hasta el `EvidenceStep` de la
respuesta. Las **escrituras** siempre van por psycopg. Al tocar `memory.py`, mantener
el SQL parametrizado con `%s` — `render()` depende de eso.

### Ranking y vigencia

`rank_score = distance - w_quality*quality_score + w_age*age_penalty` (menor es
mejor). El `ORDER BY embedding <=> %s::VECTOR(n)` debe quedar textualmente así para
que el índice vectorial de Cockroach lo acelere; el re-ranking se hace en Python
sobre `recall_candidates` y se corta en `recall_top_k`.

Un incidente está vigente si `valid_until` es nulo o futuro y `superseded_by` es
nulo. Esa condición vive duplicada a propósito en dos lugares —
`CURRENT_SQL_FILTER` (SQL) e `is_current()` (Python, para lo que vuelve del MCP);
si cambia una, cambia la otra. `tests/test_recall_sql.py` y `test_recall_filters.py`
son el gate.

### Contrato del agente

`Diagnosis` se valida con Pydantic contra lo que devuelve `submit_diagnosis`; si no
valida, el error se le devuelve al modelo como `tool_result` con `is_error` y sigue
el bucle. Si `submit_diagnosis` llega en el mismo turno que otras tools, se descarta
(el modelo no vio los resultados aún). Agotados los `agent_max_turns` se devuelve
`NO_DIAGNOSIS` con `confidence=0.0`. La regla de producto: sin antecedentes en
memoria, hay que decirlo, no inventar causa raíz.

## Convenciones del repo

- Los prompts, mensajes de log y nombres de test están en español, sin tildes en el
  código. Seguir ese estilo.
- Las dimensiones del embedding (`embedding_dims=1024`) tienen que coincidir con el
  `VECTOR(1024)` de `schema.sql`: cambiar de modelo de embeddings implica migrar la
  tabla.
- `BEDROCK_MODEL_ID` requiere prefijo de inference profile acorde a `AWS_REGION`
  (`us.`, `eu.`, `au.`, `jp.`, `global.`); el ID desnudo falla. Los modelos de
  embedding, en cambio, van con ID desnudo. Detalle en `.env.example` y §7 de la doc.
- `frontend/src/types.ts` espeja los modelos Pydantic de `app/models.py`: si
  cambia un modelo que viaja por la API, actualizar ambos lados.
- `docs/recall-DOCUMENTATION.md` es la referencia larga (modelo de datos,
  API, variables de entorno, roadmap).
