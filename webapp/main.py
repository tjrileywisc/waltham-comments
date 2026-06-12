from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

import os
from lib.db import connect, get_transcript as db_get_transcript
from lib.search import do_search
from monitoring import setup_logging
from pathlib import Path
from contextlib import asynccontextmanager

logger = setup_logging("webapp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup; initializing resources.")

    with connect() as conn:
        conn.execute("SELECT 1")  # raises on connection failure, preventing startup
    logger.info("Database connection verified.")

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

app.mount(
    "/assets",
    StaticFiles(directory="./frontend/dist/assets"),
    name="static"
)

VIDEO_DB = list()


@app.get("/")
def root():
    return FileResponse("./frontend/dist/index.html")


@app.get("/api/transcript/{video_id}")
def get_transcript(video_id: int):
    name = VIDEO_DB[video_id]["name"]
    with connect() as conn:
        rows = db_get_transcript(conn, name)
    if not rows:
        raise HTTPException(404)
    return rows


@app.get("/api/video/{video_id}")
def get_video(video_id: int, request: Request):
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


@app.get("/api/videos")
def get_videos():
    return VIDEO_DB


@app.get("/about")
def about():
    return FileResponse("./frontend/dist/index.html")


@app.get("/api/search")
def search(query: str):
    return do_search(query)


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("./frontend/dist/index.html")
