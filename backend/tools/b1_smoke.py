"""B1 real local smoke: normalized artifacts, transformed geometry and audio word sample cues.

Synthetic historical content; no user rights review or live provider claim.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from backend.app.contracts import ContractViolation,validate_document
from backend.app.director.blueprint import normalize_story
from backend.app.director.timing import bind_beats
from backend.app.director.staging import group_staging
from backend.app.maps.ingest import ingest

ROOT=Path(__file__).resolve().parents[2]

def fixture(relative):
    return json.loads((ROOT/relative).read_text(encoding="utf-8"))

def run(case, mode):
    if mode!="local":
        raise ContractViolation("B1_OFFLINE_ONLY",case,
                                "B1 smoke is a synthetic local test; real operators and providers are separate.")
    if case=="normalize-visual":
        story=fixture("contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json")
        authored=fixture("contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json")
        payloads={p["setup_id"]:p["template_payload"] for p in authored["setup_plans"]}
        bp=normalize_story(story,payloads)
        validate_document("VisualBlueprint.v1",bp)
        if (len(bp["setup_plans"])!=10 or
                {p["template_id"] for p in bp["setup_plans"]}!={f"T{i:02d}" for i in range(1,11)} or
                not bp["setup_plans"][2]["editorial_direction"]["visual_beats"] or
                any(b["approved_asset_id"] for p in bp["setup_plans"] for b in p["asset_slot_bindings"])):
            raise RuntimeError("Typed normalized blueprint lost one or more authored templates/beats/draft slots.")
        print("normalize-visual: LOCAL_PASS SYNTHETIC setups=10, SHA="+bp["story_revision_sha256"]+
              ", focus="+bp["setup_plans"][0]["editorial_direction"]["visual_beats"][0]["focus_ref"])
        return
    if case=="historical-map":
        # A reviewed fixture, not verified historical rights. EPSG:3857 -> WGS84.
        merc=lambda lon,lat: [6378137*math.radians(lon),
                 6378137*math.log(math.tan(math.pi/4+math.radians(lat)/2))]
        pts=[merc(*v) for v in [(10,50),(11,50),(11,51),(10,50)]]
        binary=json.dumps({"type":"FeatureCollection","crs":"EPSG:3857",
                          "features":[{"id":"feature_001","type":"Feature",
                                       "geometry":{"type":"Polygon","coordinates":[pts]},
                                       "properties":{}}]}).encode()
        m=fixture("contracts/examples/HistoricalMap.v1.valid.json")
        digest=hashlib.sha256(binary).hexdigest()
        m.update(source_original_sha256=digest,source_crs="EPSG:3857",user_approved=True,
                 source_asset_id="candidate_fixture",rights_review_record_id="approval_fixture",
                 approved_feature_ids=["feature_001"],
                 geography_bbox={"min_lon":9,"min_lat":49,"max_lon":13,"max_lat":53})
        review={"original_sha256":digest,"candidate_id":"candidate_fixture",
                "approval_record_id":"approval_fixture"}
        result=ingest(m,binary,year=1871,feature_ids=["feature_001"],approval=review)
        first=result["features"][0]["geometry"]["coordinates"][0][0]
        if first!=[10.0,50.0] or not result["geometry_sha256"]:
            raise RuntimeError("Map CRS projection produced wrong coordinate or missing geometry fingerprint.")
        try:
            ingest(m,binary,year=1914,feature_ids=["feature_001"],approval=review)
        except ContractViolation as exc:
            if exc.code!="MAP_PERIOD_MISMATCH":raise
        else:
            raise RuntimeError("Modern/wrong-era source was incorrectly accepted.")
        print("historical-map: LOCAL_PASS SYNTHETIC EPSG:3857->4326 lonlat="+str(first)+
              " derived_sha="+result["geometry_sha256"]+" wrong-era=BLOCKED")
        return
    if case=="align-scene-cues":
        story=fixture("contracts/examples/StoryPackage.v1.valid.json")
        authored=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
        bp=normalize_story(story,{"setup_001":authored})
        words=fixture("contracts/examples/WordTimingMap.v1.valid.json")
        # Fixed synthetic native sample offsets, NEVER inferred from WPM.
        windows=bind_beats(bp,words,audio_sha256=words["audio_sha256"],
                           transcript_sha256=words["transcript_sha256"],audio_total_samples=48000)
        staging=group_staging(windows,48000,words["sample_rate"])
        if (len(windows)!=1 or windows[0]["word_ids"]!=["word_001"] or
                (windows[0]["cue_start_frame"],windows[0]["cue_end_frame"])!=(0,9) or
                staging[0]["end_frame"]!=30):
            raise RuntimeError("Aligned phrase/sample-to-frame or scene-local boundary mismatch.")
        from backend.app.director.timing import resolve_cue
        try:resolve_cue({"section_id":"sec_001","phrase":"In","occurrence":10},words,"beat_setup_001")
        except ContractViolation as exc:
            if exc.code!="CUE_OCCURRENCE_INVALID":raise
        else:raise RuntimeError("Out-of-range repeated cue must block.")
        print("align-scene-cues: LOCAL_PASS SYNTHETIC word_id=word_001 cue_frames=[0,9) scene_frames=[0,30)")
        return
    raise ContractViolation("B1_SMOKE_CASE_UNKNOWN",case,"Use one of the three B1 cases.")
