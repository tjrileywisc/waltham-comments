import csv
import os
import sys
from pathlib import Path

import psycopg
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "transcription-service"))
from db import build_window_text

EMBEDDINGS_SERVICE_URL = os.environ.get("EMBEDDINGS_SERVICE_URL", "http://localhost:8001")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://waltham:waltham_dev@localhost:5432/waltham")


def migrate_directory(transcriptions_dir: str) -> None:
    csv_files = sorted(Path(transcriptions_dir).glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    with psycopg.connect(DATABASE_URL) as conn:
        for csv_path in csv_files:
            _migrate_meeting(conn, csv_path.stem, csv_path)


def _migrate_meeting(conn, meeting_name: str, csv_path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM utterance_embeddings ue
            JOIN utterances u ON ue.utterance_id = u.id
            WHERE u.meeting_name = %s
            """,
            (meeting_name,),
        )
        count = cur.fetchone()[0]

    if count > 0:
        print(f"Skipping {meeting_name} (already in DB)")
        return

    print(f"Migrating {meeting_name}...")

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        segments = [
            {
                "start": float(row["start"]),
                "end": float(row["end"]),
                "text": row["text"],
                "speaker": row.get("speaker", "DEFAULT"),
            }
            for row in reader
        ]

    windowed_texts = [build_window_text(segments, i) for i in range(len(segments))]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO utterances (meeting_name, segment_index, start_time, end_time, text, speaker)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_name, segment_index) DO NOTHING
            """,
            [
                (meeting_name, i, seg["start"], seg["end"], seg["text"], seg["speaker"])
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
    print(f"  Done: {len(segments)} utterances")


if __name__ == "__main__":
    transcriptions_dir = sys.argv[1] if len(sys.argv) > 1 else "transcriptions"
    migrate_directory(transcriptions_dir)
