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

-- covers the queue when it filters by an explicit status. The default queue
-- filters status != 'resolved', which this B-tree cannot serve, and the title
-- search is an ILIKE '%...%': both stay scans until the queue is big enough
-- to need trigram, full-text or a partial index.
CREATE INDEX IF NOT EXISTS tickets_status_idx ON tickets (status, created_at);

ALTER TABLE tickets ADD CONSTRAINT IF NOT EXISTS tickets_status_check
    CHECK (status IN ('open', 'handling', 'resolved'));
ALTER TABLE tickets ADD CONSTRAINT IF NOT EXISTS tickets_severity_check
    CHECK (severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low'));

CREATE TABLE IF NOT EXISTS diagnoses (
    ticket_id  UUID PRIMARY KEY REFERENCES tickets (id) ON DELETE CASCADE,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
