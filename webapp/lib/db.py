import os
import psycopg


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"])


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
