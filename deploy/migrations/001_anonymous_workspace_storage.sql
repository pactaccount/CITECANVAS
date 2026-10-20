-- Upgrade installations created from the initial Evid schema. These columns
-- turn internal project records into expiring anonymous browser workspaces.
ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours');

CREATE INDEX IF NOT EXISTS projects_expiry_idx ON projects (expires_at);

-- The UI record is stored as JSON so pages can be restored after a Render
-- restart, while searchable page text remains normalized in document_pages.
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS document_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
