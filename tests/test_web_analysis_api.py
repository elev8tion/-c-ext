"""Tests for v0.3 web API endpoints — analysis, catalog, docs, tour, diff, tools."""

import time
import pytest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    from code_extract.web.state import state
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _scan_and_wait(client, path=None):
    """Scan and wait for background extraction to complete."""
    res = client.post("/api/scan", json={"path": str(path or FIXTURES)})
    assert res.status_code == 200
    data = res.json()
    scan_id = data["scan_id"]

    # Wait for extraction to finish (background task)
    for _ in range(30):
        status_res = client.get(f"/api/scan/{scan_id}/status")
        if status_res.json().get("status") == "ready":
            break
        time.sleep(0.2)

    return scan_id, data


# ── Scan Status ───────────────────────────────────────────────

class TestScanStatus:
    def test_status_endpoint(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.get(f"/api/scan/{scan_id}/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["blocks_extracted"] > 0

    def test_status_not_found(self, client):
        res = client.get("/api/scan/nonexistent/status")
        assert res.status_code == 404


# ── Dependency Graph ──────────────────────────────────────────

class TestGraphAPI:
    def test_build_graph(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/analysis/graph", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert "edges" in data

    def test_graph_not_found(self, client):
        res = client.post("/api/analysis/graph", json={"scan_id": "nonexistent"})
        assert res.status_code == 400


# ── Dead Code ─────────────────────────────────────────────────

class TestDeadCodeAPI:
    def test_dead_code(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/analysis/dead-code", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "items" in data


# ── Architecture ──────────────────────────────────────────────

class TestArchitectureAPI:
    def test_architecture(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/analysis/architecture", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "modules" in data
        assert "elements" in data
        assert "stats" in data


# ── Health ────────────────────────────────────────────────────

class TestHealthAPI:
    def test_health(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/analysis/health", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "score" in data
        assert "long_functions" in data


# ── Catalog ───────────────────────────────────────────────────

class TestCatalogAPI:
    def test_build_catalog(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/catalog/build", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "items" in data

    def test_get_catalog(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.get(f"/api/catalog/{scan_id}")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data


# ── Docs ──────────────────────────────────────────────────────

class TestDocsAPI:
    def test_generate_docs(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/docs/generate", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "sections" in data

    def test_markdown_export(self, client):
        scan_id, _ = _scan_and_wait(client)
        # Generate first
        client.post("/api/docs/generate", json={"scan_id": scan_id})
        res = client.get(f"/api/docs/{scan_id}/markdown")
        assert res.status_code == 200
        assert "text/markdown" in res.headers.get("content-type", "")


# ── Tour ──────────────────────────────────────────────────────

class TestTourAPI:
    def test_generate_tour(self, client):
        scan_id, _ = _scan_and_wait(client)
        res = client.post("/api/tour/generate", json={"scan_id": scan_id})
        assert res.status_code == 200
        data = res.json()
        assert "steps" in data

    def test_get_tour(self, client):
        scan_id, _ = _scan_and_wait(client)
        client.post("/api/tour/generate", json={"scan_id": scan_id})
        res = client.get(f"/api/tour/{scan_id}")
        assert res.status_code == 200


# ── Diff ──────────────────────────────────────────────────────

class TestDiffAPI:
    def test_diff_same_dir(self, client):
        res = client.post("/api/diff", json={
            "path_a": str(FIXTURES),
            "path_b": str(FIXTURES),
        })
        assert res.status_code == 200
        data = res.json()
        assert "diff_id" in data
        # Same dir should have zero added/removed
        assert len(data.get("added", [])) == 0
        assert len(data.get("removed", [])) == 0

    def test_diff_not_found(self, client):
        res = client.get("/api/diff/nonexistent")
        assert res.status_code == 404
