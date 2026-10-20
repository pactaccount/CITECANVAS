#!/usr/bin/env python3 -I
"""Local CiteCanvas UI and PDF upload API with persistent, source-scoped records."""

import hashlib
import http.server
import json
import os
import re
import shutil
import sys
import threading
import uuid
from http.cookies import SimpleCookie
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PORT = int(os.getenv("PORT", "8000"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"
STORAGE_DIR = Path(os.getenv("EVID_LOCAL_STORAGE_DIR", PROJECT_ROOT / "storage" / "pages"))
PAGES_PUBLIC_DIR = FRONTEND_DIR / "public" / "pages"
MAX_FILE_BYTES = 25 * 1024 * 1024
WORKSPACE_COOKIE = "evid_workspace"
WORKSPACE_ID_RE = re.compile(r"[a-f0-9]{32}")
# PDFium is not thread-safe. Keep native rendering/text extraction serialized
# while HTTP threads can still serve page images and the app during an upload.
INGESTION_LOCK = threading.Lock()

from backend.src.runtime import Runtime, load_environment
from backend.src.persistent_store import PersistentWorkspaceStore
from backend.src.observability import configure_observability, span
load_environment(PROJECT_ROOT)
configure_observability()
RUNTIME = None
WORKSPACE_RUNTIMES = {}
PERSISTENT_STORE = None
LAST_EXPIRY_CLEANUP = 0.0


def persistent_store():
    """Return the durable production store only when explicitly enabled.

    Keeping the default local makes development and the staged rollout
    reversible. Render enables this with EVID_STORAGE_BACKEND=r2_neon.
    """
    global PERSISTENT_STORE
    if os.getenv("EVID_STORAGE_BACKEND", "local").lower() != "r2_neon":
        return None
    if PERSISTENT_STORE is None:
        PERSISTENT_STORE = PersistentWorkspaceStore()
    return PERSISTENT_STORE


def prune_expired_workspaces():
    """Bound expiry work so a normal request never triggers it repeatedly."""
    global LAST_EXPIRY_CLEANUP
    store = persistent_store()
    if not store:
        return
    import time
    if time.monotonic() - LAST_EXPIRY_CLEANUP >= 300:
        expired = store.cleanup_expired()
        for workspace_id in expired:
            active = WORKSPACE_RUNTIMES.pop(workspace_id, None)
            if active:
                active.clear_workspace_cache()
        LAST_EXPIRY_CLEANUP = time.monotonic()


def workspace_storage_dir(workspace_id):
    """Return the only on-disk location visible to an anonymous workspace."""
    if not isinstance(workspace_id, str) or not WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise ValueError("Invalid workspace.")
    return STORAGE_DIR / "workspaces" / workspace_id


def runtime(workspace_id=None):
    """Keep retrieval state isolated as well as source records.

    The no-argument branch is retained for small local unit tests and legacy
    uploads. HTTP requests always pass an anonymous workspace ID.
    """
    global RUNTIME
    if workspace_id is None:
        if RUNTIME is None:
            RUNTIME = Runtime(STORAGE_DIR, saved_documents, INGESTION_LOCK)
        return RUNTIME
    if workspace_id not in WORKSPACE_RUNTIMES:
        storage = workspace_storage_dir(workspace_id)
        store = persistent_store()
        if store:
            # The model runtime deliberately reads only the local cache. On a
            # fresh Render instance, rebuild that cache from R2 before it can
            # answer; no uploaded source depends on Render's filesystem.
            for record in store.documents(workspace_id):
                store.hydrate_document(workspace_id, record, storage)
        WORKSPACE_RUNTIMES[workspace_id] = Runtime(
            storage,
            lambda: saved_documents(workspace_id),
            INGESTION_LOCK,
        )
    return WORKSPACE_RUNTIMES[workspace_id]



def whole_file_section(doc_id, filename, pages):
    return [{
        "subdocId": f"{doc_id}_sub_1",
        "parentFileId": doc_id,
        "title": filename,
        "docType": "Document",
        "startPage": 1,
        "endPage": pages,
        "pageCount": pages,
        "scopedIdentifiers": {},
        "metadataStatus": "User-uploaded",
    }]


def saved_documents(workspace_id=None):
    """Recover old rendered uploads as well as new complete document records.

    Legacy uploads have page images but no stored PDF/text. Never substitute
    the demo's text for that missing native text.
    """
    store = persistent_store() if workspace_id is not None else None
    if store:
        prune_expired_workspaces()
        return store.documents(workspace_id)
    records = []
    storage_dir = STORAGE_DIR if workspace_id is None else workspace_storage_dir(workspace_id)
    for manifest_path in sorted(storage_dir.glob("*/manifest.json")):
        doc_id = manifest_path.parent.name
        if not re.fullmatch(r"[a-f0-9]{64}", doc_id):
            continue
        try:
            record_path = manifest_path.parent / "document.json"
            if record_path.exists():
                record = json.loads(record_path.read_text())
            else:
                case = json.loads(manifest_path.read_text())
                pages = int(case["total_pages"])
                filename = case["filename"]
                record = {
                    "status": "Ready", "docId": doc_id,
                    "filename": filename, "totalPages": pages,
                    "uploadedAt": case.get("uploaded_at"),
                    "pageImageBase": (f"public/pages/{doc_id}" if workspace_id is None
                                      else f"/api/documents/{doc_id}/pages"),
                    "pageText": {}, "textAvailable": False,
                    "subdocuments": whole_file_section(doc_id, filename, pages),
                }
            if record.get("docId") == doc_id and record.get("totalPages", 0) > 0:
                records.append(record)
        except (OSError, ValueError, KeyError, TypeError):
            # One damaged metadata record must not hide other uploaded sources.
            continue
    return records


def ingest_uploaded_pdf(file_bytes, filename, workspace_id=None):
    """Persist one independent source, deduplicating by bytes, never filename."""
    from backend.src.ingestion.pdf_renderer import DocumentIngestionService
    from backend.src.ingestion.text_extractor import TextExtractionService

    doc_id = hashlib.sha256(file_bytes).hexdigest()
    store = persistent_store() if workspace_id is not None else None
    storage_dir = STORAGE_DIR if workspace_id is None else workspace_storage_dir(workspace_id)
    with INGESTION_LOCK:
        record_path = storage_dir / doc_id / "document.json"
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if store:
                # A previous request may have rendered locally but died before
                # persistence. Replaying the same upload completes that safe,
                # idempotent operation rather than losing the source.
                stored = store.save_document(workspace_id, record, record_path.parent)
                return {**stored, "duplicate": bool(stored.get("duplicate", True))}
            return {**record, "duplicate": True}

        service = DocumentIngestionService(storage_dir=storage_dir)
        case = service.ingest_pdf(file_bytes, filename=filename)
        if case.total_pages < 1:
            raise ValueError("PDF contains no pages.")
        source_dir = storage_dir / doc_id
        # Legacy local files remain available at their old static URLs. New
        # anonymous workspaces use a cookie-checked page endpoint instead.
        if workspace_id is None:
            target = PAGES_PUBLIC_DIR / doc_id
            target.mkdir(parents=True, exist_ok=True)
            for page in range(1, case.total_pages + 1):
                shutil.copy2(source_dir / f"page_{page}.png", target / f"page_{page}.png")

        # Save the original so metadata and native text can be recovered later.
        (source_dir / "source.pdf").write_bytes(file_bytes)
        try:
            page_text = TextExtractionService.extract_from_pdf(file_bytes)
        except Exception:
            page_text = {}
        record = {
            "status": "Ready", "docId": doc_id,
            "filename": case.filename,
            "fileSize": f"{len(file_bytes) / 1024:.1f} KB",
            "totalPages": case.total_pages,
            "uploadedAt": case.uploaded_at,
            "pageImageBase": (f"public/pages/{doc_id}" if workspace_id is None
                              else f"/api/documents/{doc_id}/pages"),
            "pageText": page_text,
            "textAvailable": any(text.strip() for text in page_text.values()),
            # Arbitrary papers are whole documents. Pharma-specific heuristics
            # must not classify unrelated research as a compliance certificate.
            "subdocuments": whole_file_section(doc_id, case.filename, case.total_pages),
        }
        temp = record_path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False))
        temp.replace(record_path)
        if store:
            return store.save_document(workspace_id, record, source_dir)
        return record


class EvidHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def workspace_id(self):
        """Return this browser's opaque workspace token, creating it once.

        The token is intentionally not exposed to JavaScript. Tabs in the same
        browser profile automatically send the same HttpOnly cookie; another
        profile receives a different workspace without needing an account.
        """
        if hasattr(self, "_workspace_id"):
            return self._workspace_id
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        value = cookie.get(WORKSPACE_COOKIE)
        candidate = value.value if value else ""
        if WORKSPACE_ID_RE.fullmatch(candidate):
            self._workspace_id = candidate
        else:
            self._workspace_id = uuid.uuid4().hex
            self._workspace_cookie_to_set = self._workspace_id
        return self._workspace_id

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        workspace_id = getattr(self, "_workspace_cookie_to_set", None)
        if workspace_id:
            # A session cookie is deliberate: open tabs share one workspace,
            # while closing the browser starts a fresh anonymous workspace.
            cookie = f"{WORKSPACE_COOKIE}={workspace_id}; Path=/; HttpOnly; SameSite=Lax"
            # Render and similar hosts send the original HTTPS scheme in this
            # header. Localhost remains usable over plain HTTP during development.
            if (os.getenv("EVID_COOKIE_SECURE", "").lower() == "true" or
                    self.headers.get("X-Forwarded-Proto", "").lower() == "https"):
                cookie += "; Secure"
            self.send_header("Set-Cookie", cookie)
            del self._workspace_cookie_to_set
        super().end_headers()

    def send_json(self, status, payload):
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_workspace_page(self, workspace_id, doc_id, page_number):
        """Serve rendered evidence only after scoping it to the request cookie."""
        page_path = workspace_storage_dir(workspace_id) / doc_id / f"page_{page_number}.png"
        if page_path.is_file():
            data = page_path.read_bytes()
        else:
            store = persistent_store()
            if not store:
                self.send_json(404, {"error": "This page is not available in this workspace."})
                return
            try:
                data = store.page_bytes(workspace_id, doc_id, page_number)
            except Exception:
                self.send_json(404, {"error": "This page is not available in this workspace."})
                return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def require_same_origin(self):
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self.send_json(403, {"error": "Cross-origin requests are not allowed."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            self.send_json(200, {"status": "Ready", "service": "CiteCanvas", "version": "1.1.0",
                                 "supportedFormats": [".pdf"], "maxFileSizeMb": 25})
        elif path == "/api/health":
            self.send_json(200, runtime(self.workspace_id()).health())
        elif path == "/api/workspace":
            self.send_json(200, {"mode": "anonymous_browser", "sharedAcrossTabs": True})
        elif path == "/api/documents":
            self.send_json(200, {"documents": saved_documents(self.workspace_id())})
        elif match := re.fullmatch(r"/api/documents/([a-f0-9]{64})/pages/page_(\d+)\.png", path):
            self.send_workspace_page(self.workspace_id(), match.group(1), int(match.group(2)))
        else:
            super().do_GET()

    def do_POST(self):
        route = urlsplit(self.path).path
        workspace_id = self.workspace_id()
        if not self.require_same_origin():
            return
        if route == "/api/workspace/clear":
            workspace_dir = workspace_storage_dir(workspace_id)
            with INGESTION_LOCK:
                active = WORKSPACE_RUNTIMES.pop(workspace_id, None)
                if active:
                    active.clear_workspace_cache()
                store = persistent_store()
                if store:
                    store.clear_workspace(workspace_id)
                shutil.rmtree(workspace_dir, ignore_errors=True)
            self.send_json(200, {"cleared": True})
            return
        if route in ("/api/ask", "/api/extract", "/api/compare"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 20000: raise ValueError("Invalid request size.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError("Expected a JSON object.")
                selected = data.get("sourceIds")
                count = len(selected) if isinstance(selected, list) else 0
                with span("evid.workflow." + route.removeprefix("/api/"), {"evid.source_count": count}):
                    if route == "/api/ask": result = runtime(workspace_id).ask(selected, data.get("query"))
                    elif route == "/api/extract": result = runtime(workspace_id).extract(selected, data.get("fields"))
                    else: result = runtime(workspace_id).compare(selected)
                self.send_json(200, result)
            except (ValueError, TypeError) as error:
                self.send_json(400, {"error": str(error)[:300]})
            except Exception:
                self.send_json(503, {"error": "Analysis could not complete. Check the configured model service, then retry. No sample answer was substituted."})
            return
        if urlsplit(self.path).path != "/api/upload":
            self.send_json(404, {"error": "Endpoint not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json(400, {"error": "Invalid upload size."})
            return
        if length <= 0:
            self.send_json(400, {"error": "File is empty (0 bytes)."})
            return
        content_type = self.headers.get("Content-Type", "")
        multipart = "multipart/form-data" in content_type
        if length > MAX_FILE_BYTES + (64 * 1024 if multipart else 0):
            self.send_json(400, {"error": "File exceeds the 25 MB limit."})
            return
        body = self.rfile.read(length)
        filename = unquote(self.headers.get("X-Filename", "uploaded_document.pdf"))
        file_bytes = body
        if multipart:
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\n\r\n".encode() + body
            )
            file_bytes = b""
            for part in message.walk():
                if part.get_content_disposition() == "form-data" and part.get_filename():
                    filename = part.get_filename()
                    file_bytes = part.get_payload(decode=True) or b""
                    break
        filename = Path(filename.replace("\\", "/")).name
        if not file_bytes:
            self.send_json(400, {"error": "File is empty (0 bytes)."})
        elif len(file_bytes) > MAX_FILE_BYTES:
            self.send_json(400, {"error": "File exceeds the 25 MB limit."})
        elif not filename.lower().endswith(".pdf"):
            self.send_json(400, {"error": "Unsupported format. Upload a PDF file (.pdf)."})
        elif not file_bytes.startswith(b"%PDF-"):
            self.send_json(400, {"error": "Invalid or corrupted PDF header."})
        else:
            try:
                with span("evid.upload.process", {"evid.upload.bytes": len(file_bytes)}):
                    record = ingest_uploaded_pdf(file_bytes, filename, workspace_id)
            except Exception:
                self.send_json(422, {"error": "Could not render this PDF. It may be damaged or password protected."})
                return
            self.send_json(200, record)


def run_server(port=PORT):
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), EvidHTTPRequestHandler) as server:
        print(f"CiteCanvas UI and upload API: http://localhost:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    run_server(int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
