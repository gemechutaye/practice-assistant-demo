CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS pa_source_vectors (
 workspace_id uuid NOT NULL, source_id text NOT NULL, content_hash text NOT NULL,
 embedding_model text NOT NULL, embedding vector(1536) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,source_id),
 FOREIGN KEY(workspace_id,source_id) REFERENCES pa_sources(workspace_id,id) ON DELETE CASCADE
);
ALTER TABLE pa_source_vectors ENABLE ROW LEVEL SECURITY;
