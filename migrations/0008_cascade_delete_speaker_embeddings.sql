ALTER TABLE speaker_embeddings DROP CONSTRAINT speaker_embeddings_meeting_id_fkey;
ALTER TABLE speaker_embeddings ADD CONSTRAINT speaker_embeddings_meeting_id_fkey
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE;
