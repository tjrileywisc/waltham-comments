import logging
import os
import time

from monitoring import setup_logging
from downloader import MeetingDownloader
from audio import extract_audio

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", 3600))

PLAYLISTS = [
    {
        "City Council": 5499,
        "City Council Committees": 10088,
        "Zoning Board of Appeals": 5528,
    }
]

logger = setup_logging("downloader")

def main():
    downloader = MeetingDownloader()
    while True:
        logger.info("Checking for new meetings...")
        meetings = downloader.get_new_public_meetings(None)
        for meeting in meetings:
            url = downloader.get_download_url(meeting)
            if url:
                downloader.download_meeting(url, meeting.name)
                extract_audio(meeting.name)
        logger.info(f"Done. Sleeping {POLL_INTERVAL}s.")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
