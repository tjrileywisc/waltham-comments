# CPU Transcription Service Design

Date: 2026-06-10

## Goal

Switch the transcription service from GPU (CUDA) to CPU execution. The primary motivation is removing the NVIDIA GPU dependency so the service can run in environments without GPU hardware (e.g., the existing k8s deployment via `spec.yaml`).

## Scope

Five files change. No new abstractions, no new services, no model changes.

## Architecture

No structural change — the four-service pipeline (downloader → transcription → web + embeddings) remains identical. The transcription service changes only internally and in its deployment configuration.

## Components

### Dockerfile

Replace:
```
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
```
With:
```
FROM ubuntu:24.04
```

No additional Python install step needed. The current Dockerfile already uses uv, which manages its own Python installation — `uv sync` will download Python 3.13 automatically based on the `requires-python = "==3.13.*"` constraint in `pyproject.toml`.

### pyproject.toml

Remove the `pytorch-cu128` index and the `[tool.uv.sources]` override that pins torch to that index. CPU torch is available on PyPI directly — no extra index needed.

### transcription.py

| Setting | Current | New |
|---|---|---|
| `DEVICE` | `"cuda"` | `"cpu"` |
| `COMPUTE_TYPE` | `"float16"` | `"int8"` (CTranslate2's fastest CPU path) |
| `BATCH_SIZE` | `8` | `1` (CPU batching provides little benefit) |
| `cpu_threads` | not set | new param, read from `CPU_THREADS` env var, default `0` (all cores) |
| CUDA cache clearing | `torch.cuda.empty_cache()` x2 | removed |

`cpu_threads` is passed to `whisperx.load_model` and `whisperx.load_align_model`. The `DiarizationPipeline` (pyannote) uses PyTorch threading which honours the same env var implicitly.

`CPU_THREADS` follows the existing env var pattern (`MIN_SPEAKERS`, `MAX_SPEAKERS`, etc.) and is documented in CLAUDE.md's "Optional env vars" list.

### compose.yml

Remove the `deploy.resources.reservations.devices` block from the `transcription-service` entry. No other compose changes.

### spec.yaml

The transcription-service container currently has placeholder CPU/memory limits (256Mi / 500m) identical to other services. Raise these to realistic values for CPU inference of a large-v2 model:

- Memory request/limit: `8Gi` / `16Gi` (large-v2 model weights alone are ~3 GB; runtime overhead adds more)
- CPU request/limit: `2` / `4` (leaving headroom for other containers in the pod)

## Error Handling

No new error handling needed. Existing behaviour — skipping files that already have a `.csv` transcription, logging failures, and continuing the poll loop — is unchanged.

## Testing

Manual: run the service locally (`uv run python main.py`) against a sample WAV file and confirm a `.csv` is produced. Check log output for the "Transcribing", "Aligning", "Assigning speaker labels" messages.

Automated: no unit tests currently exist for the transcription pipeline; out of scope for this change.

## Open Questions

- `BATCH_SIZE=1` is conservative. After initial testing, increasing to 4–8 may improve throughput if memory allows.
- `cpu_threads=0` (all cores) may contend with other containers in the same pod. Tuning `CPU_THREADS` via the k8s env can be done post-deployment.
