from datetime import datetime, timezone

from app.config import settings
from app.db import execute, fetch, fetch_one, render, to_vector_literal
from app.mcp import cockroach_client
from app.providers.registry import get_embedder

DISTANCE_OP = "<=>"

VECTOR_CAST = f"::VECTOR({settings.embedding_dims})"

RECALL_COLUMNS = """
    id::STRING AS id, title, symptom, root_cause, resolution, service, severity,
    created_at, quality_score, times_cited, times_helpful
"""

MEMORY_COLUMNS = (
    RECALL_COLUMNS
    + ", resolved_at, valid_until, superseded_by::STRING AS superseded_by, source"
)

FEEDBACK_COLUMNS = "id::STRING AS incident_id, quality_score, times_helpful"

CURRENT_SQL_FILTER = (
    "(valid_until IS NULL OR valid_until > now()) AND superseded_by IS NULL"
)

UPDATABLE_COLUMNS = {
    "title", "symptom", "root_cause", "resolution", "service", "severity",
    "quality_score", "times_cited", "times_helpful", "valid_until",
}


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
    distance = f"embedding {DISTANCE_OP} %s{VECTOR_CAST}"
    where = f"WHERE {CURRENT_SQL_FILTER}"
    params: list = [vector]
    if service:
        where = f"WHERE service = %s AND {CURRENT_SQL_FILTER}"
        params.append(service)
    params.append(settings.recall_candidates)
    sql = f"""
        SELECT {MEMORY_COLUMNS}, {distance} AS distance
        FROM incidents
        {where}
        ORDER BY distance
        LIMIT %s
    """
    return sql, params


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


def validity_of(row: dict, now: datetime) -> str:
    if row.get("superseded_by"):
        return "superseded"
    valid_until = row.get("valid_until")
    if valid_until is not None and _as_datetime(valid_until) <= now:
        return "expired"
    return "current"


def is_recallable(row: dict, now: datetime) -> bool:
    return row.get("distance") is not None and validity_of(row, now) == "current"


def recall(symptom: str, service: str | None = None) -> tuple[list[dict], str]:
    embedding = get_embedder().embed(symptom)
    rows, via = _read(*_recall_sql(embedding, service))
    now = datetime.now(timezone.utc)

    hits = []
    for row in rows:
        if not is_recallable(row, now):
            continue
        row["created_at"] = _as_datetime(row["created_at"])
        row["distance"] = float(row["distance"])
        row["quality_score"] = float(row["quality_score"] or 0.0)
        row["score"] = rank_score(row["distance"], row["quality_score"], row["created_at"])
        hits.append(row)

    return sorted(hits, key=lambda r: r["score"])[: settings.recall_top_k], via


def cite(incident_ids: list[str]) -> None:
    if not incident_ids:
        return
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
    params.append(max(1, min(limit, 50)))
    sql = f"""
        SELECT {RECALL_COLUMNS}
        FROM incidents
        WHERE {" AND ".join(conditions)}
          AND {CURRENT_SQL_FILTER}
        ORDER BY created_at DESC
        LIMIT %s
    """
    return _read(sql, params)


def _embed_incident(title: str, symptom: str) -> list[float]:
    return get_embedder().embed(f"{title} {symptom}")


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
    embedding = _embed_incident(title, symptom)
    row = fetch_one(
        f"""
        INSERT INTO incidents (
            title, symptom, root_cause, resolution, service, severity,
            source, external_id, embedding, resolved_at,
            created_at, valid_until
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s{VECTOR_CAST}, %s,
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


def supersede(old_id: str, new_id: str) -> bool:
    if old_id == new_id:
        return False
    row = fetch_one(
        """
        UPDATE incidents
        SET superseded_by = %s::UUID, valid_until = now()
        WHERE id = %s::UUID
          AND EXISTS (SELECT 1 FROM incidents WHERE id = %s::UUID)
        RETURNING id::STRING AS id
        """,
        (new_id, old_id, new_id),
    )
    return row is not None


def _with_validity(row: dict | None, now: datetime | None = None) -> dict | None:
    if row:
        row["validity"] = validity_of(row, now or datetime.now(timezone.utc))
    return row


def ids_by_external_id(external_ids: list[str]) -> dict[str, str]:
    rows = fetch(
        "SELECT external_id, id::STRING AS id FROM incidents WHERE external_id = ANY(%s)",
        (external_ids,),
    )
    return {row["external_id"]: row["id"] for row in rows}


def get_incident(incident_id: str) -> dict | None:
    row = fetch_one(
        f"SELECT {MEMORY_COLUMNS} FROM incidents WHERE id = %s::UUID",
        (incident_id,),
    )
    return _with_validity(row)


def update_incident(incident_id: str, changes: dict) -> dict | None:
    if not changes:
        return get_incident(incident_id)

    unknown = set(changes) - UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"Unknown incident columns: {', '.join(sorted(unknown))}")

    sets = []
    params: list = []
    for field, value in changes.items():
        sets.append(f"{field} = %s")
        params.append(value)

    if "title" in changes or "symptom" in changes:
        existing = get_incident(incident_id)
        if existing is None:
            return None
        title = changes.get("title") or existing["title"]
        symptom = changes.get("symptom") or existing["symptom"]
        if (title, symptom) != (existing["title"], existing["symptom"]):
            sets.append(f"embedding = %s{VECTOR_CAST}")
            params.append(to_vector_literal(_embed_incident(title, symptom)))

    params.append(incident_id)
    row = fetch_one(
        f"""
        UPDATE incidents
        SET {", ".join(sets)}
        WHERE id = %s::UUID
        RETURNING {MEMORY_COLUMNS}
        """,
        params,
    )
    return _with_validity(row)


def delete_incident(incident_id: str) -> bool:
    execute(
        "UPDATE incidents SET superseded_by = NULL WHERE superseded_by = %s::UUID",
        (incident_id,),
    )
    row = fetch_one(
        "DELETE FROM incidents WHERE id = %s::UUID RETURNING id::STRING AS id",
        (incident_id,),
    )
    return row is not None


def clear_memory() -> int:
    rows = fetch("DELETE FROM incidents RETURNING id")
    return len(rows)


def list_memory(service: str | None = None, limit: int = 100) -> list[dict]:
    params: list = []
    service_filter = ""
    if service:
        service_filter = "WHERE service = %s"
        params.append(service)
    params.append(limit)
    rows = fetch(
        f"""
        SELECT {MEMORY_COLUMNS}
        FROM incidents
        {service_filter}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        params,
    )
    now = datetime.now(timezone.utc)
    return [_with_validity(row, now) for row in rows]
