import numpy as np
from numpy.typing import NDArray

from db import claim_pending_job, complete_job, fail_job
from identification import Identifier
from monitoring import setup_logging

logger = setup_logging("transcription")


def relabel_meeting(conn, meeting_id: int) -> None:
    """Re-run speaker identification on all unassigned clusters for a meeting.

    Only touches speaker_embeddings rows where speaker_id IS NULL.
    Clusters already assigned (manually or automatically) are left untouched.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT diarization_speaker, embedding_vec::text
            FROM speaker_embeddings
            WHERE meeting_id = %s AND speaker_id IS NULL AND embedding_vec IS NOT NULL
            """,
            (meeting_id,),
        )
        rows = cur.fetchall()

    if not rows:
        logger.info(f"No unassigned clusters for meeting {meeting_id}, skipping relabel")
        return

    speaker_embeddings: dict[str, NDArray[np.float64]] = {
        disp: np.array([float(x) for x in vec_text.strip("[]").split(",")], dtype=np.float64)
        for disp, vec_text in rows
    }

    results = Identifier()(conn, speaker_embeddings)
    cluster_ids = list(speaker_embeddings.keys())

    with conn.cursor() as cur:
        for cluster_id, (name, confidence) in zip(cluster_ids, results):
            if name == Identifier.DEFAULT_SPEAKER:
                continue

            cur.execute("SELECT id FROM speakers WHERE speaker_name = %s", (name,))
            row = cur.fetchone()
            if row is None:
                logger.warning(f"Speaker '{name}' returned by Identifier but not found in speakers table")
                continue
            speaker_id = row[0]

            cur.execute(
                "UPDATE utterances SET speaker_id = %s, confidence = %s "
                "WHERE meeting_id = %s AND diarization_speaker = %s",
                (speaker_id, confidence, meeting_id, cluster_id),
            )
            cur.execute(
                "UPDATE speaker_embeddings SET speaker_id = %s "
                "WHERE meeting_id = %s AND diarization_speaker = %s",
                (speaker_id, meeting_id, cluster_id),
            )
    conn.commit()
    logger.info(f"Relabel complete for meeting {meeting_id}")


def process_pending_jobs(conn) -> None:
    """Drain all pending jobs from the queue, processing each in order."""
    while True:
        job = claim_pending_job(conn)
        if job is None:
            break
        job_id, job_type, payload = job
        logger.info(f"Processing job {job_id} (type={job_type})")
        try:
            if job_type == "relabel":
                relabel_meeting(conn, payload["meeting_id"])
            else:
                raise ValueError(f"Unknown job type: {job_type!r}")
            complete_job(conn, job_id)
            logger.info(f"Job {job_id} completed")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            fail_job(conn, job_id, str(e))
