-- Evid uses anonymous browser workspaces, not user accounts. Every durable
-- record is scoped to its opaque workspace token and is deleted after expiry.
CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY,
  public_slug TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours')
);
CREATE INDEX IF NOT EXISTS projects_expiry_idx ON projects (expires_at);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  original_object_key TEXT NOT NULL UNIQUE,
  page_prefix TEXT NOT NULL,
  byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
  total_pages INTEGER,
  status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
  failure_reason TEXT,
  document_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS document_pages (
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number > 0),
  image_object_key TEXT NOT NULL UNIQUE,
  extracted_text TEXT,
  PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS document_sections (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  document_type TEXT NOT NULL,
  start_page INTEGER NOT NULL,
  end_page INTEGER NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'imported'
);

CREATE TABLE IF NOT EXISTS processing_jobs (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
