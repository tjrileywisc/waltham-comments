from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

import os
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel

from yoyo import get_backend, read_migrations

from lib.db import connect, get_transcript as db_get_transcript
from lib.admin import (
    get_admin, get_meetings, get_clusters,
    label_cluster, set_canonical, get_speakers,
)
from lib.search import do_search
from monitoring import setup_logging

logger = setup_logging("webapp")

class VideoSummary(BaseModel):
    video_id: int
    name: str
class SearchResult(BaseModel):
    video_id: int
    meeting_name: str
    start: float
    text: str
    score: float

class LabelRequest(BaseModel):
    speaker_name: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup; initializing resources.")

    db_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    backend = get_backend(db_url)
    migrations = read_migrations("./migrations")
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
    logger.info("Database migrations applied.")

    global VIDEO_DB
    files = os.listdir(os.environ["DATA_DIR"] + "/videos")
    VIDEO_DB = [
        {"video_id": i, "name": f.replace(".mp4", "")}
        for i, f in enumerate(files)
    ]

    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if Path("./frontend/dist/assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory="./frontend/dist/assets"),
        name="static"
    )

VIDEO_DB = list()

@app.get("/api/transcript/{video_id}")
def get_transcript(video_id: int):
    name = VIDEO_DB[video_id]["name"]
    with connect() as conn:
        rows = db_get_transcript(conn, name)
    if not rows:
        raise HTTPException(404)
    return rows


@app.get("/api/video/{video_id}")
def get_video(video_id: int, request: Request) -> StreamingResponse:
    path = os.environ['DATA_DIR'] + "/videos/" + VIDEO_DB[video_id]["name"] + ".mp4"

    video_path = Path(path)
    if not video_path.exists:
        raise HTTPException(404)

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        start, end = range_header.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else file_size - 1
    else:
        start, end = 0, file_size - 1

    def iterfile():
        with open(path, "rb") as f:
            f.seek(start)
            yield f.read(end - start + 1)

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }

    return StreamingResponse(
        iterfile(),
        status_code=206 if range_header else 200,
        headers=headers,
        media_type="video/mp4",
    )


@app.get("/api/videos", response_model=list[VideoSummary])
def get_videos():
    return VIDEO_DB


@app.get("/about")
def about():
    return FileResponse("./frontend/dist/index.html")

@app.get("/healthcheck")
def healthcheck() -> int:
    return 200


@app.get("/api/search", response_model=list[SearchResult])
def search(query: str):
    results = do_search(query)
    name_to_id = {v["name"]: v["video_id"] for v in VIDEO_DB}
    matching = []
    for r in results:
        video_id = name_to_id.get(r["meeting_name"])
        if video_id is not None:
            # we might not have the video locally
            r["video_id"] = video_id
            matching.append(r)
    return matching


@app.get("/admin/meetings")
def admin_meetings(_=Depends(get_admin)):
    with connect() as conn:
        return get_meetings(conn)


@app.get("/admin/meetings/{meeting_id}/clusters")
def admin_meeting_clusters(meeting_id: int, _=Depends(get_admin)):
    with connect() as conn:
        return get_clusters(conn, meeting_id)


@app.post("/admin/meetings/{meeting_id}/clusters/{cluster}/label")
def admin_label_cluster(meeting_id: int, cluster: str, body: LabelRequest, _=Depends(get_admin)):
    with connect() as conn:
        label_cluster(conn, meeting_id, cluster, body.speaker_name)
    return {"ok": True}


@app.post("/admin/speaker-embeddings/{embedding_id}/canonical")
def admin_set_canonical(embedding_id: int, _=Depends(get_admin)):
    with connect() as conn:
        set_canonical(conn, embedding_id)
    return {"ok": True}


@app.get("/admin/speakers")
def admin_speakers(_=Depends(get_admin)):
    with connect() as conn:
        return get_speakers(conn)


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("./frontend/dist/index.html")
