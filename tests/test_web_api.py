"""Tests for the web API."""

import pytest
from pathlib import Path

# Only run if fastapi/httpx are installed
try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_scan_fixtures(client):
    res = client.post("/api/scan", json={"path": str(FIXTURES)})
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert "scan_id" in data
    assert len(data["items"]) == data["count"]


def test_scan_nonexistent_path(client):
    res = client.post("/api/scan", json={"path": "/nonexistent/path"})
    assert res.status_code == 404


def test_path_traversal_blocked(client):
    res = client.post("/api/scan", json={"path": "/etc"})
    assert res.status_code == 403


def test_preview_item(client):
    # First scan to populate state
    scan_res = client.post("/api/scan", json={"path": str(FIXTURES)})
    items = scan_res.json()["items"]
    assert len(items) > 0

    # Preview first item
    item_id = items[0]["id"]
    res = client.get(f"/api/preview/{item_id}")
    assert res.status_code == 200
    data = res.json()
    assert "code" in data
    assert "name" in data
    assert "language" in data


def test_preview_not_found(client):
    res = client.get("/api/preview/nonexistent:0")
    assert res.status_code == 404


def test_exports_list_empty(client):
    res = client.get("/api/exports")
    assert res.status_code == 200
    data = res.json()
    assert "exports" in data


def test_autocomplete(client):
    home = str(Path.home())
    res = client.get(f"/api/autocomplete?q={home}")
    assert res.status_code == 200
    data = res.json()
    assert "suggestions" in data


def test_autocomplete_empty(client):
    res = client.get("/api/autocomplete?q=")
    assert res.status_code == 200
    data = res.json()
    assert len(data["suggestions"]) > 0  # Should return home dir


def test_extract_items(client):
    # Scan first
    scan_res = client.post("/api/scan", json={"path": str(FIXTURES)})
    data = scan_res.json()
    scan_id = data["scan_id"]
    item_ids = [item["id"] for item in data["items"][:3]]

    # Extract
    res = client.post("/api/extract", json={
        "scan_id": scan_id,
        "item_ids": item_ids,
    })
    assert res.status_code == 200
    extract_data = res.json()
    assert "export_id" in extract_data
    assert extract_data["files_created"] > 0
    assert "download_url" in extract_data


def test_download_export(client):
    # Scan + extract
    scan_res = client.post("/api/scan", json={"path": str(FIXTURES)})
    data = scan_res.json()
    item_ids = [item["id"] for item in data["items"][:2]]

    extract_res = client.post("/api/extract", json={
        "scan_id": data["scan_id"],
        "item_ids": item_ids,
    })
    download_url = extract_res.json()["download_url"]

    # Download
    res = client.get(download_url)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
