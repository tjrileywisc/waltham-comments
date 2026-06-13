-- depends:

ALTER TABLE utterances
    ADD COLUMN ts_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;

CREATE INDEX ON utterances USING gin(ts_vector);
