"""Exact per-template G4 authoring uses persisted Story facts, not guessed payloads."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app.api.server import create_app

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "contracts/examples/visual_cases"


def test_ten_typed_setups_save_and_unapproved_compile_blocks(tmp_path):
    app = create_app(tmp_path / "isolated.sqlite", tmp_path / "media")
    story = json.loads((CASE / "StoryPackage.visual_cases.synthetic.json").read_text(encoding="utf-8"))
    bp = json.loads((CASE / "VisualBlueprint.visual_cases.synthetic.json").read_text(encoding="utf-8"))
    pid = story["project"]["project_id"]
    app.state.store.create_project(pid, "G4 authoring")
    with TestClient(app) as client:
        imported = client.post(f"/api/v1/projects/{pid}/story/import?expected_revision=0",
                               json=story, headers={"Idempotency-Key": "g4-import-synthetic-001"})
        assert imported.status_code == 200, imported.text
        url = f"/api/v1/projects/{pid}/storyboard/blueprint-authoring"
        first = client.get(url)
        assert first.status_code == 200, first.text
        board = first.json()
        assert not board["ready"]
        assert {s["template_id"] for s in board["setups"]} == {f"T{i:02}" for i in range(1, 11)}
        assert len(board["setups"]) == 10
        revision = board["project_revision"]
        payloads = {p["setup_id"]: p["template_payload"] for p in bp["setup_plans"]}
        first_setup = board["setups"][0]
        invalid = client.put(url + "/" + first_setup["setup_id"], json={
            "expected_revision": revision, "story_sha256": board["story_sha256"],
            "payload": {"template_id": first_setup["template_id"]}
        }, headers={"Idempotency-Key": "g4-invalid-template-001"})
        assert invalid.status_code == 422
        assert "TEMPLATE_PAYLOAD_INVALID" in invalid.text
        assert client.get(url).json()["project_revision"] == revision
        for index, item in enumerate(board["setups"]):
            body = {"expected_revision": revision, "story_sha256": board["story_sha256"],
                    "payload": payloads[item["setup_id"]]}
            key = f"g4-synthetic-save-{index:04}-unique"
            saved = client.put(url + "/" + item["setup_id"],json=body,headers={"Idempotency-Key":key})
            assert saved.status_code == 200, saved.text
            assert client.put(url + "/" + item["setup_id"],json=body,
                              headers={"Idempotency-Key":key}).json() == saved.json()
            revision += 1
            assert saved.json()["project_revision"] == revision
        fresh = client.get(url).json()
        assert fresh["ready"]
        assert len([s for s in fresh["setups"] if s["payload"]]) == 10
        compile_result = client.post(f"/api/v1/projects/{pid}/storyboard/compile",
                                     json={"expected_revision": revision, "story_sha256": board["story_sha256"]},
                                     headers={"Idempotency-Key": "g4-synthetic-compile-001"})
        assert compile_result.status_code == 422
        assert "COMPILER_GATE_UNAPPROVED" in compile_result.text
        assert client.get(url).json()["project_revision"] == revision
        unknown = client.put(url + "/setup_DOES_NOT_EXIST",json={
            "expected_revision": revision, "story_sha256": board["story_sha256"],
            "payload": {"template_id": "T01"}},
            headers={"Idempotency-Key": "g4-synthetic-unknown-001"})
        assert unknown.status_code == 422


def test_g4_payload_rejects_foreign_project_or_stale_story(tmp_path):
    app = create_app(tmp_path / "isolated.sqlite", tmp_path / "media")
    story = json.loads((CASE / "StoryPackage.visual_cases.synthetic.json").read_text(encoding="utf-8"))
    pid = story["project"]["project_id"]
    app.state.store.create_project(pid, "G4 project identity")
    with TestClient(app) as client:
        client.post(f"/api/v1/projects/{pid}/story/import?expected_revision=0",
                    json=story,headers={"Idempotency-Key":"g4-import-foreign-001"})
        board = client.get(f"/api/v1/projects/{pid}/storyboard/blueprint-authoring").json()
        sid = board["setups"][0]["setup_id"]
        result = client.put(f"/api/v1/projects/{pid}/storyboard/blueprint-authoring/{sid}",
                            json={"expected_revision":board["project_revision"],
                                  "story_sha256":"f"*64,
                                  "payload":{"template_id":board["setups"][0]["template_id"]}},
                            headers={"Idempotency-Key":"g4-stale-story-001"})
        assert result.status_code == 422
        assert "STORY_SHA_MISMATCH" in result.text
        assert client.get(f"/api/v1/projects/{pid}/storyboard/blueprint-authoring").json()["setups"][0]["payload"] is None
