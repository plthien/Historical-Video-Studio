"""B2-05 real G3-reviewed T02 alpha derivative via operator HTTP and gate reapproval."""
import base64
import json
import struct
import zlib
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.api.server import create_app
from backend.app.assets.alpha_mask import rgba_alpha_extent
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.contracts import ContractViolation
from backend.app.projects.models import StoryCandidate
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore


ROOT=Path(__file__).resolve().parents[2]


def png(transparent=False, all_clear=False):
    w=h=8
    pixels=bytearray()
    for y in range(h):
        pixels.append(0)
        for x in range(w):
            a=(0 if all_clear or (transparent and x<4) else 255)
            pixels.extend((100,80,40,a))
    def chunk(tag,payload):
        return struct.pack(">I",len(payload))+tag+payload+struct.pack(">I",zlib.crc32(tag+payload))
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,6,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes(pixels)))+chunk(b"IEND",b""))


def test_reviewed_t02_mask_real_http_and_negative(tmp_path):
    story=json.loads((ROOT/"contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json").read_text())
    store=ProjectStore(tmp_path/"test.db",tmp_path/"media")
    project=story["project"]["project_id"]
    store.create_project(project,"Synthetic T02 cutout test")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    rev=store.revision(project)
    for claim in story["claims"]:
        if claim["critical"]:
            rev=gates.review_claim(project,claim["claim_id"],"VERIFIED",
                                   "Synthetic G1 fixture, no historical assertions",rev,
                                   "https://www.loc.gov/")
    board=gates.board(project)[0]
    g1=gates.decide(project,"G1",{"decision":"APPROVED","candidate_sha256":board["candidate_sha256"],
        "dependency_fingerprint":board["dependency_fingerprint"],
        "expected_revision":rev,"comment":"Test fixture source only"})
    assert g1["state"]=="APPROVED"
    resolver=AssetResolution(store)
    assets=AssetCandidates(store)
    reviews=[]
    rev=store.revision(project)
    candidates={}
    for requirement in story["asset_requirements"]:
        rid=requirement["requirement_id"]
        rev=resolver.choose(project,rid,"MANUAL_UPLOAD","Synthetic test media",rev)["project_revision"]
        source=assets.manual(project,rid,png(),"Synthetic "+rid,
                             "Synthetic review only","Test-rights note")
        candidates[rid]=source
        reviews.append({"requirement_id":rid,"candidate_id":source["candidate_id"],
                        "original_sha256":source["original_sha256"],
                        "rights_status":"ELIGIBLE",
                        "rights_evidence_note":"Test fixtures owned for software testing",
                        "historical_context_note":"Synthetic—not historical evidence"})
    resolver.approve_batch(project,reviews,store.revision(project))
    board=next(x for x in gates.board(project) if x["gate_id"]=="G3")
    g3=gates.decide(project,"G3",{"decision":"APPROVED",
        "candidate_sha256":board["candidate_sha256"],
        "dependency_fingerprint":board["dependency_fingerprint"],
        "expected_revision":store.revision(project),"comment":"Synthetic G3 test"})
    assert g3["state"]=="APPROVED"
    rid="req_02_portrait_main"
    slot="slot_02_portrait_main"
    candidate=candidates[rid]
    parent_sha=candidate["original_sha256"]
    client=TestClient(create_app(store.database,store.artifacts.root))
    base=f"/api/v1/projects/{project}/assets/{rid}"
    def request(content,revision,key="real-operator-mask"):
        return client.post(base+"/masks/review",headers={"Idempotency-Key":key},json={
            "expected_revision":revision,"slot_id":slot,
            "parent_candidate_id":candidate["candidate_id"],
            "parent_original_sha256":parent_sha,
            "png_base64":base64.b64encode(content).decode(),
            "source_crop":{"x":0,"y":0,"w":1,"h":1},
            "operator_reason":"Synthetic T02 cutout review, no historical claim"})
    before=store.revision(project)
    assert request(png(),before,"opaque-mask").status_code==422
    assert request(png(transparent=True,all_clear=True),before,"empty-mask").status_code==422
    assert request(png(transparent=True)+b"tamper",before,"corrupt-mask").status_code==422
    assert store.revision(project)==before
    reviewed=request(png(transparent=True),before)
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["width"]==8
    assert reviewed.json()["g3_reapproval_required"] is True
    assert store.get_artifact(parent_sha)==png()
    assert resolver.reviewed_mask(project,rid,slot,candidate["candidate_id"]) is None
    board=next(x for x in gates.board(project) if x["gate_id"]=="G3")
    assert board["state"]!="APPROVED"
    response=client.post(f"/api/v1/projects/{project}/gates/G3/decision",
        json={"decision":"APPROVED","candidate_sha256":board["candidate_sha256"],
              "dependency_fingerprint":board["dependency_fingerprint"],
              "expected_revision":reviewed.json()["project_revision"],
              "comment":"Reapproved synthetic G3 mask"},headers={"Idempotency-Key":"g3-mask-reapproval"})
    assert response.status_code==200,response.text
    reread=TestClient(create_app(store.database,store.artifacts.root))
    current=reread.get(base+f"/masks/{slot}/{candidate['candidate_id']}")
    assert current.status_code==200,current.text
    assert current.json()["derivative_sha256"]==reviewed.json()["derivative_sha256"]
    assert rgba_alpha_extent(store.get_artifact(reviewed.json()["derivative_sha256"]))==(8,8)
    assert request(png(transparent=True),before,"stale-mask").status_code==409
