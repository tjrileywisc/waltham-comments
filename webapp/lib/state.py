
VIDEO_DB: list[dict] = []

def get_video_ids() -> dict[str, int]:
    """Get a mapping of video name to id"""
    return {v["name"]: v["video_id"] for v in VIDEO_DB}