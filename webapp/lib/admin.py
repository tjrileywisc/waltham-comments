import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from psycopg.types.json import Json

security = HTTPBasic()


def get_admin(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    admin_user = os.environ.get("ADMIN_USER", "")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise HTTPException(status_code=503, detail="Admin credentials not configured")
    ok = (
        secrets.compare_digest(credentials.username, admin_user)
        and secrets.compare_digest(credentials.password, admin_password)
    )
    if not ok:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


def get_meetings(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.meeting_name, m.meeting_date, m.meeting_type,
                   COUNT(se.id) FILTER (WHERE se.speaker_id IS NULL) AS unlabeled_count
            FROM meetings m
            LEFT JOIN speaker_embeddings se ON se.meeting_id = m.id
            GROUP BY m.id
            ORDER BY m.meeting_date DESC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "meeting_name": r[1],
            "meeting_date": str(r[2]),
            "meeting_type": r[3],
            "unlabeled_count": r[4] or 0,
        }
        for r in rows
    ]


def get_clusters(conn, meeting_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT se.id, se.diarization_speaker, se.is_canonical, s.speaker_name
            FROM speaker_embeddings se
            LEFT JOIN speakers s ON s.id = se.speaker_id
            WHERE se.meeting_id = %s
            ORDER BY se.diarization_speaker
            """,
            (meeting_id,),
        )
        clusters = cur.fetchall()

        result = []
        for se_id, disp_speaker, is_canonical, speaker_name in clusters:
            cur.execute(
                """
                SELECT u.id, u.start_time, u.end_time, u.text, u.confidence
                FROM utterances u
                WHERE u.meeting_id = %s AND u.diarization_speaker = %s
                ORDER BY u.segment_index
                LIMIT 50
                """,
                (meeting_id, disp_speaker),
            )
            utterances = [
                {
                    "id": row[0],
                    "start": float(row[1]),
                    "end": float(row[2]),
                    "text": row[3],
                    "confidence": float(row[4]) if row[4] is not None else None,
                }
                for row in cur.fetchall()
            ]
            result.append(
                {
                    "embedding_id": se_id,
                    "diarization_speaker": disp_speaker,
                    "speaker_name": speaker_name,
                    "is_canonical": is_canonical,
                    "utterances": utterances,
                }
            )
    return result


def label_cluster(conn, meeting_id: int, diarization_speaker: str, speaker_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM speakers WHERE speaker_name = %s", (speaker_name,))
        row = cur.fetchone()
        if row:
            speaker_id = row[0]
        else:
            cur.execute(
                "INSERT INTO speakers (speaker_name) VALUES (%s) RETURNING id",
                (speaker_name,),
            )
            speaker_id = cur.fetchone()[0]

        cur.execute(
            "UPDATE utterances SET speaker_id = %s WHERE meeting_id = %s AND diarization_speaker = %s",
            (speaker_id, meeting_id, diarization_speaker),
        )
        cur.execute(
            "UPDATE speaker_embeddings SET speaker_id = %s WHERE meeting_id = %s AND diarization_speaker = %s",
            (speaker_id, meeting_id, diarization_speaker),
        )
    conn.commit()


def set_canonical(conn, embedding_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT speaker_id FROM speaker_embeddings WHERE id = %s", (embedding_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Embedding not found")
        if row[0] is None:
            raise HTTPException(
                status_code=400, detail="Label this cluster first before marking it canonical"
            )
        speaker_id = row[0]
        cur.execute(
            "UPDATE speaker_embeddings SET is_canonical = FALSE WHERE speaker_id = %s",
            (speaker_id,),
        )
        cur.execute(
            "UPDATE speaker_embeddings SET is_canonical = TRUE WHERE id = %s",
            (embedding_id,),
        )
    conn.commit()


def enqueue_relabel_job(conn, meeting_id: int) -> int:
    """Insert a relabel job for the given meeting and return the new job id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (job_type, payload) VALUES ('relabel', %s) RETURNING id",
            (Json({"meeting_id": meeting_id}),),
        )
        job_id = cur.fetchone()[0]
    conn.commit()
    return job_id


def get_speakers(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                s.id, s.speaker_name, s.speaker_role,
                se_c.id AS canonical_embedding_id,
                COUNT(u.id) AS utterance_count,
                AVG(u.confidence) AS mean_confidence,
                COUNT(u.id) FILTER (WHERE u.confidence IS NOT NULL AND u.confidence < 0.7) AS low_confidence_count
            FROM speakers s
            LEFT JOIN speaker_embeddings se_c
                ON se_c.speaker_id = s.id AND se_c.is_canonical = TRUE
            LEFT JOIN utterances u ON u.speaker_id = s.id
            WHERE s.speaker_name != 'DEFAULT'
            GROUP BY s.id, se_c.id
            ORDER BY s.speaker_name
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "speaker_name": r[1],
            "speaker_role": r[2],
            "canonical_embedding_id": r[3],
            "utterance_count": r[4],
            "mean_confidence": float(r[5]) if r[5] is not None else None,
            "low_confidence_count": r[6],
        }
        for r in rows
    ]
