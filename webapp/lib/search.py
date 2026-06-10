

def do_search(query: str) -> list:
    # TODO: create embedding on `query` and search vector db
    
    return [
        {
            "video_id": 0,
            "video_title": "Mock video", 
            "start": 12.4,
            "text": f"This is a placeholder result for: {query}"
        }
    ]
