import glob
import logging
import os
import time

from transcription import transcription
from monitoring import setup_logging

logger = setup_logging("transcription")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))

def main():
    while True:
        logger.info("Checking for audio files to transcribe...")
        for audio_file in glob.glob("audio/*.wav"):
            meeting_name = os.path.basename(audio_file).replace(".wav", "")
            if not os.path.exists(f"transcriptions/{meeting_name}.csv"):
                logger.info(f"Transcribing {meeting_name}...")
                transcription(meeting_name)
        logger.info(f"Done. Sleeping {POLL_INTERVAL}s.")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
