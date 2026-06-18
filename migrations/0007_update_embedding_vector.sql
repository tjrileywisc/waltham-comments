
ALTER TABLE speaker_embeddings ADD COLUMN embedding_vec vector(256);
ALTER TABLE speaker_embeddings DROP COLUMN embedding;