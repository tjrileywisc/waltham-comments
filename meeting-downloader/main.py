import logging
import os
import time

from downloader import MeetingDownloader
from audio import extract_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))


def main():
    downloader = MeetingDownloader()
    while True:
        logging.info("Checking for new meetings...")
        meetings = downloader.get_new_public_meetings(None)
        for meeting in meetings:
            url = downloader.get_download_url(meeting)
            if url:
                downloader.download_meeting(url, meeting.name)
                extract_audio(meeting.name)
        logging.info(f"Done. Sleeping {POLL_INTERVAL}s.")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
