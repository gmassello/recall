import logging
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, open=False)


def _pool() -> ConnectionPool:
    if pool.closed:
        pool.open()
    return pool


def fetch(sql: str, params: Any = None) -> list[dict]:
    with _pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_one(sql: str, params: Any = None) -> dict | None:
    rows = fetch(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Any = None) -> None:
    with _pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)


def render(sql: str, params: Any = None) -> str:
    with _pool().connection() as conn:
        return psycopg.ClientCursor(conn).mogrify(sql, params)


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in embedding) + "]"


def init_schema() -> None:
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        try:
            conn.execute("SET CLUSTER SETTING feature.vector_index.enabled = true")
        except psycopg.Error as exc:
            log.warning("Could not enable feature.vector_index: %s", exc)
        conn.execute(SCHEMA_PATH.read_text())
    log.info("Schema ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_schema()
