# Recall

Copiloto de guardia con memoria semántica de incidentes, construido para el
hackathón **CockroachDB × AWS — Build with Agentic Memory**.

Recibe tickets de incidente, los diagnostica con un agente LLM que consulta una
memoria vectorial de incidentes pasados (CockroachDB + `VECTOR`), y cierra el
ciclo escribiendo el postmortem de vuelta en esa memoria: cada incidente
resuelto mejora el diagnóstico del siguiente.

## Arquitectura

```
frontend (React + Vite, :5173)
        │  /api → proxy → :8000
backend FastAPI (:8000)
        │  agent loop (Claude via Bedrock) ── search_memory / query_incidents
        ▼
CockroachDB (tabla incidents con VECTOR(1024) + índice vectorial)
```

- **Backend** (`backend/`): FastAPI + agente LLM. El loop del agente es agnóstico
  del proveedor (Bedrock por default, Anthropic API como alternativa). Lecturas
  con doble ruta: Managed MCP Server de Cockroach con fallback a psycopg.
- **Frontend** (`frontend/`): React + Vite + TypeScript, sin dependencias extra.
  Tres vistas: cola de tickets (alta manual o generación random, con edición y
  borrado), vista de incidente (diagnóstico con timeline de evidencia **en vivo
  por SSE**) y explorador de memoria (edición, borrado y supersede).
- Referencia completa (modelo de datos, API, decisiones de diseño):
  [`docs/recall-DOCUMENTATION.md`](docs/recall-DOCUMENTATION.md).

## Requisitos

- Python 3.11+
- Node 18+
- Un cluster de CockroachDB (Cloud serverless alcanza) con soporte `VECTOR`
- Acceso a Bedrock, por credenciales AWS (SigV4) o por API key en
  `BEDROCK_API_KEY`. **Los embeddings de Titan son obligatorios**: `ANTHROPIC_API_KEY`
  solo reemplaza el LLM, no la generación de embeddings, así que sin Bedrock no se
  puede sembrar ni escribir en memoria

## Puesta en marcha

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # completar DATABASE_URL, Cockroach MCP y acceso a Bedrock

.venv/bin/python -m app.db              # crea/actualiza el schema
.venv/bin/python -m seed.seed_memory    # incidentes + tickets de ejemplo (idempotente)
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173 (proxy /api → :8000)
```

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET  | `/health` | Health check (incluye estado del MCP) |
| GET  | `/tickets` | Cola de tickets abiertos |
| POST | `/tickets` | Ingesta manual de un ticket |
| POST | `/tickets/generate?n=1` | Genera `n` tickets sintéticos |
| DELETE | `/tickets` | Vacía la cola (solo los `status != 'resolved'`) |
| GET  | `/tickets/{id}` | Detalle de un ticket |
| PATCH | `/tickets/{id}` | Edita título, síntoma, área o severidad |
| DELETE | `/tickets/{id}` | Elimina un ticket |
| POST | `/tickets/{id}/handle` | Corre el loop agéntico → diagnóstico + evidencia |
| GET  | `/tickets/{id}/handle/stream` | Igual que `handle`, por SSE: eventos `evidence`, `result`, `agent_error` |
| POST | `/incidents/{ticket_id}/resolve` | Escribe el postmortem (la memoria crece) |
| POST | `/incidents/{ticket_id}/feedback` | 👍/👎 ajusta la calidad del incidente citado |
| GET  | `/memory?service=...` | Inspección de la memoria |
| PATCH | `/memory/{id}` | Edita un incidente (re-embebe si cambia título o síntoma) |
| DELETE | `/memory/{id}` | Elimina un incidente |
| DELETE | `/memory` | Borra toda la memoria |
| POST | `/memory/{id}/supersede` | Marca un incidente como reemplazado por otro |

## Flujo de demo

El dataset de ejemplo es una casa de service técnico de computación y celulares:
las áreas son `hardware-pc`, `software-pc`, `hardware-celular` y `software-celular`
(§9 de la doc). El dominio vive entero en `TEMPLATES` y en los seeds; el resto del
sistema es agnóstico.

1. **Memoria** — arranca con los incidentes sembrados.
2. **Generar random** (o **Nuevo ticket** para cargarlo a mano) — aparece en la cola.
3. **Diagnosticar** — el timeline muestra en vivo qué herramientas usa el agente
   y qué recupera; al final, causa raíz + mitigación + confianza.
4. **Resolver** — el postmortem se embebe en la memoria.
5. **Feedback 👍** — sube el `quality_score` del incidente citado.
6. Un segundo ticket parecido ahora rankea mejor: ese delta es la demo.

Regla de producto: si la memoria no tiene antecedentes, el agente lo dice con
confianza baja en lugar de inventar una causa raíz. `software-celular` no tiene
incidentes sembrados justamente para poder mostrar ese caso.

## Tests

```bash
cd backend
.venv/bin/pytest        # unitarios puros: no necesitan DB ni AWS
.venv/bin/ruff check .

cd ../frontend
npm run build           # type-check (tsc --noEmit) + build
```
