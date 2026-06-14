ALTER TABLE utterances DROP CONSTRAINT utterances_meeting_id_fkey;
ALTER TABLE utterances ADD CONSTRAINT utterances_meeting_id_fkey
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE;
