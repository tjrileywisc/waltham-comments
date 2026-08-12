from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

import os
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel

from yoyo import get_backend, read_migrations

from lib.db import connect, readonly_connect, get_transcript as db_get_transcript, init_pools, close_pools
from lib.admin import (
    get_admin, get_meetings, get_clusters, get_todo_labeling_tasks,
    label_cluster, set_canonical, get_speakers,
    enqueue_relabel_job,
)
from lib.search import do_search
from lib.chat import run_chat
from lib import state
from monitoring import setup_logging
import requests as http_requests

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

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    query: str

class ChatSource(BaseModel):
    meeting_name: str
    speaker_name: str
    video_id: int | None
    start: float
    text: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup; initializing resources.")
    init_pools()

    db_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    backend = get_backend(db_url)
    migrations = read_migrations("./migrations")
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))
    logger.info("Database migrations applied.")

    files = os.listdir(os.environ["DATA_DIR"] + "/videos")
    state.VIDEO_DB = [
        {"video_id": i, "name": f.replace(".mp4", "")}
        for i, f in enumerate(files)
    ]

    yield

    close_pools()


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


@app.get("/api/transcript/{video_id}")
def get_transcript(video_id: int):
    name = state.VIDEO_DB[video_id]["name"]
    with connect() as conn:
        rows = db_get_transcript(conn, name)
    if not rows:
        raise HTTPException(404)
    return rows


@app.get("/api/video/{video_id}")
def get_video(video_id: int, request: Request) -> StreamingResponse:
    path = os.environ['DATA_DIR'] + "/videos/" + state.VIDEO_DB[video_id]["name"] + ".mp4"

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
    return state.VIDEO_DB


@app.get("/about")
def about():
    return FileResponse("./frontend/dist/index.html")

@app.get("/healthcheck")
def healthcheck() -> int:
    return 200


@app.get("/api/search", response_model=list[SearchResult])
def search(query: str) -> list[SearchResult]:
    results = do_search(query)
    name_to_id = state.get_video_ids()
    matching = []
    for r in results:
        video_id = name_to_id.get(r["meeting_name"])
        if video_id is not None:
            # we might not have the video locally
            r["video_id"] = video_id
            matching.append(r)
    return matching


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    """Accept a query and conversation history, return an LLM answer with cited sources."""
    try:
        result = await run_chat(
            query=body.query,
            prev_messages=[m.model_dump() for m in body.messages],
        )
    except http_requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Chat service is currently unavailable.")
    except http_requests.exceptions.HTTPError:
        raise HTTPException(status_code=502, detail="Chat service returned an error.")

    name_to_id = state.get_video_ids()
    sources = [
        ChatSource(
            meeting_name=u["meeting_name"],
            speaker_name=u["speaker_name"],
            video_id=name_to_id.get(u["meeting_name"]),
            start=u["start"],
            text=u["text"],
        )
        for u in result["utterances"]
    ]
    return ChatResponse(answer=result["answer"], sources=sources)


@app.get("/api/admin/meetings")
def admin_meetings(_=Depends(get_admin)):
    name_to_video_id = state.get_video_ids()
    with connect() as conn:
        meetings = get_meetings(conn)
    for m in meetings:
        m["video_id"] = name_to_video_id.get(m["meeting_name"])
    return meetings


@app.get("/api/admin/meetings/{meeting_id}/clusters")
def admin_meeting_clusters(meeting_id: int, _=Depends(get_admin)):
    name_to_video_id = state.get_video_ids()
    with connect() as conn:
        clusters = get_clusters(conn, meeting_id)
        with conn.cursor() as cur:
            cur.execute("SELECT meeting_name FROM meetings WHERE id = %s", (meeting_id,))
            row = cur.fetchone()
    meeting_name = row[0] if row else None
    return {"video_id": name_to_video_id.get(meeting_name), "clusters": clusters}


@app.post("/api/admin/meetings/{meeting_id}/clusters/{cluster}/label")
def admin_label_cluster(meeting_id: int, cluster: str, body: LabelRequest, _=Depends(get_admin)):
    with connect() as conn:
        label_cluster(conn, meeting_id, cluster, body.speaker_name)
    return {"ok": True}

@app.get("/api/meetings/unlabeled_count")
def total_unlabled_count():
    with readonly_connect() as conn:
        return {"count": get_todo_labeling_tasks(conn)}
        

@app.post("/api/admin/meetings/{meeting_id}/relabel")
def admin_relabel_meeting(meeting_id: int, _=Depends(get_admin)):
    with connect() as conn:
        job_id = enqueue_relabel_job(conn, meeting_id)
    return {"job_id": job_id}


@app.post("/api/admin/speaker-embeddings/{embedding_id}/canonical")
def admin_set_canonical(embedding_id: int, _=Depends(get_admin)):
    with connect() as conn:
        set_canonical(conn, embedding_id)
    return {"ok": True}


@app.get("/api/admin/speakers")
def admin_speakers(_=Depends(get_admin)):
    with connect() as conn:
        return get_speakers(conn)


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("./frontend/dist/index.html")
