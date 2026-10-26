"""Controlled current G4 SQLite fixture for B2 Player/Node host ingress tests.
All rights and evidence here are SYNTHETIC_TEST_ONLY, never operator/live.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from backend.app.projects.storage import ProjectStore
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.jobs.queue import JobQueue
from backend.app.voice.attempts import VoiceService
from backend.app.voice import attempts
from backend.app.voice.workflow import FinalVoiceWorkflow
from backend.tools.voice_final_smoke import wav_fixture, mock_alignment
from backend.app.director.blueprint import normalize_story
from backend.app.director.compiler import compile_from_store
from backend.app.director.layout import windows_font_measure

ROOT=Path(__file__).resolve().parents[2]
def load(name):return json.loads((ROOT/name).read_text(encoding="utf-8"))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--scene-count",type=int,default=2)
    args=parser.parse_args()
    if args.scene_count < 2 or args.scene_count > 120:
        raise ValueError("B2_SYNTHETIC_SCENE_COUNT_INVALID")
    if os.name!="nt":
        raise RuntimeError("APPROVED_PLAYER_TEST_FIXTURE_REQUIRES_NATIVE_WINDOWS")
    out=ROOT/"renderer"/".artifacts"/("approved-player-test-longform" if args.scene_count>2
                                      else "approved-player-test")
    # Controlled generated fixture, never operator data. Owner commands must
    # be repeatable without inheriting an earlier SQLite approval head.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True,exist_ok=True)
    story=load("contracts/examples/StoryPackage.v1.valid.json")
    # Source claim is present in G1; pin that existing claim to its authored
    # map headline before the controlled G1 import/approval (not at render time).
    story["visual_setups"][0]["direction"]["on_screen_text"][0]["claim_ref"]="claim_001"
    second=copy.deepcopy(story["visual_setups"][0])
    second["setup_id"]="setup_002"
    second["direction"]["visual_beats"][0]["beat_id"]="beat_setup_002"
    second["direction"]["visual_beats"][0]["cue"]={"section_id":"sec_001","phrase":"the","occurrence":0}
    second["direction"]["visual_beats"][0]["continuity"]["group_id"]="group_setup_002"
    second["direction"]["reveal_plan"][0]["beat_id"]="beat_sec_002"
    second["direction"]["reveal_plan"][0]["cue"]={"section_id":"sec_001","phrase":"the","occurrence":0}
    story["visual_setups"].append(second)
    if args.scene_count > 2:
        # Synthetic only: reuse the same sourced T01 layout, but bind 61 distinct
        # cue occurrences against an actually longer controlled G2 transcript.
        story["sections"][0]["narration"] = " ".join(
            ["In 1871, the German Empire was proclaimed."] * args.scene_count)
        original=story["visual_setups"][0]
        story["visual_setups"]=[original]
        for i in range(args.scene_count):
            setup=original if i==0 else copy.deepcopy(original)
            setup_id=f"setup_{i+1:03d}"
            setup["setup_id"]=setup_id
            cue={"section_id":"sec_001","phrase":"In","occurrence":i}
            beat=setup["direction"]["visual_beats"][0]
            beat["beat_id"]="beat_"+setup_id
            beat["cue"]=dict(cue)
            beat["continuity"]["group_id"]="group_"+setup_id
            reveal=setup["direction"]["reveal_plan"][0]
            reveal["beat_id"]="reveal_"+setup_id
            reveal["cue"]=dict(cue)
            if i:
                story["visual_setups"].append(setup)
    pid=story["project"]["project_id"]
    store=ProjectStore(out/"g4.sqlite",out/"artifacts")
    store.create_project(pid,"Synthetic authorized-source test only")
    store.import_story(StoryCandidate.parse(story),0)
    gate=GateService(store)
    def approve(gid):
        head=next(g for g in gate.board(pid) if g["gate_id"]==gid)
        gate.decide(pid,gid,{"decision":"APPROVED","candidate_sha256":head["candidate_sha256"],
            "dependency_fingerprint":head["dependency_fingerprint"],"expected_revision":store.revision(pid)})
    approve("G1")
    voice=VoiceService(store,gate,JobQueue(store))
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"synthetic"}):
        voice.enqueue(pid,"sec_001","kokoro_local","am_adam",1.0,
            "Synthetic local test",store.revision(pid),"test_b2_player_001")
        voice_result=voice.process_one(lambda *_:wav_fixture(150.0 if args.scene_count>2 else 4.0))
        assert voice_result and voice_result["state"]=="SUCCEEDED",voice_result
    approve("G2")
    workflow=FinalVoiceWorkflow(store,gate,JobQueue(store))
    assert workflow.process_one()["state"]=="SUCCEEDED"
    frozen=workflow.status(pid)["final_audio"]
    assert workflow.process_one(lambda audio,text:mock_alignment(frozen,text))["state"]=="SUCCEEDED"
    words=workflow.status(pid)["word_map"]
    resolver=AssetResolution(store)
    resolver.choose(pid,"req_001","MANUAL_UPLOAD","Synthetic original",store.revision(pid))
    image=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC")
    candidate=AssetCandidates(store).manual(pid,"req_001",image,"Synthetic raster map",
        "Synthetic 1871","Test rights—not live")
    review=resolver.approve_batch(pid,[{"requirement_id":"req_001","candidate_id":candidate["candidate_id"],
        "original_sha256":candidate["original_sha256"],"rights_status":"ELIGIBLE",
        "rights_evidence_note":"Controlled synthetic-only review","historical_context_note":"Synthetic map"}],
        store.revision(pid))
    approve("G3")
    record=load("contracts/examples/HistoricalMap.v1.valid.json")
    record.update(source_asset_id=candidate["candidate_id"],
        source_original_sha256=candidate["original_sha256"],
        raster_asset_sha256=candidate["original_sha256"],geometry_format="RASTER",
        geography_mode="raster_georeferenced",geometry_object_sha256=None,
        approved_feature_ids=[],labels=[],user_approved=True,
        rights_review_record_id=review["approved"][0]["approval_record_id"])
    authored=load("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    blueprint=normalize_story(story,{setup["setup_id"]:authored for setup in story["visual_setups"]})
    font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
    compile_from_store(store,pid,blueprint,words,frozen,
        map_requests={"req_001":{"year":1871,"map_record":record,"feature_ids":[]}},
        font_measure=measure,font_identity=identity)
    config={"db":str(out/"g4.sqlite"),"artifactRoot":str(out/"artifacts"),
        "project":pid,"source":"SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS"}
    (ROOT/"renderer"/".artifacts"/("approved-player-test-longform.json" if args.scene_count>2
        else "approved-player-test.json")).write_text(json.dumps(config),encoding="utf-8")
    print(json.dumps({"status":"LOCAL_PASS","kind":config["source"],"project":pid}))
if __name__=="__main__":main()
