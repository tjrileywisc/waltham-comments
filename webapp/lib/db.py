import os
import psycopg


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])

def readonly_connect() -> psycopg.Connection:

    POSTGRES_READONLY_USER = os.environ["POSTGRES_READONLY_USER"]
    POSTGRES_READONLY_PASSWORD = os.environ["POSTGRES_READONLY_PASSWORD"]
    POSTGRES_DB = os.environ["POSTGRES_DB"]
    return psycopg.connect(f"postgresql://{POSTGRES_READONLY_USER}:{POSTGRES_READONLY_PASSWORD}@postgres:5432/{POSTGRES_DB}")

def get_transcript(conn, meeting_name: str) -> list[dict]:
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
