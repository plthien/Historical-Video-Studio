"""A3-04/05: durable operator choice, exact immutable bytes and batch atomicity."""
import pytest
from backend.app.contracts import ContractViolation
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.projects.storage import ProjectStore
import json
from pathlib import Path
from backend.app.projects.models import StoryCandidate
from backend.app.assets.download import inspect
def png():
    import struct,zlib
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes([0,1,10,30])))+chunk(b"IEND",b""))
PNG=png()
def project(tmp_path):
    source=Path(__file__).resolve().parents[2]/"contracts/examples/longform/StoryPackage.longform.synthetic.json"
    story=json.loads(source.read_text())
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    pid=story["project"]["project_id"]
    store.create_project(pid,"Local archive review")
    store.import_story(StoryCandidate.parse(story),0)
    return store,pid,story["asset_requirements"][0]["requirement_id"]

def test_resolution_requires_operator_choice_and_second_review(tmp_path):
    store,pid,rid=project(tmp_path)
    resolver=AssetResolution(store)
    assets=AssetCandidates(store)
    assert resolver.requirements(pid)["requirements"][0]["status"]=="ARCHIVE_ASSET_UNRESOLVED"
    revision=store.revision(pid)
    with pytest.raises(ContractViolation,match="ASSET_RESOLUTION_INVALID"):
        resolver.choose(pid,rid,"MANAGED_FALLBACK","",revision)
    saved=resolver.choose(pid,rid,"MANUAL_UPLOAD","I own licensed source",revision)
    candidate=assets.manual(pid,rid,PNG,"Manual source","Ancient period, suitable reference","Written rights permission")
    review=dict(requirement_id=rid,candidate_id=candidate["candidate_id"],
                original_sha256=candidate["original_sha256"],rights_status="ELIGIBLE",
                rights_evidence_note="Documented owned-source permission",
                historical_context_note="Confirmed period and region")
    with pytest.raises(ContractViolation,match="ASSET_REVIEW_REQUIRED"):
        resolver.approve_batch(pid,[{**review,"rights_status":"UNKNOWN"}],saved["project_revision"])
    with pytest.raises(ContractViolation,match="ASSET_ORIGINAL_SHA_MISMATCH"):
        resolver.approve_batch(pid,[{**review,"original_sha256":store.put_artifact(png()+b"other","original")}],saved["project_revision"])
    confirmed=resolver.approve_batch(pid,[review],saved["project_revision"])
    assert len(confirmed["approved"])==1
    assert resolver.requirements(pid)["requirements"][0]["status"]=="APPROVED"
    with pytest.raises(ContractViolation,match="REVISION_CONFLICT"):
        resolver.approve_batch(pid,[review],saved["project_revision"])
    reread=AssetResolution(ProjectStore(store.database,store.artifacts.root))
    assert reread.requirements(pid)["requirements"][0]["approval_record_id"]==confirmed["approved"][0]["approval_record_id"]

def test_batch_approval_is_all_or_nothing(tmp_path):
    store,pid,rid=project(tmp_path)
    rid2=store.get_story(pid).data()["asset_requirements"][1]["requirement_id"]
    resolver=AssetResolution(store)
    assets=AssetCandidates(store)
    a=assets.manual(pid,rid,PNG,"One","Period confirmed","Permission one")
    b=assets.manual(pid,rid2,PNG,"Two","Period confirmed","Permission two")
    reviews=[dict(requirement_id=rid,candidate_id=a["candidate_id"],original_sha256=a["original_sha256"],
                  rights_status="ELIGIBLE",rights_evidence_note="Owned",historical_context_note="Period verified"),
             dict(requirement_id=rid2,candidate_id=b["candidate_id"],original_sha256=b["original_sha256"],
                  rights_status="ELIGIBLE",rights_evidence_note="Owned",historical_context_note="Period verified")]
    start=store.revision(pid)
    with pytest.raises(ContractViolation,match="ASSET_RESOLUTION_REQUIRED"):
        resolver.approve_batch(pid,reviews,start)
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_approval_events").fetchone()[0]==0
    start=resolver.choose(pid,rid,"MANUAL_UPLOAD","User owned file",start)["project_revision"]
    start=resolver.choose(pid,rid2,"MANUAL_UPLOAD","User owned file",start)["project_revision"]
    done=resolver.approve_batch(pid,reviews,start)
    assert len(done["approved"])==2
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_approval_heads").fetchone()[0]==2
