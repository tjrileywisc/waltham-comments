ALTER TABLE utterances
    ALTER COLUMN meeting_id SET NOT NULL,
    ALTER COLUMN speaker_id SET NOT NULL,
    DROP CONSTRAINT utterances_meeting_name_segment_index_key,
    DROP COLUMN meeting_name,
    DROP COLUMN meeting_type,
    DROP COLUMN speaker;

ALTER TABLE utterances
    ADD CONSTRAINT utterances_meeting_id_segment_index_key UNIQUE (meeting_id, segment_index);
