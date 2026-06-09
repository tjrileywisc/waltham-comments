$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

docker build -f "$root\transcription-service\Dockerfile" -t waltham-comments/transcription-service "$root"
docker build -f "$root\meeting-downloader\Dockerfile" -t waltham-comments/meeting-downloader "$root"
docker build -f "$root\embeddings-service\Dockerfile" -t waltham-comments/embeddings-service "$root"
docker build -f "$root\webapp\Dockerfile" -t waltham-comments/web "$root\webapp"
