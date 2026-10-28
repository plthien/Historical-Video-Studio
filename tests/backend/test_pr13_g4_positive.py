"""Native Windows positive G4 API route over persisted controlled G1/G2/G3 sources.

Synthetic TTS/rights are strictly SYNTHETIC_TEST_ONLY, not licensed historical proof.
This exercises the REAL production compiler, GDI, map ingest, SQLite draft and HTTP API.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.jobs.queue import JobQueue
from backend.app.voice.attempts import VoiceService
from backend.app.voice import attempts
from backend.app.voice.workflow import FinalVoiceWorkflow
from backend.tools.voice_final_smoke import wav_fixture,mock_alignment
from backend.app.director import draft

ROOT=Path(__file__).resolve().parents[2]
def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))
PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC")
KEY=lambda text: {"Idempotency-Key":text}

@pytest.mark.skipif(os.name!="nt",reason="Required genuine native Windows GDI integration")
def test_http_g4_initial_compile_with_reviewed_period_map(tmp_path):
    story=load("contracts/examples/StoryPackage.v1.valid.json")
    payload=load("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    pid=story["project"]["project_id"]
    app=create_app(tmp_path/"g4-positive.sqlite",tmp_path/"media")
    store=app.state.store
    store.create_project(pid,"Test-only period map production flow")
    gates=GateService(store)
    store.import_story(StoryCandidate.parse(story),0)
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    voice=VoiceService(store,gates,JobQueue(store))
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"synthetic_test_only"}):
        voice.enqueue(pid,"sec_001","kokoro_local","am_adam",1.0,
                      "SYNTHETIC_TEST_ONLY",store.revision(pid),"g4route_voice_attempt_001")
        assert voice.process_one(lambda *_:wav_fixture(4.0))["state"]=="SUCCEEDED"
    g2=gates.board(pid)[1]
    gates.decide(pid,"G2",{"decision":"APPROVED",
        "candidate_sha256":g2["candidate_sha256"],
        "dependency_fingerprint":g2["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    workflow=FinalVoiceWorkflow(store,gates,JobQueue(store))
    assert workflow.process_one()["state"]=="SUCCEEDED"
    final=workflow.status(pid)["final_audio"]
    assert workflow.process_one(lambda audio,text:mock_alignment(final,text))["state"]=="SUCCEEDED"
    resolver=AssetResolution(store)
    resolver.choose(pid,"req_001","MANUAL_UPLOAD","SYNTHETIC_TEST_ONLY period map",store.revision(pid))
    candidate=AssetCandidates(store).manual(pid,"req_001",PNG,"SYNTHETIC_TEST_ONLY source",
                                               "1871 fixture","Not actual rights clearance")
    rights=resolver.approve_batch(pid,[{
        "requirement_id":"req_001","candidate_id":candidate["candidate_id"],
        "original_sha256":candidate["original_sha256"],"rights_status":"ELIGIBLE",
        "rights_evidence_note":"SYNTHETIC_TEST_ONLY rights fixture",
        "historical_context_note":"SYNTHETIC_TEST_ONLY historical fixture"}],store.revision(pid))
    g3=gates.board(pid)[2]
    gates.decide(pid,"G3",{"decision":"APPROVED",
        "candidate_sha256":g3["candidate_sha256"],
        "dependency_fingerprint":g3["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    record=load("contracts/examples/HistoricalMap.v1.valid.json")
    record.update(source_asset_id=candidate["candidate_id"],
                  source_original_sha256=candidate["original_sha256"],
                  raster_asset_sha256=candidate["original_sha256"],
                  geometry_format="RASTER",geography_mode="raster_georeferenced",
                  geometry_object_sha256=None,approved_feature_ids=[],labels=[],
                  user_approved=True,
                  rights_review_record_id=rights["approved"][0]["approval_record_id"])
    with TestClient(app) as client:
        base=f"/api/v1/projects/{pid}/storyboard"
        authored=client.get(base+"/blueprint-authoring")
        assert authored.status_code==200,authored.text
        meta=authored.json()
        assert meta["story_sha256"]==StoryCandidate.parse(story).sha256
        saved=client.put(base+"/blueprint-authoring/setup_001",
            json={"expected_revision":meta["project_revision"],
                  "story_sha256":meta["story_sha256"],"payload":payload},
            headers=KEY("g4route-payload-save-001"))
        assert saved.status_code==200,saved.text
        map_view=client.get(base+"/map-authoring")
        assert map_view.status_code==200,map_view.text
        body={"expected_revision":saved.json()["project_revision"],
              "story_sha256":meta["story_sha256"],
              "year":1871,"map_record":record,"feature_ids":[],
              "route_feature_id":None,"reviewed_tie_points":None}
        mapped=client.put(base+"/map-authoring/req_001",json=body,
                          headers=KEY("g4route-period-map-save-001"))
        assert mapped.status_code==200,mapped.text
        before=store.revision(pid)
        compile_body={"expected_revision":before,"story_sha256":meta["story_sha256"]}
        completed=client.post(base+"/compile",json=compile_body,
                              headers=KEY("g4route-positive-compile-001"))
        assert completed.status_code==200,completed.text
        assert completed.json()["state"]=="COMPILED_AWAITING_G4_REVIEW"
        assert completed.json()["project_revision"]==before
        assert client.post(base+"/compile",json=compile_body,
                           headers=KEY("g4route-positive-compile-001")).json()==completed.json()
        page=client.get(base+"/scenes")
        assert page.status_code==200,page.text
        assert page.json()["total"]==1
        assert page.json()["scenes"][0]["template_id"]=="T01"
        frozen=draft.load(store,pid)
        assert frozen["manifest_sha256"]==completed.json()["draft_manifest_sha256"]
        assert frozen["manifest"]["map_requests"]["req_001"]["year"]==1871
        assert frozen["manifest"]["gate_heads"]["G1"]
        assert frozen["manifest"]["gate_heads"]["G2"]
        assert frozen["manifest"]["gate_heads"]["G3"]
        assert client.get(base+"/timeline").status_code==200
        # Source-bound compiler refuses edits after the original G3 approval
        # changes or a Story revision, rather than replaying this old draft.
