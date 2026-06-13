import os
import psycopg
import requests

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")


def do_search(query: str) -> list:
    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": [query]},
        timeout=30,
    )
    resp.raise_for_status()
    query_embedding = resp.json()["embeddings"][0]
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.meeting_name, u.start_time, u.text, u.speaker,
                       1 - (ue.embedding <=> %s::vector) AS score
                FROM utterance_embeddings ue
                JOIN utterances u ON ue.utterance_id = u.id
                ORDER BY ue.embedding <=> %s::vector
                LIMIT 10
                """,
                (vec_str, vec_str),
            )
            rows = cur.fetchall()

    return [
        {
            "meeting_name": row[0],
            "start": row[1],
            "text": row[2],
            "speaker": row[3],
            "score": float(row[4]),
        }
        for row in rows
    ]
