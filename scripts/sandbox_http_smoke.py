#!/usr/bin/env python3
"""One offline HTTP smoke test for anonymous-workspace isolation.

It intentionally uses a bundled fixture and cookie jars. No NVIDIA, R2,
Neon, or Qdrant request is made.
"""

import http.cookiejar
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor


BASE_URL = os.getenv("EVID_SMOKE_URL", "http://127.0.0.1:8000")
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "evaluation" / "upload_beta.pdf"


def client():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(opener, path, data=None, headers=None, json_response=True):
    response = opener.open(Request(BASE_URL + path, data=data, headers=headers or {}), timeout=15)
    body = response.read()
    return response.status, (json.loads(body) if json_response else body)


def main():
    first, second = client(), client()
    assert request(first, "/api/documents")[1]["documents"] == []
    assert request(second, "/api/documents")[1]["documents"] == []

    status, record = request(
        first,
        "/api/upload",
        FIXTURE.read_bytes(),
        {"X-Filename": "sandbox-fixture.pdf", "Content-Type": "application/pdf"},
    )
    assert status == 200
    doc_id = record["docId"]
    assert len(request(first, "/api/documents")[1]["documents"]) == 1
    assert request(second, "/api/documents")[1]["documents"] == []

    assert request(first, f"/api/documents/{doc_id}/pages/page_1.png", json_response=False)[0] == 200
    try:
        request(second, f"/api/documents/{doc_id}/pages/page_1.png", json_response=False)
        raise AssertionError("A second workspace read a private page.")
    except HTTPError as error:
        assert error.code == 404

    assert request(first, "/api/workspace/clear", b"")[1]["cleared"] is True
    assert request(first, "/api/documents")[1]["documents"] == []
    print("sandbox HTTP smoke: passed")


if __name__ == "__main__":
    main()
