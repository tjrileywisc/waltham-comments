import gc
import os
import psycopg

from identification import Identifier
from db import save_meeting, is_meeting_processed, save_speaker_embeddings

import torch
import whisperx
from whisperx.diarize import DiarizationPipeline

from monitoring import setup_logging

logger = setup_logging("transcription")

os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

HF_TOKEN = os.environ.get("HF_TOKEN", "")
MIN_SPEAKERS = int(os.environ.get("MIN_SPEAKERS", 5))
MAX_SPEAKERS = int(os.environ.get("MAX_SPEAKERS", 18))
MODELS_DIR = os.environ.get("MODELS_DIR", "models")
CPU_THREADS = int(os.environ.get("CPU_THREADS", 0))

if CPU_THREADS > 0:
    torch.set_num_threads(CPU_THREADS)

TEXT = "text"
SPEAKER = "speaker"
DEVICE = "cpu"
BATCH_SIZE = 1
COMPUTE_TYPE = "int8"


def transcription(meeting_name: str):

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if is_meeting_processed(conn, meeting_name):
            logger.info(f"skipping {meeting_name}, already in database")
            return

    audio_file = f"audio/{meeting_name}.wav"
    os.makedirs(MODELS_DIR, exist_ok=True)

    model = whisperx.load_model(
        "medium", DEVICE,
        compute_type=COMPUTE_TYPE, language="en",
        download_root=MODELS_DIR, threads=CPU_THREADS,
    )

    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=BATCH_SIZE)
    del model; gc.collect()

    logger.info("Aligning whisper output")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)
    del model_a; gc.collect()

    logger.info("Assigning speaker labels")
    diarize_model = DiarizationPipeline(token=HF_TOKEN, device=DEVICE)
    diarize_segments, speaker_embeddings = diarize_model(
        audio,
        min_speakers=MIN_SPEAKERS,
        max_speakers=MAX_SPEAKERS,
        return_embeddings=True,
    )
    result = whisperx.assign_word_speakers(diarize_segments, result)

    cluster_ids = list(speaker_embeddings.keys()) if speaker_embeddings else []

    for segment in result["segments"]:
        segment.pop("words", None)
        segment["diarization_speaker"] = segment.get(SPEAKER, Identifier.DEFAULT_SPEAKER)

    logger.info("Saving to database")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        identification_results: list[tuple[str, float | None]] = []
        if speaker_embeddings:
            logger.info("Identifying speakers")
            identification_results = Identifier()(conn, speaker_embeddings)

        for segment in result["segments"]:
            orig = segment.get("diarization_speaker", Identifier.DEFAULT_SPEAKER)
            if identification_results and orig != Identifier.DEFAULT_SPEAKER:
                try:
                    idx = int(orig.split("_")[1])
                    name, confidence = identification_results[idx]
                except (ValueError, IndexError):
                    name, confidence = Identifier.DEFAULT_SPEAKER, None
                segment[SPEAKER] = name
                segment["confidence"] = confidence
            else:
                segment[SPEAKER] = Identifier.DEFAULT_SPEAKER
                segment["confidence"] = None

        meeting_id, speaker_name_to_id = save_meeting(conn, meeting_name, result["segments"])

        if speaker_embeddings and identification_results:
            cluster_to_speaker_id = {
                cid: (speaker_name_to_id.get(name) if name != Identifier.DEFAULT_SPEAKER else None)
                for cid, (name, _) in zip(cluster_ids, identification_results)
            }
            save_speaker_embeddings(conn, meeting_id, speaker_embeddings, cluster_to_speaker_id)


if __name__ == "__main__":
    import sys
    transcription(sys.argv[1])
