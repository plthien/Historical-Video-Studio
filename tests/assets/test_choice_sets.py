"""D02: real operator choice-set review and independent G3 gate approval."""
from __future__ import annotations
import json
import struct
import zlib
from pathlib import Path
import pytest

from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.contracts import ContractViolation
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore


ROOT=Path(__file__).resolve().parents[2]


def png(rgb):
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes([0,*rgb])))+chunk(b"IEND",b""))


def fixture(tmp_path):
    story=json.loads((ROOT/"contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    pid=story["project"]["project_id"]
    store.create_project(pid,"Synthetic reviewed choice set")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    rev=store.revision(pid)
    for claim in story["claims"]:
        rev=gates.review_claim(pid,claim["claim_id"],"VERIFIED",
                               "Synthetic test-source review only",rev,"https://www.loc.gov/")
    board=gates.board(pid)[0]
    result=gates.decide(pid,"G1",{
        "decision":"APPROVED","candidate_sha256":board["candidate_sha256"],
        "dependency_fingerprint":board["dependency_fingerprint"],
        "expected_revision":rev,"comment":"Synthetic software evidence, not archival approval"})
    assert result["state"]=="APPROVED"
    resolver=AssetResolution(store)
    assets=AssetCandidates(store)
    rev=store.revision(pid)
    candidates={}
    reviews=[]
    for i,req in enumerate(story["asset_requirements"]):
        rid=req["requirement_id"]
        rev=resolver.choose(pid,rid,"MANUAL_UPLOAD","Synthetic source review",rev)["project_revision"]
        artifact=png((i%255,20,35))
        candidate=assets.manual(pid,rid,artifact,"Synthetic original "+str(i),
                                "Synthetic period review","Test rights note")
        candidates[rid]=candidate
        reviews.append({"requirement_id":rid,"candidate_id":candidate["candidate_id"],
                        "original_sha256":candidate["original_sha256"],
                        "rights_status":"ELIGIBLE","rights_evidence_note":"Synthetic fixture licensed for testing",
                        "historical_context_note":"Test period source, no real historical approval"})
    complete=resolver.approve_batch(pid,reviews,store.revision(pid))
    assert len(complete["approved"])==len(reviews)
    board=next(x for x in gates.board(pid) if x["gate_id"]=="G3")
    approval=gates.decide(pid,"G3",{
        "decision":"APPROVED","candidate_sha256":board["candidate_sha256"],
        "dependency_fingerprint":board["dependency_fingerprint"],
        "expected_revision":store.revision(pid),
        "comment":"Approve test-only G3 source candidate"})
    assert approval["state"]=="APPROVED"
    return store,pid,resolver,assets,candidates,reviews,gates


def test_choice_set_is_new_current_G3_authority_and_history_not_eligible(tmp_path):
    store,pid,resolver,assets,candidates,reviews,gates=fixture(tmp_path)
    rid=reviews[0]["requirement_id"]
    story=store.get_story(pid).data()
    slot=next(x["slot_id"] for setup in story["visual_setups"]
              for x in setup["direction"]["asset_slots"] if x["requirement_id"]==rid)
    alt=assets.manual(pid,rid,png((127,8,36)),"Alternative original",
                      "Test synthetic period note","Test rights note")
    second={**reviews[0],"candidate_id":alt["candidate_id"],
            "original_sha256":alt["original_sha256"]}
    before=store.revision(pid)
    rejected=[reviews[0],{**second,"rights_status":"UNKNOWN"}]
    with pytest.raises(ContractViolation,match="ASSET_REVIEW_REQUIRED"):
        resolver.review_choice_set(pid,rid,slot,rejected,"Review same-slot sources",before)
    assert store.revision(pid)==before
    created=resolver.review_choice_set(pid,rid,slot,[reviews[0],second],
                                        "Two distinct eligible synthetic originals",before)
    assert created["g3_reapproval_required"]
    pool=resolver.current_choice_set(pid,rid,slot)
    assert pool["set_sha256"]==created["set_sha256"] and len(pool["items"])==2
    assert pool["g3_current"] is False
    board=next(x for x in gates.board(pid) if x["gate_id"]=="G3")
    assert board["state"]!="APPROVED"
    accepted=gates.decide(pid,"G3",{
        "decision":"APPROVED","candidate_sha256":board["candidate_sha256"],
        "dependency_fingerprint":board["dependency_fingerprint"],
        "expected_revision":created["project_revision"],
        "comment":"Independent test-only current G3 pool approval"})
    assert accepted["state"]=="APPROVED"
    again=AssetResolution(ProjectStore(store.database,store.artifacts.root))
    assert again.current_choice_set(pid,rid,slot)["g3_current"] is True
    with pytest.raises(ContractViolation,match="REVISION_CONFLICT"):
        resolver.review_choice_set(pid,rid,slot,[reviews[0],second],"Old revision invalid",before)
    with pytest.raises(ContractViolation,match="G3_CHOICE_SET_INVALID"):
        resolver.review_choice_set(pid,rid,slot,[reviews[0],reviews[0]],
                                   "Duplicate original cannot be option",store.revision(pid))
