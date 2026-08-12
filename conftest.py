import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "meeting_downloader"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "embeddings_service"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "transcription_service"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "webapp"))
