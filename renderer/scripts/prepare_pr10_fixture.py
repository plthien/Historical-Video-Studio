"""PR10 native Windows source-authority fixtures.

All approvals are explicit G1/G3 or auxiliary source-review transactions
on SYNTHETIC projects. None certifies a genuine historical claim or image.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import os
import shutil
import struct
import zlib
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.projects.storage import ProjectStore
from backend.app.projects.gates import GateService
from backend.app.jobs.queue import JobQueue
from backend.app.voice.attempts import VoiceService
from backend.app.voice import attempts
from backend.app.voice.workflow import FinalVoiceWorkflow
from backend.tools.voice_final_smoke import wav_fixture,mock_alignment
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.director.blueprint import normalize_story
from backend.app.director.compiler import compile_from_store
from backend.app.director.motion import presets
from backend.app.director.timing import bind_beats
from backend.app.director.staging import group_staging
from backend.app.director.layout import windows_font_measure
from backend.app.director.fingerprint import canonical

ROOT=Path(__file__).resolve().parents[2]
def load(path):return json.loads((ROOT/path).read_text(encoding="utf-8"))
def png(color=(120,50,10),cutout=False):
    w=h=8
    data=bytearray()
    for y in range(h):
        data.append(0)
        for x in range(w):
            data.extend((*color,0 if cutout and x<4 else 255))
    def chunk(tag,payload):
        return struct.pack(">I",len(payload))+tag+payload+struct.pack(">I",zlib.crc32(tag+payload))
    return (b"\x89PNG\r\n\x1a\n"+
        chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,6,0,0,0))+
        chunk(b"IDAT",zlib.compress(bytes(data)))+chunk(b"IEND",b""))


def prepare(mode:str):
    assert os.name=="nt","PR10_NATIVE_WINDOWS_REQUIRED"
    out=ROOT/"renderer"/".artifacts"/("pr10-"+mode)
    if out.exists():shutil.rmtree(out)
    out.mkdir(parents=True)
    all_story=load("contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json")
    all_bp=load("contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json")
    template={"numeric":"T08","mask":"T02","typography":"T06"}[mode]
    setup=copy.deepcopy(next(s for s in all_story["visual_setups"] if s["preferred_template"]==template))
    payload=copy.deepcopy(next(s["template_payload"] for s in all_bp["setup_plans"] if s["template_id"]==template))
    story=copy.deepcopy(all_story)
    story["project"]["project_id"]="proj_pr10_"+mode
    story["project"]["title"]="SYNTHETIC PR10 "+mode+" TEST—not a historical claim"
    secids=set(setup["section_refs"])
    claimids=set(setup["claim_refs"])
    reqids=set(setup["requirement_refs"])
    story["visual_setups"]=[setup]
    story["sections"]=[x for x in story["sections"] if x["section_id"] in secids]
    story["claims"]=[x for x in story["claims"] if x["claim_id"] in claimids]
    story["asset_requirements"]=[x for x in story["asset_requirements"] if x["requirement_id"] in reqids]
    # Standalone synthetic fixtures need strictly ordered, distinct source-word cues.
    # The canonical multi-template example reuses occurrence=0 for a visual
    # demonstration; it is not a valid successive beat boundary in G2 timing.
    beats=setup["direction"]["visual_beats"]
    if len(beats)>=3 and beats[1]["cue"]["phrase"]==beats[2]["cue"]["phrase"]:
        beats[2]["cue"]["occurrence"]=1
    claim=story["claims"][0]["claim_id"]
    story["claims"][0]["source_leads"]=[{"url":"https://example.org/synthetic-test-only","title":"Synthetic fixture—not historical evidence"}]
    story["claims"][0]["text"]="SYNTHETIC TEST SOURCE — numeric/mask renderer mechanics only"
    if mode=="numeric":
        payload["animation_rule"]="count_if_intermediates_truthful"
        payload["display_value"]="1914"
        for text in setup["direction"]["on_screen_text"]:
            if text["text_id"]==payload["fact_text_id"]:text["text"]="1914"
    elif mode=="mask":
        payload["cutout_policy"]="use_reviewed_mask"
        for text in setup["direction"]["on_screen_text"]:
            if text["text_id"]==payload["role_text_id"]:
                text["text"]="SYNTHETIC PORTRAIT. ORIGINAL PHOTO RIGHTS AND TRANSPARENT CUTOUT ARE REVIEWED SEPARATELY."
            elif text["text_id"]==payload["name_text_id"]:
                text["text"]="SYNTHETIC PERSON: SOURCE REVIEWED"
    elif mode=="typography":
        for text in setup["direction"]["on_screen_text"]:
            if text["text_id"]==payload["excerpt_text_id"]:
                text["text"]="SYNTHETIC DOCUMENT EXCERPT.\nThis second sourced line must remain fully visible."
            elif text["text_id"]==payload["attribution_text_id"]:
                text["text"]="SYNTHETIC SOURCE ONLY — NO HISTORICAL RIGHTS OR CLAIMS."
    pid=story["project"]["project_id"]
    client=TestClient(create_app(out/"g4.sqlite",out/"artifacts"))
    store=ProjectStore(out/"g4.sqlite",out/"artifacts")
    store.create_project(pid,story["project"]["title"])
    def post(route,body,key):
        response=client.post(f"/api/v1/projects/{pid}"+route,json=body,
                             headers={"Idempotency-Key":key})
        assert response.status_code==200,(route,response.status_code,response.text)
        return response.json()
    imported=post("/story/import?expected_revision=0",story,mode+"-story-import")
    review=post(f"/story/claims/{claim}/review",{
        "status":"VERIFIED","evidence_note":"Synthetic reviewed fixture, no historical validity",
        "source_url":"https://example.org/synthetic-test-only",
        "expected_revision":imported["project_revision"]},mode+"-claim-review")
    gate=GateService(store)
    def approve(which):
        head=next(g for g in client.get(f"/api/v1/projects/{pid}/gates").json() if g["gate_id"]==which)
        return post(f"/gates/{which}/decision",{"decision":"APPROVED",
            "candidate_sha256":head["candidate_sha256"],
            "dependency_fingerprint":head["dependency_fingerprint"],
            "expected_revision":store.revision(pid),
            "comment":"SYNTHETIC source mechanics only"},mode+"-approve-"+which+"-rev-"+str(store.revision(pid)))
    g1=approve("G1")
    voice=VoiceService(store,gate,JobQueue(store))
    sec=story["sections"][0]["section_id"]
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"synthetic"}):
        voice.enqueue(pid,sec,"kokoro_local","am_adam",1.0,
                      "Synthetic local audio",store.revision(pid),"pr10-voice-"+mode)
        result=voice.process_one(lambda *_:wav_fixture(12.0))
        assert result and result["state"]=="SUCCEEDED",result
    # G2's HTTP handler runs the entire queue as a TestClient background task.
    # For deterministic synthetic forced-alignment evidence, use the same real
    # GateService approval transaction without auto-consuming the queued job.
    g2_head=next(g for g in gate.board(pid) if g["gate_id"]=="G2")
    g2=gate.decide(pid,"G2",{"decision":"APPROVED",
        "candidate_sha256":g2_head["candidate_sha256"],
        "dependency_fingerprint":g2_head["dependency_fingerprint"],
        "expected_revision":store.revision(pid),
        "comment":"SYNTHETIC source mechanics only"})
    assert g2["state"]=="APPROVED"
    workflow=FinalVoiceWorkflow(store,gate,JobQueue(store))
    assert workflow.process_one()["state"]=="SUCCEEDED"
    frozen=workflow.status(pid)["final_audio"]
    assert workflow.process_one(lambda audio,text:mock_alignment(frozen,text))["state"]=="SUCCEEDED"
    word_map=workflow.status(pid)["word_map"]
    resolver=AssetResolution(store)
    sources={}
    selection=None
    mask_events=[]
    if mode=="mask":
        req=story["asset_requirements"][0]["requirement_id"]
        slot=setup["direction"]["asset_slots"][0]["slot_id"]
        resolver.choose(pid,req,"MANUAL_UPLOAD","Synthetic original",store.revision(pid))
        assets=AssetCandidates(store)
        a=assets.manual(pid,req,png((190,30,30)),"SYNTHETIC RED A",
                        "Synthetic only","Test rights only")
        b=assets.manual(pid,req,png((25,30,190)),"SYNTHETIC BLUE B",
                        "Synthetic only","Test rights only")
        def review_item(x):
            return {"requirement_id":req,"candidate_id":x["candidate_id"],
                    "original_sha256":x["original_sha256"],"rights_status":"ELIGIBLE",
                    "rights_evidence_note":"Owned synthetic source only",
                    "historical_context_note":"No historical provenance—software fixture"}
        resolver.approve_batch(pid,[review_item(a)],store.revision(pid))
        approve("G3")
        selection=post(f"/assets/{req}/choice-sets/review",{
            "expected_revision":store.revision(pid),"slot_id":slot,
            "reviews":[review_item(a),review_item(b)],
            "operator_reason":"Synthetic G3 A/B test only"},mode+"-review-options")
        for item in (a,b):
            original=png((190,30,30)) if item is a else png((25,30,190))
            response=post(f"/assets/{req}/masks/review",{
                "expected_revision":store.revision(pid),"slot_id":slot,
                "parent_candidate_id":item["candidate_id"],
                "parent_original_sha256":item["original_sha256"],
                "png_base64":base64.b64encode(png(cutout=True)).decode(),
                "source_crop":{"x":0,"y":0,"w":1,"h":1},
                "operator_reason":"SYNTHETIC T02 source-only cutout approval"},mode+"-review-mask-"+item["candidate_id"])
            mask_events.append(response)
        g3=approve("G3")
        sources={"requirement_id":req,"slot_id":slot,
                 "a":a,"b":b,"g3_approval":g3}
    elif mode=="typography":
        req=story["asset_requirements"][0]["requirement_id"]
        resolver.choose(pid,req,"MANUAL_UPLOAD","Synthetic document original",store.revision(pid))
        document=AssetCandidates(store).manual(pid,req,png((210,170,120)),
                    "SYNTHETIC T06 document","No real historical document",
                    "Synthetic fixture owned for tests")
        resolver.approve_batch(pid,[{
            "requirement_id":req,"candidate_id":document["candidate_id"],
            "original_sha256":document["original_sha256"],
            "rights_status":"ELIGIBLE","rights_evidence_note":"Synthetic owned fixture",
            "historical_context_note":"Test only; no real history"}],store.revision(pid))
        sources={"requirement_id":req,"document":document,"g3_approval":approve("G3")}
    else:
        approve("G3")
    blueprint=normalize_story(story,{setup["setup_id"]:payload})
    if mode=="numeric":
        windows=bind_beats(blueprint,word_map,
                           audio_sha256=frozen["audio_sha256"],
                           transcript_sha256=frozen["transcript_sha256"],
                           audio_total_samples=frozen["duration_samples"])
        groups=group_staging(windows,frozen["duration_samples"],word_map["sample_rate"])
        stage=next(x for x in groups if x["setup_id"]==setup["setup_id"])
        beat=next(x for x in windows if x["setup_id"]==setup["setup_id"])
        origin=beat["start_frame"]-stage["start_frame"]
        event_at=max(origin,beat["cue_start_frame"]-stage["start_frame"])
        length=min(beat["end_frame"]-stage["start_frame"]-event_at,
                   presets()["number-count"]["default_duration_frames"],
                   presets()["number-count"]["max_duration_frames"])
        assert length>=2,("NUMERIC_BOUNDS",length)
        evidence=post(f"/story/claims/{claim}/numeric-series/evidence",{
            "expected_revision":store.revision(pid),
            "content_base64":base64.b64encode(
                b"SYNTHETIC TEST ONLY. Fictional 0,957,1914 observations - NOT historical evidence.").decode(),
            "source_url":"https://example.org/synthetic-test-only",
            "review_note":"SYNTHETIC source used only to prove visual counting mechanics"},
            mode+"-numeric-evidence")
        numeric=post(f"/story/claims/{claim}/numeric-series/approve",{
            "expected_revision":store.revision(pid),"series_id":"synthetic_count_1914",
            "frozen_story_sha256":store.get_story(pid).sha256,
            "g1_approval_id":g1["approval_id"],
            "unit":"synthetic_units","precision":0,
            "authored_duration_frames":length,"start_value":"0","end_value":"1914",
            "observations":[{"frame_offset":at,"value":value,
                             "source_evidence_sha256":evidence["source_evidence_sha256"]}
                for at,value in ((0,"0"),(max(1,length//2),"957"),(length,"1914"))],
            "operator_reason":"Explicit synthetic value approval—not a historical claim"},
            mode+"-numeric-approve")
        assert numeric["approval_id"]
    font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
    timeline=compile_from_store(store,pid,blueprint,word_map,frozen,
                                font_measure=measure,font_identity=identity)
    if mode=="numeric":
        events=[x for s in timeline["scenes"] for x in s["events"] if x["preset_id"]=="number-count"]
        assert len(events)==1 and events[0]["params"]["approved_numeric_series_id"]=="synthetic_count_1914"
    elif mode=="mask":
        layers=[x for s in timeline["scenes"] for x in s["layers"] if x["mask"]["kind"]=="polygon_asset"]
        assert len(layers)==1
    else:
        texts=[x for s in timeline["scenes"] for x in s["layers"] if x["text"] is not None]
        assert any("SYNTHETIC DOCUMENT EXCERPT" in x["text"] for x in texts)
    config={"mode":mode,"project":pid,"db":str(store.database),
            "artifactRoot":str(store.artifacts.root),
            "source":"SYNTHETIC_G1_G2_G3_OPERATOR_TRANSACTIONS_NOT_REAL_HISTORY",
            "g1_approval_id":g1["approval_id"],"g3":sources,
            "numeric_approval":numeric if mode=="numeric" else None,
            "mask_reviews":mask_events,"choice_set":selection}
    (ROOT/"renderer"/".artifacts"/("pr10-"+mode+".json")).write_bytes(canonical(config))
    print(json.dumps({"status":"LOCAL_PASS","kind":config["source"],
                      "mode":mode,"project":pid,"timeline_frames":timeline["total_frames"]}))
    return config


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",choices=["numeric","mask","typography"],required=True)
    prepare(parser.parse_args().case)
