
from . import HF_TOKEN, MIN_SPEAKERS
from .utils import make_tensorboard_writer

from .identification import Identifier

import os
import pandas as pd
import whisperx
from whisperx.diarize import DiarizationPipeline

# ref. https://github.com/m-bain/whisperX/issues/1304
# a warning displays due to a potential security issue loading weights-only checkpoints
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

DEVICE = "cuda"

BATCH_SIZE = 16 # reduce if low on GPU mem
COMPUTE_TYPE = "float16" # change to "int8" if low on GPU mem (may reduce accuracy)

def transcription(meeting_name: str):
    """Diarizes and transcripts a meeting

    Args:
        meeting_name (str): the name of the meeting
    """

    audio_file = f"audio/{meeting_name}.wav"
    
    os.makedirs("transcriptions", exist_ok=True)

    # 1. Transcribe with original whisper (batched)
    model = whisperx.load_model("base", DEVICE, compute_type=COMPUTE_TYPE)

    # save model to local path (optional)
    # model_dir = "/path/"
    # model = whisperx.load_model("large-v2", device, compute_type=compute_type, download_root=model_dir)

    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=BATCH_SIZE)
    print(result["segments"]) # before alignment

    # delete model if low on GPU resources
    # import gc; import torch; gc.collect(); torch.cuda.empty_cache(); del model

    # 2. Align whisper output
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    # print(result["segments"]) # after alignment

    # delete model if low on GPU resources
    # import gc; import torch; gc.collect(); torch.cuda.empty_cache(); del model_a

    # 3. Assign speaker labels
    diarize_model = DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)

    # add min/max number of speakers if known
    diarize_segments, speaker_embeddings = diarize_model(audio, min_speakers=MIN_SPEAKERS, max_speakers=MIN_SPEAKERS + 1, return_embeddings=True)

    make_tensorboard_writer(speaker_embeddings)

    Identifier.save_database(speaker_embeddings, f"data/speaker_db.pkl")

    result = whisperx.assign_word_speakers(diarize_segments, result)

    print(diarize_segments)
    print(result["segments"]) # segments are now assigned speaker IDs

    # we don't need the 'words' array for each segment
    for segment in result["segments"]:
        segment.pop("words", None)
        
    pd.DataFrame(result["segments"]).to_csv(f"transcriptions/{meeting_name}.csv", index=False)
    
if __name__ == "__main__":
    transcription("City Council 1-12-26")