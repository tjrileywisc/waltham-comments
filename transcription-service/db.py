import os
import requests
import re
import psycopg
from datetime import date

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
            "SELECT 1 FROM meetings WHERE meeting_name = %s LIMIT 1",
            (meeting_name,),
        )
        return cur.fetchone() is not None


def extract_meeting_type(meeting_name: str) -> str:
    # ends with date, and sometimes a part number
    return re.sub(r" \d{1,2}-\d{1,2}-\d{2,}( Part \d+)?$", "", meeting_name)

def extract_meeting_date(meeting_name: str) -> date | None:
    
    match = re.search(r"(?P<month>\d{1,2})-(?P<day>\d{1,2})-(?P<year>\d{2,})", meeting_name)
    if not match:
        return
    
    month = match.group("month")
    day = match.group("day")
    year = match.group("year")
    
    return date(int(year) + 2000, int(month), int(day))

def extract_meeting_part(meeting_name: str) -> str | None:
    
    match = re.search(r"(?:Part )(\d+)$", meeting_name)
    if not match:
        return
    
    return match.group(1)

def save_meeting(conn, meeting_name: str, segments: list[dict]) -> tuple[int, dict[str, int]]:
    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    meeting_type = extract_meeting_type(meeting_name)
    meeting_date = extract_meeting_date(meeting_name)
    meeting_part = extract_meeting_part(meeting_name)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meetings (meeting_name, meeting_type, meeting_date, meeting_part) VALUES (%s, %s, %s, %s) RETURNING id",
            (meeting_name, meeting_type, meeting_date, meeting_part),
        )
        meeting_id = cur.fetchone()[0]

        speakers = set([seg.get("speaker", "DEFAULT") for seg in segments])
        speakers.add("DEFAULT")
        cur.execute(
            "SELECT id, speaker_name FROM speakers WHERE speaker_name = ANY(%s)",
            (list(speakers),),
        )
        speaker_lookup = {sp: sp_id for sp_id, sp in cur.fetchall()}

        cur.executemany(
            """
            INSERT INTO utterances
                (meeting_id, segment_index, start_time, end_time, text, speaker_id, diarization_speaker, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id, segment_index) DO NOTHING
            """,
            [
                (
                    meeting_id, i, seg["start"], seg["end"], seg["text"],
                    speaker_lookup.get(seg.get("speaker", "DEFAULT")) or speaker_lookup["DEFAULT"],
                    seg.get("diarization_speaker"),
                    seg.get("confidence"),
                )
                for i, seg in enumerate(segments)
            ],
        )

        cur.execute(
            "SELECT id FROM utterances WHERE meeting_id = %s ORDER BY segment_index",
            (meeting_id,),
        )
        ids = [row[0] for row in cur.fetchall()]

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
    return meeting_id, speaker_lookup


def save_speaker_embeddings(
    conn,
    meeting_id: int,
    speaker_embeddings: dict,
    cluster_to_speaker_id: dict[str, int | None],
) -> None:
    with conn.cursor() as cur:
        for cluster_id, embedding in speaker_embeddings.items():
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            cur.execute(
                """
                INSERT INTO speaker_embeddings (speaker_id, meeting_id, diarization_speaker, embedding_vec)
                VALUES (%s, %s, %s, %s::vector)
                ON CONFLICT (meeting_id, diarization_speaker) DO NOTHING
                """,
                (cluster_to_speaker_id.get(cluster_id), meeting_id, cluster_id, vec_str),
            )
    conn.commit()
