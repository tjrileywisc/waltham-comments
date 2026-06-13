import os
import psycopg


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"])


def get_transcript(conn, meeting_name: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, start_time, end_time, text, speaker
            FROM utterances
            WHERE meeting_name = %s
            ORDER BY segment_index
            """,
            (meeting_name,),
        )
        rows = cur.fetchall()
    return [
        {"id": row[0], "start": row[1], "end": row[2], "text": row[3], "speaker": row[4]}
        for row in rows
    ]
