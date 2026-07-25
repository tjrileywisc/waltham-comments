import os
import psycopg
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_readonly_pool: ConnectionPool | None = None
_gis_pool: ConnectionPool | None = None

def init_pools() -> None:
    """Initialize connection pools; call once at application startup."""
    global _pool, _readonly_pool, _gis_pool
    _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=0, max_size=10)

    ro_user = os.environ["POSTGRES_READONLY_USER"]
    ro_password = os.environ["POSTGRES_READONLY_PASSWORD"]
    ro_db = os.environ["POSTGRES_DB"]
    _readonly_pool = ConnectionPool(
        f"postgresql://{ro_user}:{ro_password}@postgres:5444/{ro_db}",
        min_size=0,
        max_size=5,
    )
    
    POSTGIS_HOST = os.environ["POSTGIS_HOST"]
    POSTGIS_DB = os.environ["POSTGIS_DB"]
    _gis_pool = ConnectionPool(
        f"postgresql://{ro_user}:{ro_password}@{POSTGIS_HOST}/{POSTGIS_DB}",
        min_size=0,
        max_size=5
    )

def close_pools() -> None:
    """Close connection pools; call at application shutdown."""
    if _pool:
        _pool.close()
    if _readonly_pool:
        _readonly_pool.close()
    if _gis_pool:
        _gis_pool.close()

def connect() -> psycopg.Connection:
    """Return a pooled connection to the main database."""
    assert _pool is not None, "Pools not initialized"
    return _pool.connection()

def readonly_connect() -> psycopg.Connection:
    """Return a pooled connection to the read-only database account."""
    assert _readonly_pool is not None, "Pools not initialized"
    return _readonly_pool.connection()

def gis_connect() -> psycopg.Connection:
    """Return a pooled connection to the main database."""
    assert _gis_pool is not None, "Pools not initialized"
    return _gis_pool.connection()

def get_transcript(conn: psycopg.Connection, meeting_name: str) -> list[dict]:
    """Fetch all utterances for a meeting, ordered by segment index."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.start_time, u.end_time, u.text, s.speaker_name
            FROM utterances u
            INNER JOIN meetings m on m.id = u.meeting_id
            INNER JOIN speakers s on s.id = u.speaker_id
            WHERE m.meeting_name = %s
            ORDER BY u.segment_index
            """,
            (meeting_name,),
        )
        rows = cur.fetchall()
    return [
        {"id": row[0], "start": row[1], "end": row[2], "text": row[3], "speaker": row[4]}
        for row in rows
    ]
