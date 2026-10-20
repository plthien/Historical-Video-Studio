"""A3-06 Phase A: real local SQLite/API gate and restart behavior, no live-provider claims."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.api.server import create_app
from backend.app.projects.storage import ProjectStore
from backend.app.projects.models import StoryCandidate
from backend.app.projects.gates import GateService
from backend.app.assets.resolution import AssetResolution

def test_phase_a_local_g3_never_auto_approves_and_survives_reopen(tmp_path):
    db=tmp_path/"phase_a.sqlite";media=tmp_path/"media"
    store=ProjectStore(db,media)
    story=json.loads((Path(__file__).resolve().parents[2]/
        "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    pid=story["project"]["project_id"];rid=story["asset_requirements"][0]["requirement_id"]
    store.create_project(pid,"Phase A integration")
    store.import_story(StoryCandidate.parse(story),0)
    with TestClient(create_app(db,media)) as http:
        initial=http.get("/api/v1/projects/"+pid+"/assets/requirements")
        assert initial.status_code==200
        assert initial.json()["requirements"][0]["status"]=="ARCHIVE_ASSET_UNRESOLVED"
        key={"Idempotency-Key":"phase-a-choice-001"}
        choice=http.post("/api/v1/projects/"+pid+"/assets/"+rid+"/resolve",headers=key,
                         json={"expected_revision":1,"resolution_mode":"MANUAL_UPLOAD",
                               "reason":"Operator supplies an original"})
        assert choice.status_code==200,choice.text
        assert choice.json()["project_revision"]==2
        assert http.get("/api/v1/projects/"+pid+"/gates").json()[2]["state"]!="APPROVED"
        providers=http.get("/api/v1/providers").json()["providers"]
        assert all(x["live_status"]=="NOT_RUN" for x in providers)
        assert all("api_key" not in x for x in providers)
    reopened=AssetResolution(ProjectStore(db,media))
    req=reopened.requirements(pid)["requirements"][0]
    assert req["resolution_mode"]=="MANUAL_UPLOAD"
    assert req["approved_asset_id"] is None
    assert GateService(ProjectStore(db,media)).board(pid)[3]["state"]!="APPROVED"

def test_phase_a_batch_rejects_unknown_candidate_without_sqlite_side_effect(tmp_path):
    store=ProjectStore(tmp_path/"db",tmp_path/"media")
    story=json.loads((Path(__file__).resolve().parents[2]/
        "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    pid=story["project"]["project_id"];rid=story["asset_requirements"][0]["requirement_id"]
    store.create_project(pid,"Phase A")
    store.import_story(StoryCandidate.parse(story),0)
    with TestClient(create_app(tmp_path/"db",tmp_path/"media")) as http:
        result=http.post("/api/v1/projects/"+pid+"/assets/batch-approve",
            headers={"Idempotency-Key":"phase-a-batch-reject-001"},
            json={"expected_revision":1,"reviews":[{
                "requirement_id":rid,"candidate_id":"assetcand_unknown",
                "original_sha256":"f"*64,"rights_status":"ELIGIBLE",
                "rights_evidence_note":"A note","historical_context_note":"A historical note"}]})
        assert result.status_code in (404,422),result.text
        assert store.revision(pid)==1
        with store._connection() as db:
            assert db.execute("SELECT COUNT(*) FROM asset_approval_events").fetchone()[0]==0
