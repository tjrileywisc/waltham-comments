
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
    
if __name__ == "__main__":
    import glob
    
    videos = glob.glob("videos/*.mp4")
    
    for video in videos:
        video = video.replace("\\", "/")
        print(f"extracting audio from {video}")
        video = video.replace("videos/", "").replace(".mp4", "")
        extract_audio(video)