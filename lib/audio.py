
import os
import subprocess
import logging

def extract_audio(meeting_name: str):
    """Extract the audio from an mp4 meeting to wav
    for diarization

    Args:
        meeting_name (str): the meeting name
    """

    input_file = f"videos/{meeting_name}.mp4"
    output_file = f"audio/{meeting_name}.wav"
    
    os.makedirs("audio", exist_ok=True)
    if os.path.exists(output_file):
        logging.info(f"Audio for {meeting_name} already extracted.")
        return

    logging.info(f"Extracting audio for {meeting_name}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_file,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_file
    ]

    subprocess.run(cmd, check=True)