from datetime import datetime, timezone

from app.config import settings
from app.db import execute, fetch, fetch_one, render, to_vector_literal
from app.mcp import cockroach_client
from app.providers.registry import get_embedder

DISTANCE_OP = "<=>"

RECALL_COLUMNS = """
    id::STRING AS id, title, symptom, root_cause, resolution, service, severity,
    created_at, quality_score, times_cited, times_helpful
"""

MEMORY_COLUMNS = (
    RECALL_COLUMNS
    + ", resolved_at, valid_until, superseded_by::STRING AS superseded_by, source"
)

FEEDBACK_COLUMNS = "id::STRING AS incident_id, quality_score, times_helpful"


def age_penalty(created_at: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    return min(age_days / 365.0, 1.0)


def rank_score(distance: float, quality_score: float, created_at: datetime) -> float:
    return (
        distance
        - settings.w_quality * quality_score
        + settings.w_age * age_penalty(created_at)
    )


def _recall_sql(embedding: list[float], service: str | None) -> tuple[str, list]:
    vector = to_vector_literal(embedding)
    multiplier = settings.recall_service_multiplier if service else 1
    limit = settings.recall_candidates * multiplier
    sql = f"""
        SELECT {MEMORY_COLUMNS},
               embedding {DISTANCE_OP} %s::VECTOR AS distance
        FROM incidents
        ORDER BY embedding {DISTANCE_OP} %s::VECTOR
        LIMIT %s
    """
    return sql, [vector, vector, limit]


def _read(sql: str, params: list) -> tuple[list[dict], str]:
    if cockroach_client.is_configured():
        rows = cockroach_client.run_sql(render(sql, params))
        if rows is not None:
            return rows, "mcp"
    return fetch(sql, params), "fallback"


def _as_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value))


CURRENT_SQL_FILTER = (
    "(valid_until IS NULL OR valid_until > now()) AND superseded_by IS NULL"
)


def is_current(row: dict, now: datetime) -> bool:
    if row.get("distance") is None or row.get("superseded_by"):
        return False
    valid_until = row.get("valid_until")
    return valid_until is None or _as_datetime(valid_until) > now


def recall(symptom: str, service: str | None = None) -> tuple[list[dict], str]:
    embedding = get_embedder().embed(symptom)
    rows, via = _read(*_recall_sql(embedding, service))
    now = datetime.now(timezone.utc)

    hits = []
    for row in rows:
        if not is_current(row, now):
            continue
        if service and row.get("service") != service:
            continue
        row["created_at"] = _as_datetime(row["created_at"])
        row["distance"] = float(row["distance"])
        row["quality_score"] = float(row["quality_score"] or 0.0)
        row["score"] = rank_score(row["distance"], row["quality_score"], row["created_at"])
        hits.append(row)

    top = sorted(hits, key=lambda r: r["score"])[: settings.recall_top_k]
    if top:
        _cite([row["id"] for row in top])
    return top, via


def _cite(incident_ids: list[str]) -> None:
    execute(
        "UPDATE incidents SET times_cited = times_cited + 1 WHERE id = ANY(%s::UUID[])",
        (incident_ids,),
    )


def query_incidents(
    service: str | None = None, severity: str | None = None, limit: int = 10
) -> tuple[list[dict], str]:
    conditions = ["1 = 1"]
    params: list = []
    if service:
        conditions.append("service = %s")
        params.append(service)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    params.append(min(limit, 50))
    sql = f"""
        SELECT {RECALL_COLUMNS}
        FROM incidents
        WHERE {" AND ".join(conditions)}
          AND {CURRENT_SQL_FILTER}
        ORDER BY created_at DESC
        LIMIT %s
    """
    return _read(sql, params)


def store_incident(
    title: str,
    symptom: str,
    root_cause: str | None = None,
    resolution: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    source: str = "manual",
    external_id: str | None = None,
    created_at: datetime | None = None,
    valid_until: datetime | None = None,
) -> str:
    embedding = get_embedder().embed(f"{title} {symptom}")
    row = fetch_one(
        """
        INSERT INTO incidents (
            title, symptom, root_cause, resolution, service, severity,
            source, external_id, embedding, resolved_at,
            created_at, valid_until
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s::VECTOR, %s,
            COALESCE(%s::TIMESTAMPTZ, now()), %s::TIMESTAMPTZ
        )
        RETURNING id::STRING AS id
        """,
        (
            title,
            symptom,
            root_cause,
            resolution,
            service,
            severity,
            source,
            external_id,
            to_vector_literal(embedding),
            datetime.now(timezone.utc) if resolution else None,
            created_at,
            valid_until,
        ),
    )
    return row["id"]


def apply_feedback(incident_id: str, helpful: bool) -> dict | None:
    delta = settings.feedback_up if helpful else -settings.feedback_down
    return fetch_one(
        f"""
        UPDATE incidents
        SET quality_score = GREATEST(-1.0, LEAST(1.0, quality_score + %s)),
            times_helpful = times_helpful + %s
        WHERE id = %s::UUID
        RETURNING {FEEDBACK_COLUMNS}
        """,
        (delta, 1 if helpful else 0, incident_id),
    )


def supersede(old_id: str, new_id: str) -> None:
    execute(
        """
        UPDATE incidents
        SET superseded_by = %s::UUID, valid_until = now()
        WHERE id = %s::UUID
        """,
        (new_id, old_id),
    )


def list_memory(service: str | None = None, limit: int = 100) -> list[dict]:
    params: list = []
    service_filter = ""
    if service:
        service_filter = "WHERE service = %s"
        params.append(service)
    params.append(limit)
    return fetch(
        f"""
        SELECT {MEMORY_COLUMNS}
        FROM incidents
        {service_filter}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        params,
    )
