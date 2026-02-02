
import subprocess
import logging
import json
import os
import requests
import yaml
import time
from urllib.parse import unquote

from .publicmeeting import PublicMeeting
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm

from typing import Dict, List

WCAC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wcac.org/",
    "Connection": "keep-alive",
}


class MeetingDownloader:
    def __init__(self):
        settings = yaml.safe_load(open('settings.yaml', 'r'))
        self.url = settings['telvue_url']
        self.player_id = settings['player_id']
        self.playlists = settings['playlists']

        self.session = requests.Session()
        self.session.headers.update(WCAC_HEADERS)

    def get_new_public_meetings(self, playlists: List | None) -> List:
        """Queries the WCAC site for new meetings

        Args:
            playlists (List | None): A list of playlist names to filter on. If None, all playlists are checked.

        Returns:
            List: a list of PublicMeeting objects
        """
        public_meetings = []
        
        if playlists is not None:
            # filter
            self.playlists = {k: v for k, v in self.playlists.items() if k in playlists}

        for org_name, playlist_id in self.playlists.items():
            time.sleep(2)   # add delay to mimic human browsing behavior
            res = self.session.get(
                "{}/{}/playlists/{}".format(self.url, self.player_id, playlist_id)
            )
            soup = BeautifulSoup(res.content, features="html.parser")

            n = len(public_meetings)
            for meeting in reversed(soup.find_all("div", class_="summary")):
                tag = meeting.find_next("a")
                if not tag:
                    continue
                
                if 'href' not in tag.attrs:
                    continue

                video_id = tag['href'].split("/")[-1]

                # usually something like 'City Council mm-dd-YY'
                tag = meeting.find_next("p")
                if not tag:
                    continue

                meeting_name = tag.string
                
                if meeting_name is None or PublicMeeting.meeting_exists(meeting_name):
                    continue

                public_meetings.insert(n, PublicMeeting(video_id, meeting_name, self.playlists[org_name]))

            if len(public_meetings) > 5:
                # get the most recent meetings only
                public_meetings = public_meetings[::-1]
                public_meetings = public_meetings[:5]
                break

        return(public_meetings)

    def get_download_url(self, meeting: PublicMeeting):
        page_url = "{}/{}/media/{}".format(self.url, self.player_id, meeting.video_id)
        
        playlist_urls = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("response", lambda r: playlist_urls.append(r.url) if ".m3u8" in r.url else None)
            page.goto(page_url)
            page.wait_for_timeout(5000)  # wait while network loads
            browser.close()
        
        if len(playlist_urls) == 0:
            logging.error("No playlist URL found for meeting {}".format(meeting.name))
            return
        
        # probably the first url works
        download_url = playlist_urls[0]

        self.download_meeting(download_url, meeting.name)

    def _get_duration(self, m3u8_url):
        
        headers = [f"{k}: {unquote(v)}" for k, v in WCAC_HEADERS.items()]
        
        headers.append(
            "Cookie: " + "; ".join([f"{k}={unquote(v)}" for k, v in self.session.cookies.get_dict().items()])
        )
        headers = "\r\n".join(headers) + "\r\n\r\n"
        
        cmd = [
            "ffprobe",
            "-headers", headers,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            "-loglevel", "trace",
            m3u8_url
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        process.wait()
        if process.returncode != 0:
            error_text = process.stdout.read()
            logging.error(f"ffprobe error: {error_text}")
            return

        # result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # data = json.loads(result.stdout)
        
        result = process.stdout.read()
        data = json.loads(result)
        
        return float(data["format"]["duration"])

    def download_meeting(self, download_url: str, meeting_name: str):
        output_file = f"videos/{meeting_name}.mp4"
        
        os.makedirs("videos", exist_ok=True)
        if os.path.exists(output_file):
            logging.info(f"Meeting {meeting_name} already downloaded.")
            return

        logging.info(f"Downloading meeting {meeting_name} from {download_url}")

        duration = self._get_duration(download_url) or 0.0
        
        headers = [f"{k}: {unquote(v)}" for k, v in WCAC_HEADERS.items()]
        
        headers.append(
            "Cookie: " + "; ".join([f"{k}={unquote(v)}" for k, v in self.session.cookies.get_dict().items()])
        )
        headers = "\r\n".join(headers) + "\r\n\r\n"
        
        cmd = [
            "ffmpeg",
            "-headers", headers,
            "-y",
            "-i", download_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-progress", "pipe:1",
            "-nostats",
            output_file
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )

        pbar = tqdm(
            total=duration,
            unit="s",
            unit_scale=False,
            desc=f"Downloading {meeting_name}",
            leave=True
        )

        last_time = 0.0

        for line in process.stdout:
            if line.startswith("out_time_ms="):
                current_time = int(line.split("=")[1]) / 1_000_000
                pbar.update(current_time - last_time)
                last_time = current_time

        process.wait()
        pbar.close()
