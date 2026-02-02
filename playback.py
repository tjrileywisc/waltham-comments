
import pandas as pd

import soundfile as sf
import sounddevice as sd

# play each example no more than this amount of times
SAMPLE_LIMIT = 10

# or for this amount of time total
MAX_PLAYTIME = 60  # seconds

def playback(meeting_name: str):
    
    data, samplerate = sf.read(f"audio/{meeting_name}.wav")

    # Load diarization results
    df = pd.read_csv(f"diarization/{meeting_name}.csv")

    for speaker, group in df.groupby('speaker'):

        example_number = 0
        example_duration = 0
        print(f"Speaker {speaker}:")
        for _, row in group.iterrows():
            if example_number >= SAMPLE_LIMIT or example_duration >= MAX_PLAYTIME:
                # enough from this one
                continue
            
            seg_start = row['start']
            seg_end = row['stop']
            
            example_duration += (seg_end - seg_start)
            example_number += 1

            segment = data[int(seg_start*samplerate) : int(seg_end*samplerate)]
            print(f"  Playing segment from {seg_start} to {seg_end} seconds")
            sd.play(segment, samplerate)
            sd.wait()
            
if __name__ == "__main__":
    playback("City Council 1-12-26")
