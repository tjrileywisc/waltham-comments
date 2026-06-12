# CPU Transcription Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the GPU-dependent transcription service with a CPU-only workflow, removing the NVIDIA CUDA runtime dependency and adding a `CPU_THREADS` tuning knob.

**Architecture:** Swap the CUDA base image for plain `ubuntu:24.04`, remove the CUDA-specific torch index, and update `transcription.py` to use `cpu` device with `int8` compute type and pass `cpu_threads` to WhisperX. Remove the GPU reservation from compose and raise CPU/memory limits in the k8s spec.

**Tech Stack:** WhisperX (faster-whisper / CTranslate2 backend), pyannote.audio, PyTorch (CPU), uv, Docker, Kubernetes

---

## File Map

| File | Action | What changes |
|---|---|---|
| `transcription-service/Dockerfile` | Modify | Base image only |
| `transcription-service/pyproject.toml` | Modify | Remove pytorch-cu128 index and uv.sources |
| `transcription-service/transcription.py` | Modify | Device, compute type, batch size, cpu_threads, remove CUDA cache calls |
| `compose.yml` | Modify | Remove GPU device reservation |
| `spec.yaml` | Modify | Raise transcription container CPU/memory limits |
| `CLAUDE.md` | Modify | Document `CPU_THREADS` env var |

---

### Task 1: Swap the Dockerfile base image

**Files:**
- Modify: `transcription-service/Dockerfile`

- [ ] **Step 1: Edit Dockerfile**

Replace the `FROM` line. The rest of the file is unchanged — uv handles Python 3.13 installation automatically via the `requires-python` constraint in `pyproject.toml`.

```dockerfile
FROM ubuntu:24.04

RUN apt update && apt install -y ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY transcription-service/pyproject.toml .
RUN uv sync --no-dev

COPY transcription-service/main.py transcription-service/transcription.py \
     transcription-service/identification.py .
COPY monitoring.py .

CMD ["uv", "run", "python", "main.py"]
```

- [ ] **Step 2: Verify the build succeeds**

```bash
docker build -f transcription-service/Dockerfile -t transcription-service:cpu-test .
```

Expected: build completes with no errors. uv will download Python 3.13 and install packages; this will take a few minutes on first run.

- [ ] **Step 3: Commit**

```bash
git add transcription-service/Dockerfile
git commit -m "chore(transcription): switch base image from CUDA to ubuntu:24.04"
```

---

### Task 2: Remove the CUDA torch dependency

**Files:**
- Modify: `transcription-service/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Remove the `[[tool.uv.index]]` block and the `[tool.uv.sources]` block. CPU torch is on PyPI — no extra index needed.

```toml
[project]
name = "transcription-service"
version = "0.1.0"
description = "Diarizes and transcribes Waltham public meeting audio"
requires-python = "==3.13.*"
dependencies = [
    "huggingface-hub>=0.36.0",
    "pandas>=2.0.0",
    "scikit-learn>=1.0.0",
    "tensorboard>=2.20.0",
    "torch>=2.8.0",
    "whisperx>=3.7.6",
]
```

- [ ] **Step 2: Verify resolution**

```bash
cd transcription-service
uv sync --no-dev
cd ..
```

Expected: uv resolves CPU torch from PyPI. No CUDA packages should appear in the output.

- [ ] **Step 3: Commit**

```bash
git add transcription-service/pyproject.toml
git commit -m "chore(transcription): replace CUDA torch with CPU torch from PyPI"
```

---

### Task 3: Update transcription.py for CPU execution

**Files:**
- Modify: `transcription-service/transcription.py`

- [ ] **Step 1: Edit transcription.py**

Replace the entire file content with the version below. Key changes:
- `DEVICE = "cpu"`
- `COMPUTE_TYPE = "int8"` (CTranslate2's fastest CPU path)
- `BATCH_SIZE = 1` (CPU batching gives little benefit)
- `CPU_THREADS` env var read; passed to `whisperx.load_model` as `cpu_threads`
- `torch.set_num_threads(CPU_THREADS)` covers pyannote and alignment model (which use PyTorch directly, not CTranslate2)
- `torch.cuda.empty_cache()` calls removed (CUDA-only API)
- `del model` / `del model_a` retained to free memory between pipeline steps

```python
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
        cpu_threads=CPU_THREADS,
    )

    audio = whisperx.load_audio(audio_file)
    result = model.transcribe(audio, batch_size=BATCH_SIZE)

    import gc; gc.collect(); del model

    logger.info("Aligning whisper output")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    import gc; gc.collect(); del model_a

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
```

- [ ] **Step 2: Verify the import is clean**

```bash
cd transcription-service
uv run python -c "import transcription; print('OK')"
cd ..
```

Expected: prints `OK` with no import errors.

- [ ] **Step 3: Commit**

```bash
git add transcription-service/transcription.py
git commit -m "feat(transcription): switch to CPU device with int8 compute and CPU_THREADS tuning"
```

---

### Task 4: Remove GPU reservation from compose.yml

**Files:**
- Modify: `compose.yml`

- [ ] **Step 1: Edit compose.yml**

Remove the `deploy` block from the `transcription-service` entry. The resulting service entry should look like:

```yaml
  transcription-service:
    build:
      context: .
      dockerfile: transcription-service/Dockerfile
    image: transcription-service
    env_file:
      - .env
    volumes:
      - C:/workspace/waltham-comments/audio:/app/audio
      - C:/workspace/waltham-comments/transcriptions:/app/transcriptions
      - C:/workspace/waltham-comments/data:/app/data
      - C:/workspace/waltham-comments/models:/app/models
```

- [ ] **Step 2: Validate compose config**

```bash
docker compose config --quiet
```

Expected: exits 0 with no errors.

- [ ] **Step 3: Commit**

```bash
git add compose.yml
git commit -m "chore(compose): remove GPU device reservation from transcription service"
```

---

### Task 5: Update k8s resource limits in spec.yaml

**Files:**
- Modify: `spec.yaml`

- [ ] **Step 1: Edit spec.yaml**

Raise the transcription-service container's resource requests and limits to values appropriate for CPU inference of the `large-v2` model (~3 GB weights, plus runtime overhead). Leave all other containers unchanged.

Find this block in `spec.yaml`:

```yaml
      - name: transcription-service
        image: docker.io/library/transcription-service:latest
        imagePullPolicy: Never
        envFrom:
        - secretRef:
            name: waltham-comments-env
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "1000m"
```

Replace the `resources` section with:

```yaml
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"
          limits:
            memory: "16Gi"
            cpu: "4"
```

- [ ] **Step 2: Validate the manifest**

```bash
kubectl apply --dry-run=client -f spec.yaml
```

Expected: `deployment.apps/waltham-comments-deployment configured (dry run)` and `service/waltham-comments-service configured (dry run)`.

(If `kubectl` is not available locally, skip this step — the manifest will be validated at deploy time.)

- [ ] **Step 3: Commit**

```bash
git add spec.yaml
git commit -m "chore(k8s): raise transcription service CPU/memory limits for CPU inference"
```

---

### Task 6: Document CPU_THREADS env var in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Edit CLAUDE.md**

Find this line:

```
Optional env vars: `POLL_INTERVAL_SECONDS` (default 3600), `MIN_SPEAKERS` (default 5), `MAX_SPEAKERS` (default 18), `MODELS_DIR` (default `models`).
```

Replace with:

```
Optional env vars: `POLL_INTERVAL_SECONDS` (default 3600), `MIN_SPEAKERS` (default 5), `MAX_SPEAKERS` (default 18), `MODELS_DIR` (default `models`), `CPU_THREADS` (default 0 = all cores).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document CPU_THREADS env var"
```

---

### Task 7: Smoke test the full container

- [ ] **Step 1: Build the updated image**

```bash
docker build -f transcription-service/Dockerfile -t transcription-service:latest .
```

Expected: build completes successfully.

- [ ] **Step 2: Run a transcription against a sample WAV**

Place a short WAV file (even 30 seconds of speech works) at `audio/test-smoke.wav`, then:

```powershell
docker run --rm `
  -e HF_TOKEN="<your token>" `
  -e CPU_THREADS=4 `
  -v "C:/workspace/waltham-comments/audio:/app/audio" `
  -v "C:/workspace/waltham-comments/transcriptions:/app/transcriptions" `
  -v "C:/workspace/waltham-comments/data:/app/data" `
  -v "C:/workspace/waltham-comments/models:/app/models" `
  transcription-service:latest `
  uv run python transcription.py test-smoke
```

Expected log output (in order):
1. `Aligning whisper output`
2. `Assigning speaker labels`
3. `Generating speaker database` (first run) or `Matching identifying existing speakers`

Expected file: `transcriptions/test-smoke.csv` containing columns `id`, `start`, `end`, `text`, `speaker`.

- [ ] **Step 3: Verify CSV content**

```powershell
Get-Content transcriptions/test-smoke.csv -TotalCount 5
```

Expected: a header row followed by timestamped transcript segments with speaker labels.
