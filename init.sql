CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE utterances (
    id            SERIAL PRIMARY KEY,
    meeting_name  TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    start_time    FLOAT NOT NULL,
    end_time      FLOAT NOT NULL,
    text          TEXT NOT NULL,
    speaker       TEXT NOT NULL,
    UNIQUE (meeting_name, segment_index)
);

CREATE TABLE utterance_embeddings (
    utterance_id INTEGER PRIMARY KEY REFERENCES utterances(id) ON DELETE CASCADE,
    embedding    vector(384) NOT NULL
);

CREATE INDEX ON utterance_embeddings USING hnsw (embedding vector_cosine_ops);
