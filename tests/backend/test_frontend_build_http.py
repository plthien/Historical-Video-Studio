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
    monkeypatch.setenv("HVS_FRONTEND_DIST", str(dist))
    app = create_app(tmp_path / "state.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        raw = json.dumps(manifest).encode("utf-8")
        for prefix in (b"", bytes((239, 187, 191))):
            # Reproduce the old PowerShell 5.1 UTF-8-with-BOM write and the
            # new no-BOM write, through the *real* FastAPI static HTTP route.
            expected = prefix + raw
            (dist / "build-info.json").write_bytes(expected)
            served = client.get("/build-info.json")
            assert served.status_code == 200, served.text
            assert "json" in served.headers["content-type"].lower()
            assert served.content == expected
            if not prefix:
                assert served.json() == manifest
        page = client.get("/")
        assert page.status_code == 200
        assert "Historical Video Studio" in page.text
