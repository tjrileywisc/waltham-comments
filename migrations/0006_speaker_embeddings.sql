ALTER TABLE utterances ADD COLUMN diarization_speaker TEXT;
ALTER TABLE utterances ADD COLUMN confidence FLOAT;

CREATE TABLE speaker_embeddings (
    id                   SERIAL PRIMARY KEY,
    speaker_id           INT REFERENCES speakers(id),
    meeting_id           INT REFERENCES meetings(id) NOT NULL,
    diarization_speaker  TEXT NOT NULL,
    embedding            vector(192),
    is_canonical         BOOL NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (meeting_id, diarization_speaker)
);
