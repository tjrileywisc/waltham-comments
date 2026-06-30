
VIDEO_DB: list[dict] = []

def get_video_ids() -> dict[str, int]:
    return {v["name"]: v["video_id"] for v in VIDEO_DB}