
from lib.utils import setup_logging

setup_logging()

import os
import logging

from lib.download import MeetingDownloader

if __name__ == "__main__":

    downloader = MeetingDownloader()

    playlists = {
        "City Council": "PL1A2F9C3D1E3B4F5D",
        "Zoning Board of Appeals": "PL5E6F7A8B9C0D1E2F",
    }
    
    playlists = [
        "City Council",
        "Zoning Board of Appeals",
    ]

    meeting_metadata = downloader.get_new_public_meetings(playlists)

    for meeting in meeting_metadata:
        try:
            m3u8_url = downloader.get_download_url(meeting)
            if m3u8_url:
                downloader.download_meeting(m3u8_url, meeting.name)
    
        except Exception as e:
            logging.error("Error downloading meeting {}: {}".format(meeting.name, str(e)))
            if os.path.exists(meeting.filename):
                logging.error("The meeting file will be removed: {}".format(meeting.filename))
                os.remove(meeting.filename)