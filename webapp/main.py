from fastapi import FastAPI, HTTPException, Request, logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

import os
import csv
from lib.search import do_search
from pathlib import Path
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.logger.info("Startup; initializing resources.")

    global VIDEO_DB
    files = os.listdir(os.environ["DATA_DIR"] + "/videos")
    VIDEO_DB = [
        {"video_id": i, "name": f.replace(".mp4", "")}
        for i, f in enumerate(files)
    ]

    yield
    
    # shutdown


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
    
    path = Path(f"{os.environ['DATA_DIR']}/transcriptions/{name}.csv")
    
    if not path.exists():
        logger.logger.error(f"can't find {path}")
        raise HTTPException(404)
    
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [
            {
                "id": int(row["id"]),
                "start": float(row["start"]),
                "end": float(row["end"]),
                "text": row["text"],
                "speaker": row["speaker"],
            }
            for row in reader
        ]

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

# search functions

@app.get("/api/search")
def search(query: str):
    results = do_search(query)
    return results

# catch-all route
@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("./frontend/dist/index.html")