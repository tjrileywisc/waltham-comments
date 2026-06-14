

CREATE TABLE meetings (
    id            SERIAL PRIMARY KEY,
    meeting_name  TEXT NOT NULL,
    meeting_type  TEXT NOT NULL,
    meeting_date  DATE NOT NULL,
    meeting_part  SMALLINT
);

CREATE TABLE speakers (
    id          SERIAL PRIMARY KEY,
    speaker_name TEXT,
    speaker_role TEXT
);

ALTER TABLE utterances
    ADD COLUMN speaker_id INT REFERENCES speakers(id),
    ADD COLUMN meeting_id INT REFERENCES meetings(id)
;