"""Native local Phase A smoke: actual SQLite/API files, no live archive/TTS claims."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from backend.app.projects.storage import ProjectStore
from backend.app.projects.models import StoryCandidate
from backend.app.api.server import create_app

ROOT=Path(__file__).resolve().parents[2]
def run(case,mode):
    if mode!="local":
        raise RuntimeError("A3 Phase A smoke supports local only; live evidence is separate.")
    source=json.loads((ROOT/"contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    with TemporaryDirectory() as directory:
        root=Path(directory);db=root/"state.sqlite";media=root/"media"
        store=ProjectStore(db,media)
        project=source["project"]["project_id"]
        rid=source["asset_requirements"][0]["requirement_id"]
        store.create_project(project,"Phase A smoke")
        store.import_story(StoryCandidate.parse(source),0)
        with TestClient(create_app(db,media)) as http:
            initial=http.get("/api/v1/projects/"+project+"/assets/requirements")
            assert initial.status_code==200,initial.text
            assert initial.json()["requirements"][0]["status"]=="ARCHIVE_ASSET_UNRESOLVED"
            if case in ("missing-asset-choice","phase-a"):
                response=http.post("/api/v1/projects/"+project+"/assets/"+rid+"/resolve",
                    headers={"Idempotency-Key":"phase-a-smoke-choice-01"},
                    json={"expected_revision":1,"resolution_mode":"MANUAL_UPLOAD",
                          "reason":"No verified archival media exists"})
                assert response.status_code==200,response.text
                assert http.get("/api/v1/projects/"+project+"/gates").json()[2]["state"]!="APPROVED"
            if case in ("asset-ui","phase-a"):
                assert http.get("/api/v1/projects/"+project+"/assets/"+rid+"/candidates").status_code==200
                settings=http.get("/api/v1/providers")
                assert settings.status_code==200 and all(x["live_status"]=="NOT_RUN"
                     for x in settings.json()["providers"])
        with TestClient(create_app(db,media)) as reopened:
            view=reopened.get("/api/v1/projects/"+project+"/assets/requirements").json()
            assert view["requirements"][0]["status"]==("MANUAL_SELECTED"
                     if case in ("missing-asset-choice","phase-a") else "ARCHIVE_ASSET_UNRESOLVED")
            assert reopened.get("/api/v1/projects/"+project+"/gates").json()[3]["state"]!="APPROVED"
        print(case+": LOCAL_PASS, genuine SQLite/API/restart; no G1/G3 operator approval or live provider")
