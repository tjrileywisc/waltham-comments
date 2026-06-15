import os
import psycopg
import requests

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")

type UtteranceResult = dict[str, str|float]

def vector_search(query: str) -> list[UtteranceResult]:
    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": [query]},
        timeout=30
    )
    resp.raise_for_status()
    query_embedding = resp.json()["embeddings"][0]
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, m.meeting_name, u.start_time, u.text, s.speaker_name,
                    1 - (ue.embedding <=> %s::vector) AS score
                FROM utterance_embeddings ue
                JOIN utterances u ON ue.utterance_id = u.id
                JOIN speakers s on s.id = u.speaker_id
                JOIN meetings m on u.meeting_id = m.id
                ORDER BY ue.embedding <=> %s::vector
                LIMIT 10
                """,
                (vec_str, vec_str)
            )
            rows = cur.fetchall()
            
    return [
        {
            "id": row[0],
            "meeting_name": row[1],
            "start": row[2],
            "text": row[3],
            "speaker_name": row[4],
            "score": float(row[5]),
        }
        for row in rows
    ]

def exact_search(query: str) -> list[UtteranceResult]:

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id, m.meeting_name, u.start_time, u.text, s.speaker_name,
                    ts_rank_cd(u.ts_vector, phraseto_tsquery('english', %s)) AS exact_score
                FROM utterances u
                JOIN meetings m on u.meeting_id = m.id
                JOIN speakers s on u.speaker_id = s.id
                WHERE
                    ts_vector @@ phraseto_tsquery('english', %s)
                ORDER BY exact_score DESC
                LIMIT 10
                """,
                (query, query)
            )
            rows = cur.fetchall()
            
    return [
        {
            "id": row[0],
            "meeting_name": row[1],
            "start": row[2],
            "text": row[3],
            "speaker_name": row[4],
            "score": float(row[5]),
        }
        for row in rows
    ]

def do_search(query: str) -> list[UtteranceResult]:
    scores = {}
    # RRF constant, just hardcoded for now
    k = 60
    
    exact_results = exact_search(query)
    vector_results = vector_search(query)
    
    all_results = {r["id"]: r for r in exact_results + vector_results}

    for subset in [exact_results, vector_results]:
        for rank, result in enumerate(subset):
            uid = result["id"]
            scores[uid] = scores.get(uid, 0) + 1 / (k + rank)

    res = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [all_results[uid] for uid, _ in res]
