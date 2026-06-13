import os
import requests
import psycopg

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")


def build_window_text(segments: list[dict], current_idx: int) -> str:
    current = segments[current_idx]
    if current["end"] - current["start"] >= 5.0:
        return current["text"]
    window_start = current["end"] - 5.0
    parts = [seg["text"] for seg in segments[:current_idx] if seg["start"] >= window_start]
    parts.append(current["text"])
    return " ".join(parts)


def is_meeting_processed(conn, meeting_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM utterances WHERE meeting_name = %s LIMIT 1",
            (meeting_name,),
        )
        return cur.fetchone() is not None



def save_meeting(conn, meeting_name: str, segments: list[dict]) -> None:
    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO utterances (meeting_name, segment_index, start_time, end_time, text, speaker)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_name, segment_index) DO NOTHING
            """,
            [
                (meeting_name, i, seg["start"], seg["end"], seg["text"], seg.get("speaker", "DEFAULT"))
                for i, seg in enumerate(segments)
            ],
        )
        cur.execute(
            "SELECT id FROM utterances WHERE meeting_name = %s ORDER BY segment_index",
            (meeting_name,),
        )
        ids = [row[0] for row in cur.fetchall()]
    conn.commit()

    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": windowed_texts},
        timeout=120,
    )
    resp.raise_for_status()
    embeddings = resp.json()["embeddings"]

    with conn.cursor() as cur:
        for uid, embedding in zip(ids, embeddings):
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            cur.execute(
                "INSERT INTO utterance_embeddings (utterance_id, embedding) VALUES (%s, %s::vector)"
                " ON CONFLICT DO NOTHING",
                (uid, vec_str),
            )
    conn.commit()
