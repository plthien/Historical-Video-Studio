"""A3-06 Phase A: real local SQLite/API gate and restart behavior, no live-provider claims."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.api.server import create_app
from backend.app.projects.storage import ProjectStore
from backend.app.projects.models import StoryCandidate
from backend.app.projects.gates import GateService
from backend.app.assets.resolution import AssetResolution

def _png_fixture():
    import struct,zlib
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    return (b"\x89PNG\r\n\x1a\n"+
        chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
        chunk(b"IDAT",zlib.compress(bytes([0,1,10,30])))+chunk(b"IEND",b""))

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


def test_phase_a_complete_g3_requires_g1_and_all_exact_sources(tmp_path):
    """One actual SQLite G1→G3 path: incomplete source set never yields approval."""
    import struct,zlib
    from backend.app.assets.provenance import AssetCandidates
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    raw=(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
         chunk(b"IDAT",zlib.compress(bytes([0,1,10,30])))+chunk(b"IEND",b""))
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    story=json.loads((Path(__file__).resolve().parents[2]/
        "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    for claim in story["claims"]:claim["critical"]=False
    pid=story["project"]["project_id"]
    store.create_project(pid,"Local human review fixture")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store); assets=AssetCandidates(store);resolver=AssetResolution(store)
    g1=gates.board(pid)[0]
    assert g1["state"]=="READY_FOR_REVIEW"
    gates.decide(pid,"G1",{"decision":"APPROVED","candidate_sha256":g1["candidate_sha256"],
                           "dependency_fingerprint":g1["dependency_fingerprint"],
                           "expected_revision":store.revision(pid)})
    reviews=[]
    for req in story["asset_requirements"]:
        rid=req["requirement_id"]
        rev=resolver.choose(pid,rid,"MANUAL_UPLOAD","Operator selects owned media",
                            store.revision(pid))["project_revision"]
        candidate=assets.manual(pid,rid,raw,"Reviewed visual source","Context fixture",
                                "Rights must be evaluated by the operator")
        reviews.append(dict(requirement_id=rid,candidate_id=candidate["candidate_id"],
                            original_sha256=candidate["original_sha256"],rights_status="ELIGIBLE",
                            rights_evidence_note="Synthetic rights approval test only",
                            historical_context_note="Synthetic period suitability test only"))
    assert gates.board(pid)[2]["state"]!="APPROVED"
    resolver.approve_batch(pid,reviews,store.revision(pid))
    ready=gates.board(pid)[2]
    assert ready["state"]=="READY_FOR_REVIEW"
    result=gates.decide(pid,"G3",{"decision":"APPROVED",
        "candidate_sha256":ready["candidate_sha256"],
        "dependency_fingerprint":ready["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    assert result["state"]=="APPROVED"
    assert GateService(ProjectStore(store.database,store.artifacts.root)).board(pid)[2]["state"]=="APPROVED"
    assert gates.board(pid)[3]["state"]!="APPROVED"


def test_phase_a_g3_stale_requires_new_review_even_for_same_original(tmp_path):
    """F01: an A→B→A selection never silently revives historical G3."""
    from backend.app.assets.provenance import AssetCandidates

    story=json.loads((Path(__file__).resolve().parents[2]/
        "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    rid=story["asset_requirements"][0]["requirement_id"]
    story["asset_requirements"]=story["asset_requirements"][:1]
    for section in story["sections"]:
        section["asset_requirement_refs"]=[x for x in section["asset_requirement_refs"] if x==rid]
    for setup in story["visual_setups"]:
        setup["requirement_refs"]=[x for x in setup["requirement_refs"] if x==rid]
    for claim in story["claims"]:claim["critical"]=False
    store=ProjectStore(tmp_path/"state.sqlite",tmp_path/"media")
    pid=story["project"]["project_id"]
    store.create_project(pid,"G3 stale cycle")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED","candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    resolver=AssetResolution(store)
    resolver.choose(pid,rid,"MANUAL_UPLOAD","Licensed original",store.revision(pid))
    candidate=AssetCandidates(store).manual(pid,rid,_png_fixture(),"Reviewed image","Checked date","Licensed")
    review={"requirement_id":rid,"candidate_id":candidate["candidate_id"],
            "original_sha256":candidate["original_sha256"],"rights_status":"ELIGIBLE",
            "rights_evidence_note":"Fixture license review","historical_context_note":"Fixture period check"}
    resolver.approve_batch(pid,[review],store.revision(pid))
    g3=gates.board(pid)[2]
    gates.decide(pid,"G3",{"decision":"APPROVED","candidate_sha256":g3["candidate_sha256"],
        "dependency_fingerprint":g3["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    old=gates.board(pid)[2]
    assert old["state"]=="APPROVED"
    resolver.choose(pid,rid,"MANAGED_FALLBACK","Changed selection",store.revision(pid))
    resolver.choose(pid,rid,"MANUAL_UPLOAD","Licensed original",store.revision(pid))
    assert gates.board(pid)[2]["state"]!="APPROVED"
    resolver.approve_batch(pid,[review],store.revision(pid))
    fresh=gates.board(pid)[2]
    assert fresh["state"]=="READY_FOR_REVIEW",fresh
    assert (fresh["candidate_sha256"],fresh["dependency_fingerprint"])!=(
        old["candidate_sha256"],old["dependency_fingerprint"])
    gates.decide(pid,"G3",{"decision":"APPROVED","candidate_sha256":fresh["candidate_sha256"],
        "dependency_fingerprint":fresh["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    assert GateService(ProjectStore(store.database,store.artifacts.root)).board(pid)[2]["state"]=="APPROVED"
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G3'").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM asset_approval_events").fetchone()[0]==2
    assert store.get_artifact(candidate["original_sha256"])==_png_fixture()


def test_phase_a_empty_asset_requirements_explicit_g3_and_restart(tmp_path):
    """F06: valid zero-asset StoryPackage requires real operator G3 confirmation."""
    story=json.loads((Path(__file__).resolve().parents[2]/
        "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    story["asset_requirements"]=[]
    for section in story["sections"]:section["asset_requirement_refs"]=[]
    for setup in story["visual_setups"]:setup["requirement_refs"]=[]
    for claim in story["claims"]:claim["critical"]=False
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    pid=story["project"]["project_id"]
    store.create_project(pid,"Zero media")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    assert gates.board(pid)[2]["state"]=="BLOCKED"
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED","candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    g3=gates.board(pid)[2]
    assert g3["state"]=="READY_FOR_REVIEW"
    with TestClient(create_app(store.database,store.artifacts.root)) as client:
        assert client.get("/api/v1/projects/"+pid+"/assets/requirements").json()["requirements"]==[]
        response=client.post("/api/v1/projects/"+pid+"/gates/G3/decision",
            headers={"Idempotency-Key":"empty-assets-g3-approve-001"},json={
            "decision":"APPROVED","candidate_sha256":g3["candidate_sha256"],
            "dependency_fingerprint":g3["dependency_fingerprint"],
            "expected_revision":store.revision(pid),
            "comment":"Reviewed StoryPackage: no historical media required"})
        assert response.status_code==200,response.text
    assert GateService(ProjectStore(store.database,store.artifacts.root)).board(pid)[2]["state"]=="APPROVED"


def test_phase_a_real_g1_g2_g3_reopen_independence(tmp_path):
    """F04: controlled TTS+alignment and exact reviewed image survive the same SQLite restart."""
    from backend.tools.voice_final_smoke import setup,approval,mock_alignment
    from backend.app.voice.workflow import FinalVoiceWorkflow
    from backend.app.jobs.queue import JobQueue
    from backend.app.assets.provenance import AssetCandidates

    store,gates,voice,workflow,pid,story=setup(tmp_path)
    approved_g2=approval(store,gates,pid)
    assert approved_g2["state"]=="APPROVED"
    assert workflow.process_one()["state"]=="SUCCEEDED"
    audio=workflow.status(pid)["final_audio"]
    assert workflow.process_one(lambda raw,text:mock_alignment(audio,text))["state"]=="SUCCEEDED"
    assert workflow.status(pid)["g4_ready_dependency"]
    resolver=AssetResolution(store)
    media=AssetCandidates(store)
    reviews=[]
    for requirement in story["asset_requirements"]:
        rid=requirement["requirement_id"]
        resolver.choose(pid,rid,"MANUAL_UPLOAD","Reviewed owned source",store.revision(pid))
        asset=media.manual(pid,rid,_png_fixture(),"Local original","Period checked","Operator license review")
        reviews.append({"requirement_id":rid,"candidate_id":asset["candidate_id"],
          "original_sha256":asset["original_sha256"],"rights_status":"ELIGIBLE",
          "rights_evidence_note":"Controlled fixture license","historical_context_note":"Controlled period"})
    resolver.approve_batch(pid,reviews,store.revision(pid))
    board=gates.board(pid)
    assert board[1]["state"]=="APPROVED"
    assert board[2]["state"]=="READY_FOR_REVIEW"
    g3=board[2]
    gates.decide(pid,"G3",{"decision":"APPROVED","candidate_sha256":g3["candidate_sha256"],
        "dependency_fingerprint":g3["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    reopened=ProjectStore(store.database,store.artifacts.root)
    board=GateService(reopened).board(pid)
    assert [board[i]["state"] for i in (0,1,2)]==["APPROVED"]*3
    from backend.app.voice.workflow import word_map_ready
    with reopened._connection() as db:
        assert word_map_ready(db,pid)
    assert FinalVoiceWorkflow(reopened,GateService(reopened),JobQueue(reopened)).status(pid)["g4_ready_dependency"]
    assert reopened.get_artifact(audio["audio_sha256"])
    assert board[3]["state"]!="APPROVED"
