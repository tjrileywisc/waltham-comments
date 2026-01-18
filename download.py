
import subprocess
import logging
import json
import os

from tqdm import tqdm

def get_duration(m3u8_url):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        m3u8_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])

def download_meeting(download_url: str, meeting_name: str):
    output_file = f"videos/{meeting_name}.mp4"
    
    os.makedirs("videos", exist_ok=True)
    if os.path.exists(output_file):
        logging.info(f"Meeting {meeting_name} already downloaded.")
        return

    logging.info(f"Downloading meeting {meeting_name} from {download_url}")

    duration = get_duration(download_url)
    
    cmd = [
        "ffmpeg",
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