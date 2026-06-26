from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row

from app.config import get_settings


def get_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("ISSA_DATABASE_URL is not configured. Add it to backend/.env.")
    return database_url


def fetch_all(sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    try:
        with psycopg.connect(get_database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("set statement_timeout = '12s'")
                cur.execute(sql, params or [])
                return list(cur.fetchall())
    except OperationalError as exc:
        raise RuntimeError("Database connection failed. Check ISSA_DATABASE_URL in backend/.env.") from exc
