import subprocess
import logging
import json
import os
import re
import requests
import yaml
import time
import shutil

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from monitoring import setup_logging
from publicmeeting import PublicMeeting
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm

WCAC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://videoplayer.telvue.com"
}

logger = setup_logging("downloader")
class MeetingDownloader:
    def __init__(self):
        settings = yaml.safe_load(open('settings.yaml', 'r'))
        self.url = settings['telvue_url']
        self.player_id = settings['player_id']
        self.playlists = settings['playlists']
        
        retry_strategy = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[429, 502, 503, 504],
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(WCAC_HEADERS)

    def get_new_public_meetings(self, playlists: list[str] | None) -> list[str]:
        """Queries the WCAC site for new meetings

        Args:
            playlists (list | None): A list of playlist names to filter on. If None, all playlists are checked.

        Returns:
            list: a list of PublicMeeting objects
        """
        public_meetings = []

        if playlists is not None:
            # filter
            self.playlists = {k: v for k, v in self.playlists.items() if k in playlists}

        for org_name, playlist_id in self.playlists.items():

            self.session.headers.update({
                "Referer": f"https://videoplayer.telvue.com/player/{self.player_id}/playlists/{playlist_id}"
            })

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

                if meeting_name is None:
                    logger.warning(f"unable to parse '{tag}' for a meeeting name")
                    continue
                elif PublicMeeting.meeting_exists(meeting_name):
                    logger.info(f"skipping {meeting_name}, already downloaded")
                    continue
                elif not re.search(r"(?<=\s)\d{1,2}-\d{1,2}-\d{2,}( Part \d+)?$", meeting_name):
                    # expecting 'test meeting 2-2-01', never with a date at the start of the line
                    # and sometimes 'Part n' appended to the end
                    logger.warning(f"skipping '{meeting_name}', which doesn't have a recognized date format")
                    continue

                public_meetings.insert(n, PublicMeeting(video_id, meeting_name, self.playlists[org_name]))

            # TODO: someday, just queue this work up
            if len(public_meetings) > 5:
                break

        return public_meetings[-5:][::-1]

    def get_download_url(self, meeting: PublicMeeting) -> str | None:
        """Return the meeting download URL. This is somewhat tricky because
        we need to mimic a browser and be careful about using the site token.

        Args:
            meeting (PublicMeeting): The meeting object, with metadata

        Returns:
            str | None: an m3u8 url pointing to video segments, or None if
            the URL couldn't be followed
        """

        page_url = f"{self.url}/{self.player_id}/media/{meeting.video_id}"

        m3u8_url = None
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def handle_route(route, request):
                nonlocal m3u8_url
                url = request.url

                if "master.m3u8" in url and m3u8_url is None:
                    m3u8_url = url.replace("master.m3u8", "index-savc_1000k-v1-a1.m3u8")
                    logger.info(f"Captured: {m3u8_url}")

                route.abort()  # abort everything - master, variants, segments

            page.route("**/*.m3u8", handle_route)
            page.route("**/*.ts", lambda route, _: route.abort())

            page.goto(page_url)

            for _ in range(50):
                if m3u8_url:
                    break
                page.wait_for_timeout(100)

            browser.close()

        if not m3u8_url:
            logger.error(f"No playlist URL found for meeting {meeting.name}")
            return None

        return m3u8_url

    def _get_file_duration(self, filepath: str) -> float:
        """Get the duration of the actually downloaded file.

        Args:
            filepath (str): the path to the video file

        Returns:
            float: the duration in seconds
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    
    def _cleanup(self, ts_dir: str) -> None:
        """Clean up the temporary download directory

        Args:
            ts_dir (str): the path to the temp segments directory for the video
        """
        
        # clean up temp segments
        shutil.rmtree(ts_dir, ignore_errors=True)

    def download_meeting(self, download_url: str, meeting_name: str):
        """Download a meeting from the site.

        Args:
            download_url (str): The m3u8 URL for the meeting
            meeting_name (str): The title of the meeting
        """
        output_file = f"videos/{meeting_name}.mp4"
        os.makedirs("videos", exist_ok=True)

        if os.path.exists(output_file):
            logger.info(f"Meeting {meeting_name} already downloaded.")
            return

        # get the playlist
        resp = self.session.get(download_url)
        lines = resp.text.splitlines()

        # parse segment URLs
        base_url = download_url.rsplit("/", 1)[0] + "/"
        segments = []
        for line in lines:
            if line.startswith("#EXTINF:"):
                duration = float(line.split(":")[1].split(",")[0])
                segments.append(duration)
            elif line and not line.startswith("#"):
                segments[-1] = (line if line.startswith("http") else base_url + line, segments[-1])

        segments = [(url, dur) for url, dur in segments if isinstance(url, str)]
        total_duration = sum(dur for _, dur in segments)

        # download segments one at a time
        ts_dir = f"videos/.tmp_{meeting_name}"
        os.makedirs(ts_dir, exist_ok=True)

        try:
            pbar = tqdm(total=total_duration, unit="s", desc=meeting_name)
            for i, (seg_url, duration) in enumerate(segments):
                seg_file = os.path.join(ts_dir, f"seg-{i:04d}.ts")
                if not os.path.exists(seg_file):
                    time.sleep(0.1)  # small delay between requests
                    seg_resp = self.session.get(seg_url)
                    if seg_resp.status_code >= 400:
                        logger.error(f"Segment {i} returned {seg_resp.status_code}")
                        return
                    with open(seg_file, "wb") as f:
                        f.write(seg_resp.content)
                pbar.update(duration)
            pbar.close()

            # write concat file for ffmpeg
            concat_file = os.path.join(ts_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for i in range(len(segments)):
                    f.write(f"file '{os.path.abspath(os.path.join(ts_dir, f'seg-{i:04d}.ts'))}'\n")

            # mux with ffmpeg locally - no network calls
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-reset_timestamps", "1",
                output_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"ffmpeg mux failed: {result.stderr[-500:]}")
                return

            logger.info(f"Downloaded {meeting_name} ({total_duration:.0f}s)")
        except Exception as e:
            logger.warning(f"Failed to download {meeting_name}: {e}")
        finally:
            self._cleanup(ts_dir)

