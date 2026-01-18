import yaml
import requests
import os
import argparse
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from download import download_meeting
from typing import Dict, List

import logging

wcac_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wcac.org/",
    "Connection": "keep-alive",
}

class PublicMeeting:
    def __init__(self, video_id: str, name: str, playlist_id: str):
        self.video_id = video_id
        self.name = name
        self.filename = "{}.mp4".format(name.replace(" ", "_"))
        self.playlist_id = playlist_id
        self.filesize = 0
    
    def delete_video(self):
        os.remove(self.filename)

class MeetingDownloader:
    def __init__(self, args: argparse.Namespace):
        settings = yaml.safe_load(open('settings.yaml', 'r'))
        self.url = settings['telvue_url']
        self.player_id = settings['player_id']
        self.playlists = settings['playlists']

        self.session = requests.Session()
        self.session.headers.update(wcac_headers)

    def get_new_public_meetings(self, playlists: Dict) -> List:
        public_meetings = []

        for org_name, playlist_id in self.playlists.items():
            time.sleep(2)   # add delay to mimic human browsing behavior
            res = self.session.get(
                "{}/{}/playlists/{}".format(self.url, self.player_id, playlist_id)
            )
            soup = BeautifulSoup(res.content, features="html.parser")

            n = len(public_meetings)
            for meeting in reversed(soup.find_all("div", class_="summary")):
                video_id = meeting.find_next("a")['href'].split("/")[-1]

                # usually something like 'City Council mm-dd-YY'
                meeting_name = meeting.find_next("p").string
                if meeting_name in playlists.get('recent_videos', []):
                    break

                public_meetings.insert(n, PublicMeeting(video_id, meeting_name, playlists[org_name]))

            if len(public_meetings) > 5:
                # get the most recent meetings only
                public_meetings = public_meetings[::-1]
                public_meetings = public_meetings[:5]
                break

        return(public_meetings)

    def download_meeting(self, meeting: PublicMeeting):
        page_url = "{}/{}/media/{}".format(self.url, self.player_id, meeting.video_id)
        res = self.session.get("{}/{}/media/{}".format(self.url, self.player_id, meeting.video_id))
        
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

        download_meeting(download_url, meeting.name)
        
        
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action="store_true")
    args = parser.parse_args()

    downloader = MeetingDownloader(args)

    playlists = {
        "recent_videos": [],
        "City Council": "PL1A2F9C3D1E3B4F5D",
    }
    meeting_metadata = downloader.get_new_public_meetings(playlists)


    for meeting in meeting_metadata:
        downloader.download_meeting(meeting)
