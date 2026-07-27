CREATE TABLE IF NOT EXISTS incidents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         STRING NOT NULL,
    symptom       STRING NOT NULL,
    root_cause    STRING,
    resolution    STRING,
    service       STRING,
    severity      STRING,
    created_at    TIMESTAMPTZ DEFAULT now(),
    resolved_at   TIMESTAMPTZ,
    valid_until   TIMESTAMPTZ,
    superseded_by UUID,
    quality_score FLOAT DEFAULT 0.0,
    times_cited   INT DEFAULT 0,
    times_helpful INT DEFAULT 0,
    external_id   STRING UNIQUE,
    source        STRING DEFAULT 'manual',
    embedding     VECTOR(1024)
);

CREATE VECTOR INDEX IF NOT EXISTS incidents_embedding_idx
    ON incidents (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS incidents_service_idx ON incidents (service, created_at);

CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id STRING UNIQUE,
    title STRING NOT NULL,
    description STRING,
    service STRING,
    severity STRING,
    status STRING DEFAULT 'open',
    source STRING DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- covers the queue filter by status plus the created_at ordering. The title
-- search is an ILIKE '%...%': a leading wildcard cannot use a B-tree, so it
-- stays a scan until the queue is big enough to need trigram or full-text.
CREATE INDEX IF NOT EXISTS tickets_status_idx ON tickets (status, created_at);

CREATE TABLE IF NOT EXISTS diagnoses (
    ticket_id  UUID PRIMARY KEY REFERENCES tickets (id) ON DELETE CASCADE,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
