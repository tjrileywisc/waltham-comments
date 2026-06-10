import gc
import os
from identification import Identifier

import pandas as pd
import torch
import whisperx
from whisperx.diarize import DiarizationPipeline

from monitoring import setup_logging

logger = setup_logging("transcription")

# ref. https://github.com/m-bain/whisperX/issues/1304
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

HF_TOKEN = os.environ.get("HF_TOKEN", "")

MIN_SPEAKERS = int(os.environ.get("MIN_SPEAKERS", 5))
MAX_SPEAKERS = int(os.environ.get("MAX_SPEAKERS", 18))

MODELS_DIR = os.environ.get("MODELS_DIR", "models")

# 0 means "use all available cores" in CTranslate2
CPU_THREADS = int(os.environ.get("CPU_THREADS", 0))

# Apply thread count to PyTorch (covers alignment model and diarization pipeline).
# Only set when explicitly configured — PyTorch's default (all cores) matches
# CTranslate2's default of 0.
if CPU_THREADS > 0:
    torch.set_num_threads(CPU_THREADS)

TEXT = "text"
SPEAKER = "speaker"

DEVICE = "cpu"
BATCH_SIZE = 1
COMPUTE_TYPE = "int8"

def transcription(meeting_name: str):
    """Diarizes and transcripts a meeting

    Args:
        meeting_name (str): the name of the meeting
    """

    audio_file = f"audio/{meeting_name}.wav"

    os.makedirs("transcriptions", exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    model = whisperx.load_model(
        "large-v2",
        DEVICE,
        compute_type=COMPUTE_TYPE,
        language="en",
        download_root=MODELS_DIR,
        cpu_threads=CPU_THREADS if CPU_THREADS > 0 else None,
    )

    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=BATCH_SIZE)

    gc.collect(); del model

    logger.info("Aligning whisper output")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    gc.collect(); del model_a

    logger.info("Assigning speaker labels")
    diarize_model = DiarizationPipeline(token=HF_TOKEN, device=DEVICE)

    diarize_segments, speaker_embeddings = diarize_model(
        audio,
        min_speakers=MIN_SPEAKERS,
        max_speakers=MAX_SPEAKERS,
        return_embeddings=True,
    )

    result = whisperx.assign_word_speakers(diarize_segments, result)

    new_speaker_ids = None
    if speaker_embeddings:
        if not os.path.exists(Identifier.DB_PATH):
            logger.info("Generating speaker database")
            Identifier.save_db(speaker_embeddings)
        else:
            logger.info("Matching identifying existing speakers")
            identifier = Identifier()
            new_speaker_ids = identifier(speaker_embeddings)

    for segment in result["segments"]:
        segment.pop("words", None)

        if new_speaker_ids:
            # TODO: determine why this might happen, seems to have something to do
            # with the model (it happens on large-v2 but not base)
            if not SPEAKER in segment:
                segment[SPEAKER] = Identifier.DEFAULT_SPEAKER
                continue

            old_speaker_id = segment[SPEAKER]
            old_speaker_idx = int(old_speaker_id.split("_")[1])
            new_speaker_id = new_speaker_ids[old_speaker_idx]
            segment[SPEAKER] = new_speaker_id

    df = pd.DataFrame(result["segments"])
    df.to_csv(f"transcriptions/{meeting_name}.csv", index_label="id")

if __name__ == "__main__":
    import sys
    transcription(sys.argv[1])
