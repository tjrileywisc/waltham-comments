import numpy as np
from numpy.typing import NDArray
from typing import Dict, List
from collections import defaultdict
from sklearn.metrics.pairwise import cosine_similarity


class Identifier:
    SIMILARITY_THRESHOLD = 0.7
    DEFAULT_SPEAKER = "DEFAULT"

    def __call__(
        self,
        conn,
        speaker_embeddings: Dict[str, NDArray[np.float64]],
    ) -> List[tuple[str, float | None]]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.speaker_name, se.embedding_vec::text
                FROM speaker_embeddings se
                JOIN speakers s ON s.id = se.speaker_id
                WHERE se.speaker_id IS NOT NULL
                """
            )
            rows = cur.fetchall()

        if not rows:
            return [(self.DEFAULT_SPEAKER, None)] * len(speaker_embeddings)

        speaker_vecs: dict[str, list] = defaultdict(list)
        for name, emb_text in rows:
            speaker_vecs[name].append(
                [float(x) for x in emb_text.strip("[]").split(",")]
            )

        db_names = list(speaker_vecs.keys())
        db_embeddings = np.array([
            np.mean(speaker_vecs[name], axis=0) for name in db_names
        ])

        incoming = np.array(list(speaker_embeddings.values()))
        results = cosine_similarity(incoming, db_embeddings)
        best_idx = np.argmax(results, axis=1)
        best_scores = results[np.arange(len(results)), best_idx]

        return [
            (db_names[best_idx[i]], float(best_scores[i]))
            if best_scores[i] >= self.SIMILARITY_THRESHOLD
            else (self.DEFAULT_SPEAKER, None)
            for i in range(len(speaker_embeddings))
        ]
