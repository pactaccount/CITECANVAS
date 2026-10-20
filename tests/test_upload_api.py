"""Regression coverage for independent uploads, persistence, and source text."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Load this project's server even when a temporary staged checkout is under test.
spec = importlib.util.spec_from_file_location("evid_upload_server", ROOT / "scripts" / "serve.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@pytest.fixture
def storage(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "STORAGE_DIR", tmp_path / "storage" / "pages")
    monkeypatch.setattr(server, "PAGES_PUBLIC_DIR", tmp_path / "frontend" / "public" / "pages")
    return tmp_path


def pdf(name):
    return (ROOT / "fixtures" / "evaluation" / name).read_bytes()


def test_upload_identity_images_text_and_restore(storage):
    alpha = pdf("upload_alpha.pdf")
    beta = pdf("upload_beta.pdf")
    a = server.ingest_uploaded_pdf(alpha, "research-paper.pdf")
    b = server.ingest_uploaded_pdf(beta, "research-paper.pdf")
    assert a["docId"] != b["docId"]
    assert a["totalPages"] == 12 and b["totalPages"] == 2
    assert a["subdocuments"][0]["subdocId"] != b["subdocuments"][0]["subdocId"]
    assert "ALPHA-PAGE-12" in a["pageText"][12]
    assert "BETA-PAGE-02" in b["pageText"][2]
    for record, page in [(a, 12), (b, 2)]:
        image_path = server.PAGES_PUBLIC_DIR / record["docId"] / f"page_{page}.png"
        with Image.open(image_path) as img:
            assert img.width > 1000
        assert (server.STORAGE_DIR / record["docId"] / "source.pdf").is_file()
    restored = server.saved_documents()
    assert {r["docId"] for r in restored} == {a["docId"], b["docId"]}
    assert "ALPHA-PAGE-12" in next(r for r in restored if r["docId"] == a["docId"])["pageText"]["12"]


def test_duplicate_content_with_another_name_is_one_source(storage):
    data = pdf("upload_beta.pdf")
    first = server.ingest_uploaded_pdf(data, "original.pdf")
    again = server.ingest_uploaded_pdf(data, "renamed-copy.pdf")
    assert again["duplicate"] is True
    assert first["docId"] == again["docId"]
    assert again["filename"] == "original.pdf"
    assert len(server.saved_documents()) == 1


def test_legacy_render_is_recovered_without_fabricated_text(storage):
    doc_id = "c" * 64
    folder = server.STORAGE_DIR / doc_id
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"doc_id":doc_id,"filename":"existing-research.pdf","total_pages":11}))
    legacy = server.saved_documents()[0]
    assert legacy["filename"] == "existing-research.pdf"
    assert legacy["totalPages"] == 11
    assert legacy["pageText"] == {} and legacy["textAvailable"] is False
    assert legacy["pageImageBase"] == f"public/pages/{doc_id}"


def test_corrupt_pdf_is_not_listed_as_a_source(storage):
    with pytest.raises(Exception):
        server.ingest_uploaded_pdf(b"%PDF-1.7\nnot a real PDF", "bad.pdf")
    assert server.saved_documents() == []


def test_anonymous_workspaces_are_isolated_and_use_guarded_page_urls(storage):
    first_workspace = "a" * 32
    second_workspace = "b" * 32
    record = server.ingest_uploaded_pdf(pdf("upload_beta.pdf"), "private.pdf", first_workspace)

    assert record["pageImageBase"] == f"/api/documents/{record['docId']}/pages"
    assert [item["docId"] for item in server.saved_documents(first_workspace)] == [record["docId"]]
    assert server.saved_documents(second_workspace) == []
    assert (server.workspace_storage_dir(first_workspace) / record["docId"] / "page_1.png").is_file()
    assert not (server.PAGES_PUBLIC_DIR / record["docId"] / "page_1.png").exists()
