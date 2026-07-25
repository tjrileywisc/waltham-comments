
from lib.db import readonly_connect
from lib.state import get_video_ids
from lib.search import vector_search

def get_schemas() -> str:
    """Return a formatted summary of all public tables and their columns, suitable for inclusion in a prompt."""
    with readonly_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position;
                """
            )
            rows = cur.fetchall()

    tables: dict[str, list[str]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append(f"{column_name} ({data_type})")

    return "\n".join(f"{t}: {', '.join(cols)}" for t, cols in tables.items())

def execute_meetings_sql(query: str) -> list[dict]:
    """
    Execute a SQL read-only query on meetings data. If querying for utterances,
    be sure to limit results to 50 or less.
    """

    import psycopg.rows

    ctx = readonly_connect()

    with ctx as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query)
            return cur.fetchall()
