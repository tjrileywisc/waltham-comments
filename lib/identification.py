# diarization just assigns speakers to segments of audio;
# to actually assign and identity across meetings, we need to get a persistent idea of a speaker embedding

import pickle
import numpy as np

from typing import Dict, List

from sklearn.metrics.pairwise import cosine_similarity

class Identifier:

    SIMILARITY_THRESHOLD = 0.7  # cosine similarity threshold for matching speakers
    DEFAULT_SPEAKER = "DEFAULT" # the speaker we'll use for anyone not expected to speak regularly

    def __init__(self):
        # load existing database
        with open("data/speaker_db.pkl", "rb") as f:
            self.database = pickle.load(f)

    def __call__(self, speaker_embeddings: Dict[str, List[float]]) -> List[str]:
        # use cosine similarity against a database of known speaker embeddings

        speaker_keys = list(speaker_embeddings.keys())
        embeddings_arr = np.array(
            list(
                speaker_embeddings.values()
            )
        )

        database_keys = list(self.database.keys())
        database_embeddings_arr = np.array(
            list(
                self.database.values()
            )
        )

        results = cosine_similarity(embeddings_arr, database_embeddings_arr)

        # get the column index of the best match to the database in each row,
        # replacing with the default if we didn't meet the threshold
        np.fill_diagonal(results, -np.inf)
        best = np.argmax(results, axis=1)

        max_scores = results[np.arange(len(results)), best]

        speakers = [
            (
                speaker_keys[i]
                if max_scores[i] >= Identifier.SIMILARITY_THRESHOLD
                else Identifier.DEFAULT_SPEAKER
            )
            for i in range(len(speaker_embeddings))
        ]

        return speakers
