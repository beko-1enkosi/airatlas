"""Short read-only transactions; no connection details cross the API boundary."""

import os

import psycopg
from psycopg.rows import dict_row


class DatabaseUnavailable(RuntimeError):
    """Public error without driver messages, SQL or credentials."""


def query(statement, parameters=()):
    dsn = os.environ.get("AIRATLAS_DATABASE_URL")
    if not dsn:
        raise DatabaseUnavailable("Data service unavailable.")
    try:
        with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '10s'")
            conn.execute("SET LOCAL TIME ZONE 'UTC'")
            return conn.execute(statement, parameters).fetchall()
    except psycopg.Error:
        raise DatabaseUnavailable("Data service unavailable.") from None
