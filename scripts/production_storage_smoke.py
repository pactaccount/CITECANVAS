#!/usr/bin/env python3
"""Controlled R2 + Neon round-trip, with cleanup of its temporary workspace.

This intentionally does not call NVIDIA or Qdrant. It verifies only the
durable storage path used after a hosted process restart.
"""

import importlib.util
import os
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["EVID_STORAGE_BACKEND"] = "r2_neon"
spec = importlib.util.spec_from_file_location("evid_server", ROOT / "scripts" / "serve.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def main():
    workspace_id = uuid.uuid4().hex
    workspace_dir = server.workspace_storage_dir(workspace_id)
    try:
        record = server.ingest_uploaded_pdf(
            (ROOT / "fixtures" / "evaluation" / "upload_beta.pdf").read_bytes(),
            "storage-smoke.pdf",
            workspace_id,
        )
        records = server.saved_documents(workspace_id)
        assert [item["docId"] for item in records] == [record["docId"]]
        shutil.rmtree(workspace_dir)
        server.WORKSPACE_RUNTIMES.pop(workspace_id, None)
        server.runtime(workspace_id)
        assert (workspace_dir / record["docId"] / "source.pdf").is_file()
        assert (workspace_dir / record["docId"] / "page_1.png").is_file()
        assert server.persistent_store().page_bytes(workspace_id, record["docId"], 1).startswith(b"\x89PNG")
        print("Production storage smoke: passed")
    finally:
        try:
            server.persistent_store().clear_workspace(workspace_id)
        finally:
            shutil.rmtree(workspace_dir, ignore_errors=True)
            server.WORKSPACE_RUNTIMES.pop(workspace_id, None)


if __name__ == "__main__":
    main()
