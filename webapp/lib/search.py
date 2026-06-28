import os
import psycopg
import requests

from lib.db import connect, readonly_connect

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8001")

type UtteranceResult = dict[str, str|float]

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

def execute_sql(query: str) -> list[dict]:
    """
    Execute a SQL read-only query. If querying for utterances,
    be sure to limit results to 50 or less.
    """
    import psycopg.rows
    with readonly_connect() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query)
            return cur.fetchall()

def vector_search(query: str) -> list[UtteranceResult]:
    resp = requests.post(
        f"{EMBEDDINGS_SERVICE_URL}/embeddings",
        json={"sentences": [query]},
        timeout=30
    )
    resp.raise_for_status()
    query_embedding = resp.json()["embeddings"][0]
    vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    with connect() as conn:
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
