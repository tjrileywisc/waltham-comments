
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

    # delete model if low on GPU resources
    # import gc; import torch; gc.collect(); torch.cuda.empty_cache(); del model

    # 2. Align whisper output
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    # delete model if low on GPU resources
    # import gc; import torch; gc.collect(); torch.cuda.empty_cache(); del model_a

    # 3. Assign speaker labels
    diarize_model = DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)

    # add min/max number of speakers if known
    diarize_segments, speaker_embeddings = diarize_model(audio, min_speakers=MIN_SPEAKERS, return_embeddings=True)

    result = whisperx.assign_word_speakers(diarize_segments, result)

    # the speaker embeddings are used to match speakers between transcription runs; we want to be careful not
    # to overwrite it. it should be a database that is 'typical' for a meeting, i.e. best not to choose a meeting
    # with public comment as that will generate a lot of new speakers.

    new_speaker_ids = None
    if not os.path.exists("data/speaker_db.pkl"):
        Identifier.save_database(speaker_embeddings, f"data/speaker_db.pkl")
    else:
        # load the speaker embeddings database and try to match our current vectors against it
        identifier = Identifier()
        new_speaker_ids = identifier(speaker_embeddings)

    # cleanup
    
    # we don't need the 'words' array for each segment
    for segment in result["segments"]:
        segment.pop("words", None)
        
        if new_speaker_ids:
            # for example, SPEAKER_00
            old_speaker_id = segment["speaker"]
            old_speaker_idx = int(old_speaker_id.split("_")[1])
            new_speaker_id = new_speaker_ids[old_speaker_idx]
            segment["speaker"] = new_speaker_id

    pd.DataFrame(result["segments"]).to_csv(f"transcriptions/{meeting_name}.csv", index=False)
    
if __name__ == "__main__":
    import sys
    transcription(sys.argv[1])