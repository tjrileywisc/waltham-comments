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

def save_meeting(conn, meeting_name: str, segments: list[dict]) -> None:
    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    meeting_type = extract_meeting_type(meeting_name)
    
    meeting_date = extract_meeting_date(meeting_name)
    
    meeting_part = extract_meeting_part(meeting_name)

    with conn.cursor() as cur:
        # insert the new meeting
        query = """
        INSERT INTO meetings (meeting_name, meeting_type, meeting_date, meeting_part) VALUES (%s, %s, %s, %s) returning id
        """
        cur.execute(query, (meeting_name, meeting_type, meeting_date, meeting_part))
        meeting_id = cur.fetchone()[0]
        
        # get speaker ids we know about
        query = """
        SELECT id, speaker_name FROM speakers WHERE speaker_name = ANY(%s)
        """
        speakers = set([seg.get("speaker", "DEFAULT") for seg in segments])
        # ensure we always have this one
        speakers.add("DEFAULT")
        
        cur.execute(query, (list(speakers),))
        speaker_lookup = {sp : sp_id for sp_id, sp in cur.fetchall()}
        
        # add the utterances
        cur.executemany(
            """
            INSERT INTO utterances (meeting_id, segment_index, start_time, end_time, text, speaker_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id, segment_index) DO NOTHING
            """,
            [
                (meeting_id, i, seg["start"], seg["end"], seg["text"],
                    # handle the hopefully rare case of us somehow adding a speaker that isn't recorded yet
                    speaker_lookup.get(seg.get("speaker", "DEFAULT")) or speaker_lookup["DEFAULT"]
                )
                for i, seg in enumerate(segments)
            ],
        )
        
        # get the ids of the new utterances
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
