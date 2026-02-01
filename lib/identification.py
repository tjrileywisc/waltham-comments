
# diarization just assigns speakers to segments of audio;
# to actually assign and identity across meetings, we need to get a persistent idea of a speaker embedding

import pickle
import os

class Identifier:
    def __init__(self):
        pass
    
    def __call__(self, speaker_embeddings):
        # use cosine similarity against a database of known speaker embeddings
        pass
    
    @staticmethod
    def save_database(db: dict, path: str):

        os.makedirs("data", exist_ok=True)
        
        with open(path, "wb") as f:
            pickle.dump(db, f)