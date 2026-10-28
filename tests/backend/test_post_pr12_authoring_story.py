"""Post-PR12 bounded API behavior; disposable SQLite only (WP3A/C)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app.api.server import create_app

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json"


def test_brief_is_deterministic_and_project_scoped(tmp_path):
    app = create_app(tmp_path / "db.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        pid = client.post("/api/v1/projects", json={"title": "Test external brief"}).json()["project_id"]
        body = {"topic": "Medieval road networks", "audience": "Adult learners",
                "runtime_minutes": 7, "editorial_goals": "Documented source chronology"}
        url = f"/api/v1/projects/{pid}/authoring-brief"
        first = client.post(url, json=body)
        assert first.status_code == 200
        assert first.json() == client.post(url, json=body).json()
        assert "StoryPackage.v1" in first.json()["content"]
        assert pid in first.json()["content"]
        assert "asset_requirements" in first.json()["content"]
        changed = client.post(url, json={**body, "topic": "Ancient maritime trade"})
        assert changed.json()["content"] != first.json()["content"]
        assert client.post(url, json={**body, "runtime_minutes": 11}).status_code == 422


def test_section_patch_keeps_immutable_history_and_no_unrelated_setup_mutation(tmp_path):
    app = create_app(tmp_path / "db.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        story = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        pid = story["project"]["project_id"]
        app.state.store.create_project(pid, "Section repair")
        key = "import-test-unique-001"
        original = client.post(f"/api/v1/projects/{pid}/story/import?expected_revision=0",
                               headers={"Idempotency-Key": key}, json=story)
        assert original.status_code == 200, original.text
        section = story["sections"][0]
        revision = original.json()["project_revision"]
        changed_text = section["narration"] + " Additional historical context requires review."
        path = f"/api/v1/projects/{pid}/story/sections/{section['section_id']}"
        body = {"expected_revision": revision, "narration": changed_text, "reason": "Editorial correction"}
        headers = {"Idempotency-Key": "patch-test-unique-001"}
        changed = client.patch(path, json=body, headers=headers)
        assert changed.status_code == 200, changed.text
        assert changed.json()["project_revision"] == revision + 1
        assert client.patch(path, json=body, headers=headers).json() == changed.json()
        current = client.get(f"/api/v1/projects/{pid}/story").json()["story"]
        assert current["sections"][0]["narration"] == changed_text
        assert current["visual_setups"] == story["visual_setups"]
        assert current["asset_requirements"] == story["asset_requirements"]
        assert app.state.store.get_story(pid, revision).data() == story
        assert client.patch(path, json={**body, "narration": changed_text+" again"},
                            headers={"Idempotency-Key": "patch-test-unique-002"}).status_code == 409
        assert client.patch(path+"-unknown", json=body,
                            headers={"Idempotency-Key": "patch-test-unique-003"}).status_code == 422


def test_local_project_settings_cas_reopen_and_recent_listing(tmp_path):
    database = tmp_path / "db.sqlite"
    media = tmp_path / "media"
    with TestClient(create_app(database, media)) as client:
        first = client.post("/api/v1/projects", json={"title": "First archive subject"}).json()
        second = client.post("/api/v1/projects", json={"title": "Second archive subject"}).json()
        items = client.get("/api/v1/projects").json()
        assert [item["project_id"] for item in items[:2]] == [second["project_id"], first["project_id"]]
        pid = first["project_id"]
        settings = {"topic": "Historical maritime shipping", "audience": "Adults",
                    "runtime_minutes": 8, "editorial_goals": "Careful geographic sources",
                    "expected_revision": 0}
        uri = f"/api/v1/projects/{pid}/authoring-settings"
        saved = client.put(uri, json=settings, headers={"Idempotency-Key": "settings-save-unique-001"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["project_revision"] == 1
        assert client.put(uri, json=settings,headers={"Idempotency-Key": "settings-save-unique-001"}).json() == saved.json()
        assert client.put(uri,json={**settings,"topic":"Different"},
                          headers={"Idempotency-Key":"settings-save-unique-001"}).status_code == 409
        assert client.put(uri,json={**settings,"topic":"Another topic"},
                          headers={"Idempotency-Key":"settings-save-unique-002"}).status_code == 409
        assert client.get(f"/api/v1/projects/{pid}").json()["project_revision"] == 1
    with TestClient(create_app(database,media)) as reopened:
        persisted = reopened.get(uri).json()["settings"]
        assert persisted["topic"] == settings["topic"]
        assert persisted["editorial_goals"] == settings["editorial_goals"]
        assert reopened.get(f"/api/v1/projects/{pid}").json()["project_revision"] == 1
