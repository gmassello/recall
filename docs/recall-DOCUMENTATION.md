# Recall

Agente de respuesta a incidentes con **memoria agéntica completa**: recibe tickets,
recuerda incidentes pasados semánticamente parecidos, diagnostica ponderando
recencia y calidad, y **aprende** de cada resolución. Aplicación full-stack,
**agnóstica del proveedor de IA**.

Entrega para el hackathón **CockroachDB × AWS — Build with Agentic Memory**.

> **Estado: implementado.** Backend (`backend/`) y frontend (`frontend/`) están
> construidos según este spec. Las secciones 4–7 describen lo que hoy corre.

---

## 1. Resumen

Cuando entra un ticket de incidente, el agente:

1. **Decide qué consultar** (memoria semántica + estructurada) usando herramientas.
2. **Recuerda** incidentes pasados parecidos con búsqueda vectorial + ranking temporal.
3. **Diagnostica**: causa raíz probable + pasos de mitigación + el incidente más relevante.
4. Al **resolver**, escribe el postmortem → la memoria crece.
5. El **feedback** del ingeniero re-pesa esa memoria para la próxima vez.

Ese ciclo cerrado (leer → razonar → escribir → aprender) es lo que hace la memoria
"agéntica" y no un simple vector search.

---

## 2. Stack y decisiones de arquitectura

| Capa | Elección | Nota |
|------|----------|------|
| Memoria | **CockroachDB** | Distributed Vector Indexing + Managed MCP Server |
| IA | Capa **agnóstica** (`LLMProvider`) | Default: **Claude vía Amazon Bedrock** |
| Embeddings | Amazon Titan v2 (Bedrock) | 1024 dims (coincide con `VECTOR(1024)`) |
| Backend | **FastAPI** (REST) | Docs automáticas en `/docs` |
| Frontend | **React + Vite + TypeScript** | 3 vistas |

Principios que no se rompen:

- **IA agnóstica del proveedor**: todo pasa por `providers/base.py`
  (`LLMProvider` / `EmbeddingProvider`). Se cambia de modelo con una env var
  (`LLM_PROVIDER` / `EMBEDDING_PROVIDER`). El agent loop nunca conoce el proveedor
  concreto. Default = Bedrock (cumple AWS + usa modelo de Anthropic).
- **MCP en runtime (opción b)**: las lecturas que el agente decide hacer con
  herramientas (`search_memory`, `query_incidents`) van por el Managed MCP Server de
  CockroachDB — mismo protocolo que en dev con Claude Code. Todo lo demás va por
  conexión directa `psycopg`: las escrituras (postmortem, feedback, supersede) y las
  lecturas de servicio que no pasan por el agente (`GET /tickets`, `GET /memory`).
  Si el MCP no responde, las tools caen a `psycopg` con el mismo SQL y el rastro de
  evidencia marca `via: "fallback"` — la demo no se cae por una dependencia de red.
- **Memoria temporal**: se recuperan los `k` vecinos más cercanos por vector y se
  re-rankean con

  ```
  score = distancia_coseno − W_QUALITY·quality_score + W_AGE·(edad_días / 365)
  W_QUALITY = 0.15    W_AGE = 0.10    k = 20 → top 5
  ```

  Menor score = mejor. `edad_días` es `now() − created_at`; se normaliza a años y se
  satura en 1.0, de modo que la penalización por antigüedad nunca domina a la
  similitud semántica. Se filtra el conocimiento obsoleto
  (`valid_until IS NULL OR valid_until > now()`) y las contradicciones encadenan
  `superseded_by`.
- **Feedback → calidad**: 👍 suma `+0.1` a `quality_score`, 👎 resta `0.15`, acotado a
  `[-1.0, 1.0]`. `times_cited` se incrementa cada vez que un incidente entra en el top 5
  de un diagnóstico y `times_helpful` con cada 👍. Ninguno de los dos entra en el score:
  existen para explicar en la UI *por qué* una memoria pesa lo que pesa, y para poder
  auditar si el ranking está funcionando.
- **Ticket source swappable**: interfaz `TicketSource`; el mock persiste en
  CockroachDB y un `PagerDutyTicketSource` real entra sin tocar el resto. El mock
  alimenta la cola de tres formas, todas detrás de la misma interfaz: **fixture**
  (`tickets_seed.json`), **generado** (plantillas + `random`, §9) e **importado**
  (histórico del cliente, §10).

---

## 3. Diagrama

```
Ticket Source (mock swappable)
        │ ingest
        ▼
FastAPI (REST)   /tickets · /handle · /resolve · /feedback · /memory
        │ handle()
        ▼
AGENT LOOP (agnóstico del modelo)
        │ elige herramientas: search_memory (vector) · query_incidents (SQL)
        ▼
MCP CLIENT (runtime)
        │
        ▼
CockroachDB Managed MCP Server  (read-only)
        │
        ▼
CockroachDB
        incidents          memoria LP: temporal + quality + VECTOR(1024)
        tickets
        ▲
        │ escrituras (postmortem · feedback · supersede) por psycopg directo
        │ + fallback de lectura si el MCP no responde
     FastAPI

IA: LLMProvider + EmbeddingProvider → default Bedrock (Claude + Titan)
```

---

## 4. Modelo de datos (CockroachDB)

Requiere **CockroachDB v25.3+**: el índice se declara con el opclass `vector_cosine_ops`
para que acelere el operador `<=>` que usa el recall, y ese opclass no existe antes de
v25.3 (en v25.2 solo se acelera la distancia L2 `<->`).

Dos limitaciones del índice vectorial que condicionan cómo se escribe la query de recall:

- El opclass tiene que coincidir con el operador de la query. El default es
  `vector_l2_ops`, que solo acelera `<->`.
- *"Index acceleration with filters is only supported if the filters match prefix
  columns."* Por eso el recall tiene dos caminos:
  - **Sin `service`** (el caso común): la query no lleva `WHERE` y el índice acelera.
    Los filtros de vigencia (`valid_until`, `superseded_by`) se aplican en Python sobre
    los candidatos recuperados; meterlos en el `WHERE` desactivaría el índice.
  - **Con `service`**: el servicio no es columna prefijo del índice vectorial, así que
    la aceleración no aplica de todos modos. La query filtra en SQL
    (`WHERE service = %s AND <vigencia>`) y ordena por distancia exacta, acotada por
    `incidents_service_idx`. Se cambia aceleración por exactitud a propósito: filtrar
    en Python sobre un top-N global puede omitir incidentes del servicio que rankeen
    por debajo del corte, aunque sean los únicos que existen.

  El techo del camino con `service` es que calcula distancia sobre todas las filas de ese
  servicio. A la escala del proyecto es irrelevante; si un servicio concentrara mucho
  volumen habría que volver a un esquema aproximado.

```sql
-- severity : 'sev1' | 'sev2' | 'sev3' | 'sev4'
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
    valid_until   TIMESTAMPTZ,               -- NULL = conocimiento vigente
    superseded_by UUID,                      -- cadena temporal (estilo Zep)
    quality_score FLOAT DEFAULT 0.0,         -- ajustado por feedback
    times_cited   INT DEFAULT 0,
    times_helpful INT DEFAULT 0,
    external_id   STRING UNIQUE,               -- ref del sistema origen; import idempotente
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
```

---

## 5. API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET  | `/health` | Health check |
| GET  | `/tickets` | Cola de tickets abiertos |
| POST | `/tickets` | Ingesta (mock manual o webhook de alertas) |
| POST | `/tickets/generate?n=1` | Genera `n` tickets sintéticos y los encola (§9) |
| GET  | `/tickets/{id}` | Detalle de un ticket |
| POST | `/tickets/{id}/handle` | Corre el loop agéntico → diagnóstico + evidencia |
| GET  | `/tickets/{id}/handle/stream` | Igual que `handle` pero por SSE: eventos `evidence` (uno por herramienta), `result` (respuesta completa) y `error` |
| POST | `/incidents/{ticket_id}/resolve` | Escribe el postmortem (memoria crece) |
| POST | `/incidents/{ticket_id}/feedback` | 👍/👎 ajusta la calidad de la memoria |
| GET  | `/memory?service=...` | Inspección de la memoria |

La respuesta de `handle` incluye el **rastro de evidencia** (qué herramientas usó el
agente y qué recuperó), que alimenta el timeline en vivo del frontend.

### Bodies de los endpoints no triviales

`POST /tickets/{id}/handle` — sin body.

```jsonc
// 200
{
  "ticket_id": "…",
  "diagnosis": {
    "root_cause": "Connection pool exhaustion en payments-api",
    "mitigation_steps": ["Subir max_connections a 200", "…"],
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

`POST /incidents/{ticket_id}/resolve` — escribe el postmortem y embebe el síntoma.

```jsonc
// request
{ "root_cause": "…", "resolution": "…", "supersedes": "uuid | null" }
// 201
{ "incident_id": "…", "embedded": true, "superseded": "uuid | null" }
```

`POST /incidents/{ticket_id}/feedback`

```jsonc
// request  — helpful=false resta más de lo que suma true (ver sección 2)
{ "incident_id": "…", "helpful": true }
// 200
{ "incident_id": "…", "quality_score": 0.40, "times_helpful": 3 }
```

`POST /tickets/generate?n=1` — sin body.

```jsonc
// 201
{ "generated": [ { "id": "…", "title": "…", "symptom": "…",
                   "service": "payments-api", "severity": "sev2",
                   "source": "generated" } ] }
```

---

## 6. Estructura del repo

```
backend/
  app/
    main.py                  # FastAPI app
    config.py                # env vars
    db.py                    # conexión directa (escrituras) + init schema
    models.py                # pydantic: Ticket, Incident, Diagnosis, ...
    providers/
      base.py                # LLMProvider, EmbeddingProvider, ToolSpec (canónico)
      bedrock.py             # BedrockClaudeProvider + BedrockTitanEmbedder (default)
      anthropic_provider.py  # demuestra el swap de modelo
      registry.py            # factory desde env
    mcp/
      cockroach_client.py    # cliente MCP en runtime (service-account key)
    tickets.py               # TicketSource + MockTicketSource + TicketGenerator
    memory.py                # recall temporal, store, feedback, supersede
    postmortem.py            # write_postmortem()
    agent/
      tools.py               # ToolSpecs + handlers (resuelven vía MCP)
      loop.py                # loop de tool-use, agnóstico de proveedor
    api/
      tickets.py  incidents.py  memory.py
  seed/
    tickets_seed.json      # fixture de tickets
    seed_memory.py         # memoria de ejemplo
    import_history.py      # bootstrap desde histórico del cliente
    evaluate.py            # evaluación previa (holdout + recall@k)
    history.sample.jsonl   # formato esperado del histórico
  schema.sql   requirements.txt   .env.example
frontend/
  package.json  vite.config.ts  tsconfig.json  index.html
  src/  main.tsx  App.tsx  api.ts  types.ts  styles.css
        components/  TicketQueue.tsx  IncidentView.tsx  MemoryExplorer.tsx
```

---

## 7. Puesta en marcha

### Requisitos previos
- **CockroachDB Cloud** (plan Basic, gratis): connection string + API key de service account (para el MCP).
- **AWS con Bedrock**: acceso habilitado a Claude y Titan Text Embeddings V2.
- **Python 3.11+** y **Node 18+**.

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # DATABASE_URL, AWS, COCKROACH_MCP_API_KEY
python -m app.db              # crea el schema
python -m seed.seed_memory    # memoria + tickets de ejemplo
uvicorn app.main:app --reload # http://localhost:8000/docs
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxea /api → :8000)
```

### Variables de entorno

| Variable | Obligatoria | Default | Qué es |
|----------|-------------|---------|--------|
| `DATABASE_URL` | sí | — | Connection string de CockroachDB (escrituras + fallback) |
| `COCKROACH_MCP_API_KEY` | sí | — | API key del service account para el Managed MCP Server |
| `COCKROACH_MCP_URL` | sí | — | Endpoint del MCP Server (`https://cockroachlabs.cloud/mcp`) |
| `COCKROACH_MCP_CLUSTER_ID` | sí | — | ID del cluster, viaja en el header `mcp-cluster-id` |
| `LLM_PROVIDER` | no | `bedrock` | `bedrock` \| `anthropic` \| `gemini` |
| `EMBEDDING_PROVIDER` | no | `bedrock` | `bedrock` \| `gemini`. Debe producir 1024 dims (`VECTOR(1024)`) |
| `AWS_REGION` | si `bedrock` | `us-east-1` | Región con acceso a Bedrock habilitado |
| `BEDROCK_API_KEY` | no | — | API key de Bedrock (`ABSK…`), alternativa a SigV4. Se propaga a `AWS_BEARER_TOKEN_BEDROCK` |
| `BEDROCK_MODEL_ID` | no | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Modelo vía Converse API. **Inference profile, no el ID desnudo** (ver abajo) |
| `BEDROCK_EMBEDDING_MODEL_ID` | no | `amazon.titan-embed-text-v2:0` | Titan v2, 1024 dims. ID desnudo: los modelos de embedding no usan inference profiles |
| `ANTHROPIC_API_KEY` | si `anthropic` | — | Solo para el swap de proveedor |
| `GEMINI_API_KEY` | si `gemini` | — | Alternativa **gratis** a Bedrock (free tier): una key hace LLM y embeddings |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Modelo de chat con function calling |
| `GEMINI_EMBEDDING_MODEL` | no | `gemini-embedding-001` | `output_dimensionality=1024` → sin migrar la tabla |
| `MOCK_SEED` | no | — | Semilla del generador de tickets → demo reproducible (§9) |

Credenciales AWS por la cadena estándar de boto3 (perfil, env vars o rol).

Bedrock acepta además **API keys** en lugar de SigV4: boto3 las lee de la variable de
entorno `AWS_BEARER_TOKEN_BEDROCK` y solo de ahí. Ponerla en `BEDROCK_API_KEY` del
`.env` alcanza — `providers/bedrock._client()` la propaga a esa variable antes de
construir el cliente. Si `AWS_BEARER_TOKEN_BEDROCK` ya viene del entorno, gana esa.

Ojo con el diagnóstico: sin la key, boto3 firma con SigV4 y un rol sin permisos
devuelve `AccessDeniedException: not authorized to perform bedrock:InvokeModel`. Con
una key de formato inválido el error es distinto —`Invalid API Key format`— y ese
cambio de mensaje es lo que distingue "falta la key" de "la key no sirve".

**El prefijo del model ID tiene que acompañar a `AWS_REGION`.** Claude Sonnet 4.5 no
admite invocación on-demand con el ID desnudo (`In-Region ❌` en todas las regiones): hay
que usar un inference profile.

| Región | Prefijo |
|--------|---------|
| `us-*`, `ca-central-1` | `us.` |
| `eu-*` | `eu.` |
| `ap-southeast-2/4/6` | `au.` |
| `ap-northeast-1/3` | `jp.` |
| cualquier región comercial | `global.` |

Regiones sin perfil geo (`ap-south-1`, `ap-southeast-1`, `sa-east-1`, `me-*`) solo pueden
usar `global.`. La política IAM debe permitir `bedrock:InvokeModel` **sobre el inference
profile**, no sobre el foundation model.

### Cambiar de modelo de IA (agnóstico)
```
# backend/.env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```
El resto del código no cambia. Para el hackathón, dejar `bedrock` para cumplir AWS.

Alternativa **gratis** de punta a punta (LLM + embeddings) sin cuenta AWS:
```
# backend/.env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...   # https://aistudio.google.com/apikey
```
El embedder pide `output_dimensionality=1024` y normaliza el vector, así que entra en
`VECTOR(1024)` sin migrar. Se puede mezclar: dejar `LLM_PROVIDER=anthropic` y usar solo
`EMBEDDING_PROVIDER=gemini` para cubrir lo que el gateway corporativo no da (Titan).

---

## 8. Cómo cumple los requisitos del hackathón

- ✅ **CockroachDB #1** — Distributed Vector Indexing (búsqueda semántica de memoria).
- ✅ **CockroachDB #2** — Managed MCP Server en **runtime** (opción b) + en dev con Claude Code.
- ✅ **AWS** — Amazon Bedrock (Claude Converse + Titan) como proveedor default; Lambda/ECS/S3 opcional en deploy.
- ✅ **Modelo de Anthropic** — Claude vía Bedrock, con capa agnóstica que permite swap.
- ✅ Repo open-source (MIT) + demo + video < 3 min.

---

## 9. Generador de tickets

El mock no solo sirve un fixture: genera incidentes sintéticos a demanda, vía
`POST /tickets/generate` o el botón **Generar random** de `TicketQueue`.

El dominio es una casa de service técnico de computación y celulares, y el campo
`service` es el **área**: `hardware-pc`, `software-pc`, `hardware-celular`,
`software-celular`.

Las plantillas son una lista de `(area, plantilla_de_síntoma, severidad)` en
`tickets.py`, con placeholders numéricos (`pct`, `n`, `gb`) que se rellenan con
`random`:

```python
TEMPLATES = [
    ("hardware-pc",      "la notebook no enciende y no prende el led de carga", "sev1"),
    ("software-pc",      "Windows entra en bucle de reinicio tras el update",   "sev2"),
    ("hardware-celular", "el tactil no responde en el {pct}% de la pantalla",   "sev2"),
    ("software-celular", "queda en el logo al arrancar desde hace {n} dias",    "sev2"),
]
```

Sin `faker` ni generación por LLM: pedirle texto a un modelo cuesta latencia y dinero
para producir lo que una plantilla resuelve igual.

Dos requisitos de las plantillas, que son lo que hace útil al generador:

- **Cubrir las mismas áreas y familias de síntoma que `seed_memory.py`**, con la
  redacción variada. Si el ticket generado no se parece semánticamente a nada en
  memoria, el recall vuelve vacío y la demo se ve peor de lo que el sistema es.
- **Incluir un área sin memoria previa** (hoy `software-celular`), para poder mostrar
  el caso honesto: el agente no encuentra nada y lo dice, en vez de inventar un
  diagnóstico.

Los dos requisitos son el gate de `tests/test_generador_dominio.py`, que además valida
que cada plantilla produzca un `TicketCreate` válido.

`MOCK_SEED` (env var, opcional) fija la semilla de `random` → corridas reproducibles
para grabar el video sin sorpresas.

---

## 10. Ingesta de histórico

Antes de poner el agente en producción con un cliente, su histórico de incidentes
cumple dos funciones: **arrancar con memoria real** en vez de vacía, y **medir si el
agente acierta** antes de confiar en él.

Formato de entrada, `history.jsonl` (una línea por incidente):

```jsonc
{ "external_id": "INC-1042", "title": "…", "symptom": "…",
  "root_cause": "…", "resolution": "…",       // si faltan → se omite
  "service": "payments-api", "severity": "sev2",
  "created_at": "2025-03-11T04:12:00Z", "resolved_at": "2025-03-11T05:40:00Z" }
```

### Bootstrap de memoria

```bash
python -m seed.import_history history.jsonl [--dry-run] [--limit N]
```

1. Valida y mapea cada fila. **Solo entran los incidentes resueltos**: sin
   `root_cause`/`resolution` no hay conocimiento que recordar, se cuentan como omitidos.
2. Salta los `external_id` ya presentes → reimportar es idempotente.
3. Embebe `title + symptom` y escribe en `incidents` con `source='imported'`,
   **respetando el `created_at` original**. El ranking temporal depende de esa fecha;
   usar `now()` haría ver a todo el histórico como recién ocurrido y anularía la
   penalización por antigüedad.
4. `quality_score` arranca en `0.0` — el histórico no viene pre-validado, la calidad
   la construye el feedback de uso.
5. Reporta importados / omitidos / duplicados.

Los embeddings se calculan secuencialmente, con checkpoint del último `external_id`
procesado para poder reanudar una corrida cortada. Límite conocido: para volúmenes
grandes hay que paralelizar (ver roadmap).

### Evaluación previa

```bash
python -m seed.evaluate history.jsonl --holdout 20
```

1. Aparta `N` incidentes resueltos al azar (semilla fija) e importa **solo el resto**.
   Importar todo primero haría que cada caso encontrara su propia respuesta en memoria:
   el resultado daría casi perfecto y no mediría nada.
2. Corre el loop del agente sobre el `symptom` de cada holdout.
3. Métrica: **recall@5** — cuenta como acierto si algún incidente del top 5 comparte
   `service` y su `root_cause` coincide con el real. Objetiva, sin LLM-judge.
4. Imprime `recall@5`, `recall@1` y la lista de casos fallados para inspección manual.

Esa lista de fallos es el entregable real: dice si el problema es la memoria (el
incidente correcto no estaba), el embedding (estaba pero no lo recuperó) o el ranking
(lo recuperó pero quedó abajo).

---

## 11. Guion de demo (< 3 min)

La secuencia que hay que poder correr end-to-end. El punto es mostrar el ciclo cerrado:
el mismo síntoma diagnosticado dos veces da un resultado mejor la segunda vez, porque
en el medio el sistema aprendió.

1. **Estado inicial** — `MemoryExplorer` con la memoria sembrada (`seed_memory.py`).
   Mostrar que hay incidentes viejos, uno de ellos con `valid_until` vencido.
2. **Entra un ticket** — botón **Generar ticket** (§9). Aparece en la cola un
   incidente sintético, p.ej. *"latencia p99 subió a 4200ms en checkout"*.
   Con `MOCK_SEED` fijo, siempre sale el mismo.
3. **Handle** — el timeline muestra el agente eligiendo `search_memory`, la evidencia
   recuperada y el diagnóstico. Señalar que el incidente obsoleto **no** fue recuperado.
4. **Resolve** — se escribe el postmortem. La memoria crece: el nuevo incidente aparece
   en `MemoryExplorer` con `quality_score = 0.0`.
5. **Feedback 👍** sobre el incidente que sí ayudó → su `quality_score` sube.
6. **Segundo ticket, síntoma parecido** → handle de nuevo. Ahora el top 1 es el
   postmortem recién escrito, y el `score` del que recibió 👍 mejoró. Ese delta
   *es* la demo.

7. **Cierre** — correr `seed.evaluate` sobre un histórico de ejemplo y mostrar el
   `recall@5`. Cierra el argumento: no es una demo con casos elegidos a dedo, el
   sistema se puede medir.

Fijar `MOCK_SEED` para que los pasos 2 y 6 sean reproducibles al grabar.

---

## 12. Roadmap / tareas priorizadas

1. ~~**SSE** en `/tickets/{id}/handle/stream` + consumo en el frontend para ver el razonamiento del agente en vivo.~~ **Hecho**: el frontend consume el stream con `EventSource` y pinta el timeline de evidencia en vivo.
2. **Detección de contradicción** que dispare `supersede()` automáticamente.
3. **OpenAIProvider** siguiendo `providers/base.py` (demuestra la agnosticidad).
4. **Deploy** en AWS (Lambda/ECS + S3) — suma "production readiness".
5. **Paralelizar los embeddings** de `import_history` para históricos grandes.
6. **LLM-judge** en `evaluate` sobre la calidad del `root_cause` redactado, además del
   `recall@k` que ya mide la recuperación.

---

## Licencia
MIT.
