# diarization just assigns speakers to segments of audio;
# to actually assign and identity across meetings, we need to get a persistent idea of a speaker embedding

import pickle
import numpy as np
from numpy.typing import NDArray

from typing import Dict, List

from sklearn.metrics.pairwise import cosine_similarity

class Identifier:

    DB_PATH = "data/speaker_db.pkl"

    # cosine similarity threshold for matching speakers
    SIMILARITY_THRESHOLD = 0.7
    # the speaker we'll use for anyone not expected to speak regularly
    DEFAULT_SPEAKER = "DEFAULT"

    def __init__(self, database: Dict[str, NDArray[np.float64]]=dict()):
        """Identifier constructor

        Args:
            database (Dict[str, NDArray[np.float64]], optional): a database to pass. If not provided, the default will be loaded from the filesystem.
        """
        if not database:
            self.load_db()
        else:
            self.database = database

    @staticmethod
    def save_db(speaker_embeddings: Dict[str, NDArray[np.float64]]):
        pickle.dump(speaker_embeddings, open(Identifier.DB_PATH, "wb"))

    def load_db(self):
        # load existing database
        with open(Identifier.DB_PATH, "rb") as f:
            self.database = pickle.load(f)

    def __call__(self, speaker_embeddings: Dict[str, NDArray[np.float64]]) -> List[str]:
        """Use cosine similarity to match a known speaker name against embedding vectors
        found in the incoming data

        Args:
            speaker_embeddings (Dict[str, NDArray[np.float64]]): incoming data

        Returns:
            List[str]: a list of speakers. Poor quality matches will be assigned
            the default speaker name.
        """

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

        # results shape should be (examples x known speakers)
        results = cosine_similarity(embeddings_arr, database_embeddings_arr)

        # get the column index of the best match to the database in each row,
        # replacing with the default if we didn't meet the threshold
        best = np.argmax(results, axis=1)

        max_scores = results[np.arange(len(results)), best]

        speakers = [
            (
                database_keys[i]
                if max_scores[i] >= Identifier.SIMILARITY_THRESHOLD
                else Identifier.DEFAULT_SPEAKER
            )
            for i in range(len(speaker_embeddings))
        ]

        return speakers
