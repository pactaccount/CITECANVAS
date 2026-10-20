"""R2 and PostgreSQL backing store for anonymous Evid browser workspaces.

The web server keeps a short-lived local cache for rendering and model calls.
This module is the durable source of truth when ``EVID_STORAGE_BACKEND=r2_neon``:
PDFs and page images live in R2, while the document catalog lives in PostgreSQL.
"""

import io
import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.src.production_config import ProductionStorageConfig
from backend.src.observability import span


class PersistentWorkspaceStore:
    """Idempotent durable storage for one anonymous browser workspace."""

    def __init__(self, config=None, *, s3_client=None, connect=None, ttl_hours=None):
        self.config = config or ProductionStorageConfig.from_env()
        if s3_client is None:
            import boto3
            s3_client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                region_name=self.config.region,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
        self.s3 = s3_client
        if connect is None:
            import psycopg
            connect = lambda: psycopg.connect(self.config.database_url)
        self.connect = connect
        self.ttl_hours = int(ttl_hours if ttl_hours is not None else os.getenv("EVID_WORKSPACE_TTL_HOURS", "24"))
        if self.ttl_hours < 1:
            raise ValueError("EVID_WORKSPACE_TTL_HOURS must be at least 1.")

    @staticmethod
    def workspace_uuid(workspace_id):
        return uuid.UUID(hex=workspace_id)

    @staticmethod
    def document_uuid(workspace_id, doc_id):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"evid:{workspace_id}:{doc_id}")

    def _expiry(self):
        return datetime.now(timezone.utc) + timedelta(hours=self.ttl_hours)

    def touch_workspace(self, workspace_id):
        """Create or extend a workspace without exposing a user identity."""
        workspace = self.workspace_uuid(workspace_id)
        expiry = self._expiry()
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO projects (id, public_slug, last_active_at, expires_at)
                   VALUES (%s, %s, now(), %s)
                   ON CONFLICT (id) DO UPDATE SET
                       last_active_at = EXCLUDED.last_active_at,
                       expires_at = EXCLUDED.expires_at,
                       updated_at = now()""",
                (workspace, workspace_id, expiry),
            )

    def _record(self, workspace_id, doc_id):
        workspace = self.workspace_uuid(workspace_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT d.document_metadata
                   FROM documents d
                   WHERE d.project_id = %s AND d.content_sha256 = %s AND d.status = 'ready'""",
                (workspace, doc_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        value = row[0]
        return value if isinstance(value, dict) else json.loads(value)

    def documents(self, workspace_id):
        self.touch_workspace(workspace_id)
        workspace = self.workspace_uuid(workspace_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT d.document_metadata
                   FROM documents d
                   WHERE d.project_id = %s AND d.status = 'ready'
                   ORDER BY d.created_at""",
                (workspace,),
            )
            rows = cur.fetchall()
        records = []
        for (value,) in rows:
            try:
                records.append(value if isinstance(value, dict) else json.loads(value))
            except (TypeError, ValueError):
                continue
        return records

    def save_document(self, workspace_id, record, source_dir):
        """Persist a rendered document. Repeating this operation is safe.

        Objects use deterministic keys and the database uniqueness constraint is
        per workspace plus content hash, so retries cannot create duplicates.
        """
        self.touch_workspace(workspace_id)
        existing = self._record(workspace_id, record["docId"])
        if existing:
            return {**existing, "duplicate": True}

        workspace = self.workspace_uuid(workspace_id)
        document = self.document_uuid(workspace_id, record["docId"])
        source_dir = Path(source_dir)
        original_key = self.config.document_key(workspace_id, record["docId"])
        page_prefix = f"workspaces/{workspace_id}/documents/{record['docId']}/pages/"
        uploaded_keys = []
        try:
            self._put_file(original_key, source_dir / "source.pdf", "application/pdf")
            uploaded_keys.append(original_key)
            for page in range(1, int(record["totalPages"]) + 1):
                key = self.config.page_key(workspace_id, record["docId"], page)
                self._put_file(key, source_dir / f"page_{page}.png", "image/png")
                uploaded_keys.append(key)
            metadata = json.dumps(record, ensure_ascii=False)
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO documents
                         (id, project_id, original_filename, content_sha256, original_object_key,
                          page_prefix, byte_size, total_pages, status, document_metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ready', %s::jsonb)
                       ON CONFLICT (project_id, content_sha256) DO UPDATE SET
                          updated_at = now(), status = 'ready', failure_reason = NULL,
                          document_metadata = EXCLUDED.document_metadata
                       RETURNING id""",
                    (document, workspace, record["filename"], record["docId"], original_key,
                     page_prefix, (source_dir / "source.pdf").stat().st_size,
                     record["totalPages"], metadata),
                )
                document = cur.fetchone()[0]
                cur.execute("DELETE FROM document_pages WHERE document_id = %s", (document,))
                for page in range(1, int(record["totalPages"]) + 1):
                    text = record.get("pageText", {}).get(str(page), record.get("pageText", {}).get(page, ""))
                    cur.execute(
                        """INSERT INTO document_pages (document_id, page_number, image_object_key, extracted_text)
                           VALUES (%s, %s, %s, %s)""",
                        (document, page, self.config.page_key(workspace_id, record["docId"], page), text),
                    )
            return record
        except Exception:
            # The database row is written only after every required object is
            # present. A failed upload therefore remains invisible and can be
            # retried. Remove its partial objects where possible.
            self._delete_keys(uploaded_keys)
            raise

    def hydrate_document(self, workspace_id, record, destination):
        """Restore one durable document into the local runtime cache."""
        destination = Path(destination) / record["docId"]
        source = destination / "source.pdf"
        expected_page = destination / "page_1.png"
        if source.is_file() and expected_page.is_file():
            return destination
        destination.mkdir(parents=True, exist_ok=True)
        self._download(self.config.document_key(workspace_id, record["docId"]), source)
        for page in range(1, int(record["totalPages"]) + 1):
            self._download(self.config.page_key(workspace_id, record["docId"], page), destination / f"page_{page}.png")
        (destination / "document.json").write_text(json.dumps(record, ensure_ascii=False))
        return destination

    def page_bytes(self, workspace_id, doc_id, page):
        return self.s3.get_object(
            Bucket=self.config.bucket,
            Key=self.config.page_key(workspace_id, doc_id, page),
        )["Body"].read()

    def clear_workspace(self, workspace_id):
        """Delete durable objects and catalog rows for one browser workspace."""
        workspace = self.workspace_uuid(workspace_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT original_object_key, page_prefix
                   FROM documents WHERE project_id = %s""", (workspace,)
            )
            objects = cur.fetchall()
            cur.execute("DELETE FROM projects WHERE id = %s", (workspace,))
        keys = []
        for original_key, page_prefix in objects:
            keys.append(original_key)
            keys.extend(self._list_keys(page_prefix))
        self._delete_keys(keys)

    def cleanup_expired(self):
        """Remove inactive anonymous workspaces after the configured TTL."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT public_slug FROM projects WHERE expires_at < now()")
            workspaces = [row[0] for row in cur.fetchall()]
        for workspace_id in workspaces:
            self.clear_workspace(workspace_id)
        return workspaces

    def _put_file(self, key, path, content_type):
        with span("evid.r2.put", {"evid.object_type": content_type}):
            with Path(path).open("rb") as source:
                self.s3.put_object(Bucket=self.config.bucket, Key=key, Body=source, ContentType=content_type)

    def _download(self, key, destination):
        with span("evid.r2.get"):
            payload = self.s3.get_object(Bucket=self.config.bucket, Key=key)["Body"].read()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def _list_keys(self, prefix):
        keys, token = [], None
        while True:
            kwargs = {"Bucket": self.config.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.s3.list_objects_v2(**kwargs)
            keys.extend(item["Key"] for item in page.get("Contents", []))
            if not page.get("IsTruncated"):
                return keys
            token = page["NextContinuationToken"]

    def _delete_keys(self, keys):
        for offset in range(0, len(keys), 1000):
            batch = list(dict.fromkeys(keys[offset:offset + 1000]))
            if batch:
                self.s3.delete_objects(Bucket=self.config.bucket, Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True})
