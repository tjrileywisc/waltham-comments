import glob
import psycopg
import os
import time

from db import is_meeting_processed
from relabel import process_pending_jobs
from transcription import transcription
from monitoring import setup_logging

logger = setup_logging("transcription")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))


def main():
    """Poll for audio files to transcribe and drain the job queue each cycle."""
    while True:
        logger.info("Checking for audio files to transcribe...")
        for audio_file in glob.glob("audio/*.wav"):
            meeting_name = os.path.basename(audio_file).replace(".wav", "")
            with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
                if is_meeting_processed(conn, meeting_name):
                    continue

            logger.info(f"Transcribing {meeting_name}...")
            transcription(meeting_name)

        logger.info("Checking job queue...")
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            process_pending_jobs(conn)

        logger.info(f"Done. Sleeping {POLL_INTERVAL}s.")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
