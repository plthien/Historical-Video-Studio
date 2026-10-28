"""Native local port configuration is consumed by the real FastAPI CORS layer."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.server import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_configured_development_frontend_port_is_authorized(tmp_path):
    ports = json.loads((ROOT / "config" / "ports.json").read_text(encoding="utf-8"))
    assert ports == {"backend_port": 8010, "frontend_port": 5180}
    app = create_app(tmp_path / "ports.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        for host in ("127.0.0.1", "localhost"):
            origin = f"http://{host}:{ports['frontend_port']}"
            response = client.options(
                "/api/v1/projects",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                         "Access-Control-Request-Headers": "content-type,idempotency-key"},
            )
            assert response.status_code == 200, response.text
            assert response.headers.get("access-control-allow-origin") == origin
            assert "POST" in response.headers.get("access-control-allow-methods", "")
        # E2E services keep their own isolated port mapping even when defaults change.
        test_origin = "http://127.0.0.1:5173"
        test_result = client.options("/api/v1/projects", headers={
            "Origin": test_origin, "Access-Control-Request-Method": "POST"})
        assert test_result.status_code == 200
        assert test_result.headers.get("access-control-allow-origin") == test_origin
        unexpected = client.options("/api/v1/projects", headers={
            "Origin": "http://127.0.0.1:5199", "Access-Control-Request-Method": "POST"})
        assert unexpected.headers.get("access-control-allow-origin") is None
