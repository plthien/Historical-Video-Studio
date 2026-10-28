"""Protect Windows launcher's exact static build-info HTTP contract."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.api.server import create_app


def test_built_frontend_manifest_is_served_as_json(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Historical Video Studio</title>", encoding="utf-8")
    manifest = {
        "schema_version": "HVSFrontendBuild.v1",
        "source_commit": "a" * 40,
        "input_sha256": "b" * 64,
        "port_config_sha256": "c" * 64,
        "bundle_sha256": "d" * 64,
    }
    (dist / "build-info.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("HVS_FRONTEND_DIST", str(dist))
    app = create_app(tmp_path / "state.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        served = client.get("/build-info.json")
        assert served.status_code == 200, served.text
        assert "json" in served.headers["content-type"].lower()
        assert served.json() == manifest
        assert served.json()["bundle_sha256"] == manifest["bundle_sha256"]
        page = client.get("/")
        assert page.status_code == 200
        assert "Historical Video Studio" in page.text
