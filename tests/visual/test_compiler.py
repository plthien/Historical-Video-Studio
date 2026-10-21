"""B1-01..03 behavioral regression: canonical fixtures, exact outputs, fail-closed negatives."""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import pytest

from backend.app.contracts import ContractViolation,validate_document,validate_visual_blueprint
from backend.app.projects.models import StoryCandidate
from backend.app.director.blueprint import normalize_story
from backend.app.director.timing import bind_beats,resolve_cue,sample_to_frames
from backend.app.director.staging import group_staging
from backend.app.maps.ingest import ingest
from backend.app.maps.projection import project,common_viewport

ROOT=Path(__file__).resolve().parents[2]
def fixture(p):
    return json.loads((ROOT/p).read_text(encoding="utf-8"))
def visual():
    story=fixture("contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json")
    authored=fixture("contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json")
    return story,{p["setup_id"]:p["template_payload"] for p in authored["setup_plans"]}

def test_blueprint_ten_templates_immutable_refs_and_30_layouts():
    story,payloads=visual()
    norm=normalize_story(story,payloads)
    validate_visual_blueprint(story,norm)
    assert len(norm["setup_plans"])==10
    assert {p["template_id"] for p in norm["setup_plans"]}=={f"T{i:02d}" for i in range(1,11)}
    assert norm["story_revision_sha256"]==StoryCandidate.parse(story).sha256
    assert all(b["approved_asset_id"] is None for p in norm["setup_plans"] for b in p["asset_slot_bindings"])
    assert [p["setup_id"] for p in norm["setup_plans"]]==[s["setup_id"] for s in story["visual_setups"]]
    assert normalize_story(story,payloads)==norm
    registry=fixture("contracts/registries/layouts.v1.json")["layouts"]
    assert len({(x["template_id"],x["variant_id"]) for x in registry})==30
    for variant in ("A","B","C"):
        selected={s["setup_id"]:variant for s in story["visual_setups"]}
        plans=normalize_story(story,payloads,selected_variants=selected)["setup_plans"]
        assert {p["variant_id"] for p in plans}=={variant}

@pytest.mark.parametrize("change,code",[
    ("unknown_focus","FOCUS"),
    ("unknown_group","CONTINUITY"),
    ("missing_payload","TEMPLATE_PAYLOAD_MISSING"),
    ("collage_order","COLLAGE_ORDER_INVALID"),
    ("collage_hero","COLLAGE_HERO_INVALID"),
    ("quote_verbatim","QUOTE_SOURCE_NOT_VERIFIED"),
    ("quote_t09","QUOTE_SOURCE_NOT_VERIFIED"),
    ("map_pair","MAP_PAIR_NOT_DISTINCT"),
    ("unknown_claim","TEMPLATE_CLAIM_MISSING"),
    ("geo_editorial","EDITORIAL_ROUTE_INVALID"),
])
def test_payload_role_negative_fail_closed(change,code):
    story,payloads=visual()
    s=story["visual_setups"][0]
    if change=="unknown_focus":s["direction"]["visual_beats"][0]["focus_ref"]="never_declared"
    elif change=="unknown_group":s["direction"]["visual_beats"][0]["continuity"]["carry_refs"]=["unknown_slot"]
    elif change=="missing_payload":payloads.pop(s["setup_id"])
    elif change=="collage_order":
        p=payloads["setup_03"];p["card_reveal_order"]=[p["card_reveal_order"][0]]*2
    elif change=="collage_hero":
        payloads["setup_03"]["cards"][0]["card_role"]="supporting"
    elif change=="quote_verbatim":
        payloads["setup_06"]["excerpt_kind"]="verbatim_verified"
    elif change=="quote_t09":
        payloads["setup_09"]["quote_kind"]="verbatim_verified"
    elif change=="map_pair":
        payloads["setup_07"]["after_map"]=copy.deepcopy(payloads["setup_07"]["before_map"])
    elif change=="unknown_claim":payloads["setup_01"]["map"]["label_source_claim_refs"]=["ghost_claim"]
    elif change=="geo_editorial":payloads["setup_10"]["route_geometry_ref"]="modern_roads"
    with pytest.raises(ContractViolation) as ex:normalize_story(story,payloads)
    assert code in ex.value.code or code in str(ex.value),str(ex.value)

def test_blueprint_source_sha_must_match():
    story,payloads=visual()
    with pytest.raises(ContractViolation,match="STORY_SHA_MISMATCH"):
        normalize_story(story,payloads,expected_story_sha256="0"*64)

def example_map(source, *, period=(1871,1871), projection="mercator", crs="EPSG:3857"):
    base=fixture("contracts/examples/HistoricalMap.v1.valid.json")
    base.update(source_original_sha256=hashlib.sha256(source).hexdigest(),
                valid_year_from=period[0],valid_year_to=period[1],
                source_crs=crs,map_projection=projection,user_approved=True,
                geometry_object_sha256=None,
                rights_review_record_id="approval_fixture_map",
                source_asset_id="candidate_fixture_map",
                approved_feature_ids=["feature_001"],
                geography_bbox={"min_lon":9,"min_lat":49,"max_lon":13,"max_lat":53})
    return base,dict(original_sha256=base["source_original_sha256"],
                    candidate_id="candidate_fixture_map",
                    approval_record_id="approval_fixture_map")

def vector_sample():
    # EPSG:3857 projected rectangle around approx lon=10,lat=50.
    def merc(lon,lat):
        return [6378137*math.radians(lon),
                6378137*math.log(math.tan(math.pi/4+math.radians(lat)/2))]
    points=[merc(a,b) for a,b in [(10,50),(11,50),(11,51),(10,50)]]
    source={"type":"FeatureCollection","crs":"EPSG:3857",
            "features":[{"id":"feature_001","type":"Feature",
                         "geometry":{"type":"Polygon","coordinates":[points]},"properties":{}}]}
    return json.dumps(source,separators=(",",":")).encode()

def test_map_projection_period_sha_and_feature_lineage():
    source=vector_sample();m,approval=example_map(source)
    result=ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
    assert result["coordinate_space"]=="EPSG:4326"
    first=result["features"][0]["geometry"]["coordinates"][0][0]
    assert first==[10.0,50.0]
    assert result["source_original_sha256"]==hashlib.sha256(source).hexdigest()
    assert result["geometry_sha256"]==result["historical_map"]["geometry_object_sha256"]
    assert result["geometry_sha256"]==ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)["geometry_sha256"]
    with pytest.raises(ContractViolation,match="MAP_GEOMETRY_SHA_MISMATCH"):
        ingest({**m,"geometry_object_sha256":"a"*64},source,year=1871,
               feature_ids=["feature_001"],approval=approval)
    assert result["projected"][0]["points"]
    assert project(10,50,"mercator")==project(10,50,"mercator")
    newer=copy.deepcopy(m);newer["historical_map_id"]="map_1872"
    newer["valid_year_from"]=1872;newer["valid_year_to"]=1872
    vp=common_viewport(m,newer)
    assert vp["map_ids"]==["map_1871","map_1872"] and vp["projection"]=="mercator"

@pytest.mark.parametrize("mode,expected",[
    ("year","MAP_PERIOD_MISMATCH"),
    ("crs","MAP_CRS_UNSUPPORTED"),
    ("feature","MAP_FEATURE_UNKNOWN"),
    ("rights","MAP_RIGHTS_UNREVIEWED"),
    ("sha","MAP_RIGHTS_UNREVIEWED"),
    ("topology","MAP_GEOMETRY_INVALID"),
    ("antimeridian","MAP_GEOMETRY_INVALID"),
    ("selfcross","MAP_GEOMETRY_INVALID"),
])
def test_map_invalid_source_never_geographic_fallback(mode,expected):
    source=vector_sample();m,approval=example_map(source)
    year=1871;features=["feature_001"]
    if mode=="year":year=1914
    elif mode=="crs":m["source_crs"]="UNKNOWN";source=source.replace(b"EPSG:3857",b"UNKNOWN");m["source_original_sha256"]=hashlib.sha256(source).hexdigest();approval["original_sha256"]=m["source_original_sha256"]
    elif mode=="feature":features=["missing_feature"]
    elif mode=="rights":approval["approval_record_id"]="not_reviewed"
    elif mode=="sha":source+=b" "
    elif mode in ("topology","antimeridian","selfcross"):
        raw=json.loads(source)
        raw["crs"]="EPSG:4326";m["source_crs"]="EPSG:4326"
        if mode=="topology":
            pts=[[10,50],[10,50],[10,50],[10,50]]
        elif mode=="selfcross":
            vertex=[(11+math.cos(2*math.pi*i/5),51+math.sin(2*math.pi*i/5)) for i in range(5)]
            pts=[list(vertex[i]) for i in (0,2,4,1,3,0)]
        else:
            pts=[[179,50],[-179,50],[-179,51],[179,50]]
        raw["features"][0]["geometry"]["coordinates"]=[pts]
        source=json.dumps(raw).encode()
        m["source_original_sha256"]=hashlib.sha256(source).hexdigest()
        approval["original_sha256"]=m["source_original_sha256"]
    with pytest.raises(ContractViolation,match=expected):
        ingest(m,source,year=year,feature_ids=features,approval=approval)

def test_map_raster_without_tiepoints_stays_uv_only():
    source=b"synthetic-raster-byte-fixture";m,approval=example_map(source,crs="EPSG:4326")
    m.update(geometry_format="RASTER",geography_mode="raster_georeferenced",
             geometry_object_sha256=None,raster_asset_sha256=hashlib.sha256(source).hexdigest())
    # Absence of reviewed georeferencing does not turn pixels into lat/lon.
    with pytest.raises(ContractViolation,match="MAP_GEOREFERENCE_REQUIRED"):
        ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
    ok=ingest(m,source,year=1871,feature_ids=[],approval=approval)
    assert ok["coordinate_space"]=="UV_ONLY" and ok["features"]==[]

def test_cue_repeated_phrase_exact_sample_frames_and_staging():
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    src=fixture("contracts/examples/VisualBlueprint.v1.valid.json")
    blueprint=normalize_story(story,{"setup_001":src["setup_plans"][0]["template_payload"]})
    wav=fixture("contracts/examples/WordTimingMap.v1.valid.json")
    # Native WordTimingMap schema, not freeform WPM estimate.
    wav["words"]=[
        {"word_id":f"word_{i:03d}","section_id":"sec_001","text":text,
         "start_sample":start,"end_sample":end}
        for i,(text,start,end) in enumerate([
            ("In",1,151),("1871",155,1001),("In",1501,1802),("1871",1803,2600),
            ("In",3001,3499),("1871",3501,4101)])]
    validate_document("WordTimingMap.v1",wav)
    c={"section_id":"sec_001","phrase":"In 1871","occurrence":2}
    match=resolve_cue(c,wav,"beat_setup_001")
    assert match["word_ids"]==["word_004","word_005"]
    assert sample_to_frames(3001,4101,48000)==(1,3)
    bp=blueprint["setup_plans"][0]["editorial_direction"]["visual_beats"][0]
    bp["cue"]=c
    windows=bind_beats(blueprint,wav,audio_sha256=wav["audio_sha256"],
                       transcript_sha256=wav["transcript_sha256"],audio_total_samples=48001)
    assert windows[0]["cue_start_frame"]==1 and windows[0]["cue_end_frame"]==3
    assert windows[0]["end_frame"]==31
    assert group_staging(windows,48001,48000)[0]["focus_sequence"][0]["word_ids"]==["word_004","word_005"]
    with pytest.raises(ContractViolation,match="CUE_OCCURRENCE_INVALID"):
        resolve_cue({**c,"occurrence":3},wav,"beat_setup_001")
    with pytest.raises(ContractViolation,match="CUE_AMBIGUOUS"):
        resolve_cue({**c,"occurrence":None},wav,"beat_setup_001")
    with pytest.raises(ContractViolation,match="ALIGNMENT_SOURCE_STALE"):
        bind_beats(blueprint,wav,audio_sha256="0"*64,
                   transcript_sha256=wav["transcript_sha256"],audio_total_samples=48001)
    with pytest.raises(ContractViolation,match="ALIGNMENT_TIME_INVALID"):
        bind_beats(blueprint,wav,audio_sha256=wav["audio_sha256"],
                   transcript_sha256=wav["transcript_sha256"],audio_total_samples=3000)

def test_timing_missing_cue_or_wrong_section():
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    payload=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    bp=normalize_story(story,{"setup_001":payload})
    wav=fixture("contracts/examples/WordTimingMap.v1.valid.json")
    beat=bp["setup_plans"][0]["editorial_direction"]["visual_beats"][0]
    beat["cue"]["phrase"]="never-spoken"
    with pytest.raises(ContractViolation,match="CUE_MISSING"):
        bind_beats(bp,wav,audio_sha256=wav["audio_sha256"],
                   transcript_sha256=wav["transcript_sha256"],audio_total_samples=47000)
    beat["cue"]["phrase"]="In"
    beat["cue"]["section_id"]="sec_missing"
    with pytest.raises(ContractViolation,match="CUE_SECTION_MISMATCH"):
        bind_beats(bp,wav,audio_sha256=wav["audio_sha256"],
                   transcript_sha256=wav["transcript_sha256"],audio_total_samples=47000)


def test_timing_scene_cuts_follow_global_sample_boundaries_without_frame_overlap():
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    authored=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    bp=normalize_story(story,{"setup_001":authored})
    other=copy.deepcopy(bp["setup_plans"][0]["editorial_direction"]["visual_beats"][0])
    other["beat_id"]="beat_second"
    other["cue"]={"section_id":"sec_001","phrase":"1871,","occurrence":0}
    bp["setup_plans"][0]["editorial_direction"]["visual_beats"].append(other)
    wav=fixture("contracts/examples/WordTimingMap.v1.valid.json")
    windows=bind_beats(bp,wav,audio_sha256=wav["audio_sha256"],
                       transcript_sha256=wav["transcript_sha256"],audio_total_samples=48000)
    assert len(windows)==2
    assert windows[0]["end_frame"]==windows[1]["start_frame"]==10
    assert windows[-1]["end_frame"]==30
    assert sum(w["duration_frames"] for w in windows)==30


def test_map_raster_reviewed_three_point_georeference_and_wrong_rights_rejected():
    source=b"synthetic-period-raster";m,approval=example_map(source,crs="EPSG:4326")
    m.update(geometry_format="RASTER",geography_mode="raster_georeferenced",
             geometry_object_sha256=None,raster_asset_sha256=hashlib.sha256(source).hexdigest())
    ties=[{"u":u,"v":v,"lon":lon,"lat":lat,
           "source_original_sha256":hashlib.sha256(source).hexdigest(),
           "rights_review_record_id":"approval_fixture_map","user_approved":True}
          for u,v,lon,lat in [(0,0,10,50),(1,0,11,50),(0,1,10,51)]]
    result=ingest(m,source,year=1871,feature_ids=[],approval=approval,
                  reviewed_tie_points=ties)
    assert result["coordinate_space"]=="REVIEWED_RASTER_UV_TO_GEO"
    assert result["georeference"]["uv_lon_coefficients"]==(1.0,0.0,10.0)
    assert result["geometry_sha256"]
    ties[1]["user_approved"]=False
    with pytest.raises(ContractViolation,match="MAP_GEOREFERENCE_REQUIRED"):
        ingest(m,source,year=1871,feature_ids=[],approval=approval,
               reviewed_tie_points=ties)


def test_map_real_local_g3_original_and_approval_lineage(tmp_path):
    """B1-02 integration: no user-approved boolean can replace a G3 SQLite head."""
    import base64
    from backend.app.projects.storage import ProjectStore
    from backend.app.projects.gates import GateService
    from backend.app.assets.provenance import AssetCandidates
    from backend.app.assets.resolution import AssetResolution
    from backend.app.maps.ingest import ingest_current_approved
    original=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC")
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    pid=story["project"]["project_id"];rid="req_001"
    store.create_project(pid,"Reviewed raster fixture")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    resolver=AssetResolution(store)
    resolver.choose(pid,rid,"MANUAL_UPLOAD","Operator reviewed synthetic PNG",store.revision(pid))
    asset=AssetCandidates(store).manual(pid,rid,original,"Fixture map","Synthetic period","Synthetic source rights")
    reviewed=resolver.approve_batch(pid,[{"requirement_id":rid,"candidate_id":asset["candidate_id"],
        "original_sha256":asset["original_sha256"],"rights_status":"ELIGIBLE",
        "rights_evidence_note":"SYNTHETIC review","historical_context_note":"SYNTHETIC 1871 map"}],
        store.revision(pid))
    assert gates.board(pid)[2]["state"]=="READY_FOR_REVIEW"
    g3=gates.board(pid)[2]
    gates.decide(pid,"G3",{"decision":"APPROVED",
        "candidate_sha256":g3["candidate_sha256"],
        "dependency_fingerprint":g3["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    map_record=fixture("contracts/examples/HistoricalMap.v1.valid.json")
    map_record.update(source_asset_id=asset["candidate_id"],
        source_original_sha256=asset["original_sha256"],
        raster_asset_sha256=asset["original_sha256"],
        geometry_format="RASTER",geography_mode="raster_georeferenced",
        geometry_object_sha256=None,approved_feature_ids=[],labels=[],
        user_approved=True,rights_review_record_id=reviewed["approved"][0]["approval_record_id"])
    with pytest.raises(ContractViolation,match="MAP_PERIOD_MISMATCH"):
        ingest_current_approved(store,pid,rid,{**map_record,"valid_year_from":1914,
            "valid_year_to":1914},year=1914,feature_ids=[])
    result=ingest_current_approved(store,pid,rid,map_record,year=1871,feature_ids=[])
    assert result["coordinate_space"]=="UV_ONLY"
    assert store.get_artifact(result["source_original_sha256"])==original
    with pytest.raises(ContractViolation,match="MAP_RIGHTS_UNREVIEWED"):
        ingest_current_approved(store,pid,rid,{**map_record,"rights_review_record_id":"foreign_approval"},
                                year=1871,feature_ids=[])
    changed=copy.deepcopy(story);changed["project"]["title"]="Story changed"
    store.import_story(StoryCandidate.parse(changed),store.revision(pid))
    with pytest.raises(ContractViolation,match="G3_APPROVAL_REQUIRED"):
        ingest_current_approved(store,pid,rid,map_record,year=1871,feature_ids=[])
