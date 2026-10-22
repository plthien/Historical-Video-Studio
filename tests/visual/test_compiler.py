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


def test_map_polygon_nonadjacent_vertex_on_edge_red_green():
    # B1-02: nonadjacent vertex touches the interior of the first edge.
    # Use the full provenance-checked ingest path, never a geometry-only shortcut.
    points=[[10,50],[12,50],[12,52],[11,50],[10,52],[10,50]]
    raw={"type":"FeatureCollection","crs":"EPSG:4326",
         "features":[{"id":"feature_001","type":"Feature",
                      "geometry":{"type":"Polygon","coordinates":[points]},"properties":{}}]}
    source=json.dumps(raw,separators=(",",":")).encode()
    m,approval=example_map(source,crs="EPSG:4326")
    with pytest.raises(ContractViolation) as ex:
        ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
    assert ex.value.code=="MAP_GEOMETRY_INVALID"
    assert ex.value.path=="feature_001"


@pytest.mark.parametrize("rings,accepted",[
    ([[10,50],[12,50],[12,52],[10,52],[10,50]],True),
    ([[10,50],[12,50],[12,52],[11,50],[10,52],[10,50]],False),
    ([[10,50],[12,50],[11,50],[12,52],[10,52],[10,50]],False),
    ([[10,50],[12,50],[12,52],[11,50],[11.5,50],[10,52],[10,50]],False),
    ([[10,50],[12,50],[12,52],[11,51],[11,50],[10,52],[11,51],[10,50]],False),
    ([[10,50],[12,50],[12,50],[12,52],[10,52],[10,50]],False),
])
def test_map_polygon_topology_contacts_and_valid_control(rings,accepted):
    raw={"type":"FeatureCollection","crs":"EPSG:4326",
         "features":[{"id":"feature_001","type":"Feature",
                      "geometry":{"type":"Polygon","coordinates":[rings]},"properties":{}}]}
    source=json.dumps(raw,separators=(",",":")).encode()
    m,approval=example_map(source,crs="EPSG:4326")
    if accepted:
        a=ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
        b=ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
        assert a["geometry_sha256"]==b["geometry_sha256"]
        assert a["features"][0]["geometry"]["coordinates"]==[rings]
    else:
        with pytest.raises(ContractViolation) as ex:
            ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
        assert ex.value.code=="MAP_GEOMETRY_INVALID" and ex.value.path=="feature_001"


@pytest.mark.parametrize("holes,accepted",[
    ([[10.5,50.5],[10.5,51.5],[11.5,51.5],[11.5,50.5],[10.5,50.5]],True),
    ([[10,50.5],[10.5,50.5],[10.5,51],[10,50.5]],False),
    ([[12.2,50.5],[12.5,50.5],[12.5,51],[12.2,50.5]],False),
    ([[11.8,50.5],[12.2,50.5],[11.8,51],[11.8,50.5]],False),
])
def test_map_polygon_interior_ring_relationships(holes,accepted):
    outer=[[10,50],[12,50],[12,52],[10,52],[10,50]]
    raw={"type":"FeatureCollection","crs":"EPSG:4326",
         "features":[{"id":"feature_001","type":"Feature",
                      "geometry":{"type":"Polygon","coordinates":[outer,holes]},"properties":{}}]}
    source=json.dumps(raw,separators=(",",":")).encode()
    m,approval=example_map(source,crs="EPSG:4326")
    if accepted:
        result=ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
        assert result["features"][0]["geometry"]["coordinates"]==[outer,holes]
    else:
        with pytest.raises(ContractViolation) as ex:
            ingest(m,source,year=1871,feature_ids=["feature_001"],approval=approval)
        assert ex.value.code=="MAP_GEOMETRY_INVALID"

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
    assert windows[0]["start_frame"]==0 and windows[0]["end_frame"]==31
    assert windows[0]["start_sample"]==3001 and windows[0]["end_sample"]==4101
    assert windows[0]["word_ids"]==["word_004","word_005"]
    scene=group_staging(windows,48001,48000)[0]
    assert scene["start_frame"]==0 and scene["end_frame"]==31
    assert scene["focus_sequence"][0]["word_ids"]==["word_004","word_005"]
    assert scene["focus_sequence"][0]["cue_start_frame"]==1
    assert scene["focus_sequence"][0]["cue_end_frame"]==3
    assert scene["focus_sequence"][0]["pre_cue_hold_frames"]==1
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
    scenes=group_staging(windows,48000,wav["sample_rate"])
    assert scenes[0]["start_frame"]==0 and scenes[0]["end_frame"]==30
    assert [f["beat_id"] for f in scenes[0]["focus_sequence"]]==[w["beat_id"] for w in windows]


def test_map_timing_two_setups_contiguous_from_audio_frame_zero():
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    authored=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    bp=normalize_story(story,{"setup_001":authored})
    p=bp["setup_plans"][0]
    other=copy.deepcopy(p)
    other["setup_id"]="setup_second"
    other["editorial_direction"]["visual_beats"][0]["beat_id"]="beat_second"
    other["editorial_direction"]["visual_beats"][0]["cue"]={"section_id":"sec_001","phrase":"1871,","occurrence":0}
    bp["setup_plans"].append(other)
    wav=fixture("contracts/examples/WordTimingMap.v1.valid.json")
    windows=bind_beats(bp,wav,audio_sha256=wav["audio_sha256"],
                       transcript_sha256=wav["transcript_sha256"],audio_total_samples=48001)
    scenes=group_staging(windows,48001,wav["sample_rate"])
    assert len(windows)==len(scenes)==2
    assert windows[0]["start_frame"]==scenes[0]["start_frame"]==0
    assert windows[0]["end_frame"]==windows[1]["start_frame"]
    assert scenes[0]["end_frame"]==scenes[1]["start_frame"]
    assert windows[-1]["end_frame"]==scenes[-1]["end_frame"]==31


def test_map_timing_staging_rejects_gap_or_leading_hole():
    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    authored=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    bp=normalize_story(story,{"setup_001":authored})
    wav=fixture("contracts/examples/WordTimingMap.v1.valid.json")
    windows=bind_beats(bp,wav,audio_sha256=wav["audio_sha256"],
                       transcript_sha256=wav["transcript_sha256"],audio_total_samples=48000)
    broken=copy.deepcopy(windows)
    broken[0]["start_frame"]=1
    with pytest.raises(ContractViolation) as exc:
        group_staging(broken,48000,wav["sample_rate"])
    assert exc.value.code=="FRAME_INTERVAL_INVALID"

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
    changed=copy.deepcopy(story);changed["asset_requirements"][0]["subject"]="Updated period source evidence"
    store.import_story(StoryCandidate.parse(changed),store.revision(pid))
    with pytest.raises(ContractViolation,match="G3_APPROVAL_REQUIRED"):
        ingest_current_approved(store,pid,rid,map_record,year=1871,feature_ids=[])



def test_layers_registered_variants_and_g3_source_binding():
    from backend.app.director.layout import layouts, pixel_geometry, windows_font_measure
    from backend.app.director.layers import build_layers
    from backend.app.director.blueprint import normalize_story
    import os
    if os.name != "nt":
        pytest.skip("Pinned real Windows GDI font measurement is Windows-only")
    path=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,identity=windows_font_measure(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
    story,payloads=visual()
    bp=normalize_story(story,payloads)
    assert len(layouts())==30
    first=bp["setup_plans"][0]
    all_geom=[]
    for variant in ("A","B","C"):
        selected=copy.deepcopy(first)
        selected["variant_id"]=variant
        selected["layout_control"]["layout_id"]=f"T01.{variant}.v1"
        all_geom.append(pixel_geometry(selected))
    assert all_geom[0]!=all_geom[1] and all_geom[1]!=all_geom[2]
    req=first["editorial_direction"]["asset_slots"][0]["requirement_id"]
    approval={req:{"candidate_id":"candidate_test_map",
                    "approval_record_id":"approval_test_map",
                    "original_sha256":"a"*64,
                    "asset_class":"HISTORICAL_MAP","source_kind":"ARCHIVE"}}
    classes={x["requirement_id"]:x for x in story["asset_requirements"]}
    layers,refs=build_layers(first,approval,classes,font_measure=measure)
    assert len(layers)>=2
    map_layer=next(x for x in layers if x["layer_kind"]=="map")
    assert map_layer["template_slot_id"]=="map_main"
    assert map_layer["source_asset_slot_id"]==first["editorial_direction"]["asset_slots"][0]["slot_id"]
    assert map_layer["asset_id"]=="candidate_test_map"
    assert layers[1]["text_layout"]["font_size_px"]>=20
    with pytest.raises(ContractViolation,match="G3_ASSET_UNAPPROVED"):
        build_layers(first,{},classes,font_measure=measure)
    with pytest.raises(ContractViolation,match="G3_ASSET_UNAPPROVED"):
        bad=copy.deepcopy(approval)
        bad[req]["asset_class"]="ARCHIVAL_PHOTO"
        build_layers(first,bad,classes,font_measure=measure)


def test_motion_nineteen_distinct_registered_grammars_and_blockers():
    from backend.app.director.motion import presets,compile_event
    entries=presets()
    assert len(entries)==19 and len({p["render_recipe"]["primitive"] for p in entries.values()})==19
    for name,preset in entries.items():
        kind=("archival_photo" if name=="parallax-layers" else
              "text" if name in ("typewriter","number-count","text-highlight") else
              "route" if name=="route-line-draw" else
              "annotation" if name=="editorial-connector-draw" else
              preset["compatible_layer_kinds"][0])
        target={"layer_id":"layer_test_primary","layer_kind":kind,
                "source_claim_id":"claim_001","path_geometry_ref":(
                    "geometry_001" if kind=="route" else "connector_001")}
        other={"layer_id":"layer_test_secondary","layer_kind":"archival_photo",
               "source_claim_id":"claim_001","path_geometry_ref":None}
        evidence={"source_sha":"a"*64,"claim_ids":["claim_001"],"number_value":1914,
                  "historical_map_id":"map_001","era_year":1914,
                  "approved_feature_ids":["feature_001"],"reviewed_period_map":True,
                  "route_feature_id":"geometry_001","geometry_type":(
                      "LineString" if name=="route-line-draw" else "editorial"),
                  "editorial_connector":True}
        event=compile_event(name,target,[target,other],event_id="event_test_"+name.replace("-","_"),
                            start_frame=3,duration_frames=preset["default_duration_frames"],
                            cue_word_id="word_001",evidence=evidence)
        assert event["preset_id"]==name
        assert event["motion_space"]==preset["render_recipe"]["transform_space"]
        assert event["keyframes"][0]["frame"]==0
        assert event["keyframes"][-1]["frame"]==event["duration_frames"]
        assert sum(p["duration_frames"] for p in event["phases"])==event["duration_frames"]
    target={"layer_id":"layer_test_primary","layer_kind":"route","path_geometry_ref":"geometry_001"}
    with pytest.raises(ContractViolation,match="MOTION_GEOGRAPHY_UNREVIEWED"):
        compile_event("route-line-draw",target,[target],event_id="event_negative",
                      start_frame=0,duration_frames=8,cue_word_id="word_001",evidence={})
    with pytest.raises(ContractViolation,match="MOTION_TIME_INVALID"):
        compile_event("route-line-draw",target,[target],event_id="event_negative",
                      start_frame=-1,duration_frames=8,cue_word_id="word_001",evidence={})



def test_compiler_fingerprint_full_48_synthetic_deterministic_and_negative():
    """B1-06 executes new production compiler on 48 re-cued synthetic setups."""
    from backend.tools.b1_smoke import synthetic_longform_inputs
    from backend.app.director.compiler import compile_timeline
    from backend.app.director.layout import windows_font_measure
    import os
    if os.name!="nt":
        pytest.skip("B1 compiler target is native Windows")
    path=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,font_id=windows_font_measure(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
    story,bp,words,final,approved,maps=synthetic_longform_inputs()
    args=dict(maps=maps,font_measure=measure,font_identity=font_id,
              expected_story_sha256=bp["story_revision_sha256"])
    result=compile_timeline(story,bp,words,final,approved,**args)
    again=compile_timeline(story,bp,words,final,approved,**args)
    assert json.dumps(result,sort_keys=True)==json.dumps(again,sort_keys=True)
    validate_document("CompiledTimeline.v1",result)
    assert len(result["scenes"])==48
    assert result["total_frames"]==10800
    assert [s["start_frame"] for s in result["scenes"]]==sorted(s["start_frame"] for s in result["scenes"])
    assert {s["template_id"] for s in result["scenes"]}=={"T01","T03","T06","T08"}
    assert all(s["events"] and s["layers"] and s["camera"]["keyframes"] for s in result["scenes"])
    assert result["scenes"][0]["start_frame"]==0
    assert result["scenes"][-1]["start_frame"]+result["scenes"][-1]["duration_frames"]==10800
    wrong_audio=copy.deepcopy(words)
    wrong_audio["audio_sha256"]="a"*64
    with pytest.raises(ContractViolation,match="ALIGNMENT_SOURCE_STALE"):
        compile_timeline(story,bp,wrong_audio,final,approved,**args)
    missing=copy.deepcopy(approved)
    missing.pop(bp["setup_plans"][0]["requirement_refs"][0])
    with pytest.raises(ContractViolation,match="G3_ASSET_UNAPPROVED"):
        compile_timeline(story,bp,words,final,missing,**args)
    wrong_registry=copy.deepcopy(bp)
    wrong_registry["setup_plans"][0]["variant_id"]="Z"
    with pytest.raises(ContractViolation):
        compile_timeline(story,wrong_registry,words,final,approved,**args)


def test_compiler_g4_invariant_rejects_changed_frozen_source_before_recompute():
    """B1-06: G4 may only reuse prior approved WAV/word-map/G3 snapshot."""
    from backend.app.director.compiler import revise_g4
    from backend.app.director.fingerprint import digest
    class RevisionOnlyStore:
        def revision(self, project_id):
            return 7
    store=RevisionOnlyStore()
    original={"project_id":"project_test",
              "story_revision_sha256":"a"*64,"setup_plans":[]}
    prior={"story_sha256":"a"*64,"audio_sha256":"b"*64,
           "word_map_sha256":digest({"words":[]}),
           "asset_snapshot_sha256":digest({"req_001":{"original_sha256":"c"*64}})}
    rows=[
        ({"words":[{"word_id":"modified"}]},{"audio_sha256":"b"*64},
         {"req_001":{"original_sha256":"c"*64}}),
        ({"words":[]},{"audio_sha256":"e"*64},
         {"req_001":{"original_sha256":"c"*64}}),
        ({"words":[]},{"audio_sha256":"b"*64},
         {"req_001":{"original_sha256":"f"*64}}),
    ]
    for words,audio,assets in rows:
        with pytest.raises(ContractViolation) as ex:
            revise_g4(store,"project_test",prior,original,copy.deepcopy(original),
                      words,audio,assets,expected_revision=7,
                      operator_reason="Presentation-only adjustment")
        assert ex.value.code=="G4_SOURCE_EDIT_FORBIDDEN"
    with pytest.raises(ContractViolation) as ex:
        revise_g4(store,"project_test",prior,original,copy.deepcopy(original),
                  {"words":[]},{"audio_sha256":"b"*64},
                  {"req_001":{"original_sha256":"c"*64}},
                  expected_revision=6,operator_reason="Presentation-only adjustment")
    assert ex.value.code=="APPROVAL_REVISION_CONFLICT"


# B1-04/B1-05 RED discriminators: call the production scene compiler, not compile_event.
def _actual_scene_for(template_id):
    from backend.app.director.compiler import _scene
    story, payloads = visual()
    plan = next(p for p in normalize_story(story, payloads)["setup_plans"]
                if p["template_id"] == template_id)
    requirements = {r["requirement_id"]: r for r in story["asset_requirements"]}
    approved = {
        rid: {"candidate_id": "candidate_" + rid, "approval_record_id": "approval_" + rid,
              "original_sha256": hashlib.sha256(rid.encode()).hexdigest(),
              "asset_class": req["asset_class"], "source_kind": "SYNTHETIC"}
        for rid, req in requirements.items()}
    frame_rows = [
        {**{"start_frame": i*60, "end_frame": (i+1)*60,
            "cue_start_frame": i*60, "word_ids": ["word_" + str(i+1)]},
         "beat_id": beat["beat_id"], "focus_ref": beat["focus_ref"],
         "staging": beat["staging"]}
        for i, beat in enumerate(plan["editorial_direction"]["visual_beats"])]
    maps = {plan["setup_id"]: {
        "reviewed_period_map": True, "route_feature_id": "geometry_route_001",
        "geometry_type": "LineString", "historical_map_id": "map_synthetic",
        "era_year": 1914, "approved_feature_ids": ["feature_001"]}}
    if template_id == "T07":
        maps[plan["setup_id"]].update(shared_projection="mercator",
                                      shared_viewport=[0,0,1,1])
    staging = {"start_frame": 0, "end_frame": len(frame_rows)*60}
    # No rights or font claims: synthetic helper only. Production compiler still runs.
    return _scene(plan, staging, frame_rows, approved, requirements, maps,
                  lambda text, size: (len(text)*size//2, size)), plan


def test_b1_authored_t03_stagger_dispatch_actual_scene():
    scene, plan = _actual_scene_for("T03")
    e = scene["events"][0]
    assert e["preset_id"] == "stagger-reveal"
    assert e["stagger"]["order"] == [
        next(x["layer_id"] for x in scene["layers"]
             if x["source_asset_slot_id"] == card["asset_slot_id"])
        for card_id in plan["template_payload"]["card_reveal_order"]
        for card in plan["template_payload"]["cards"] if card["card_id"] == card_id]
    assert len(e["affected_layer_ids"]) == 3
    assert e["cue_binding"]["word_id"] == "word_1"


def test_b1_authored_t04_route_draw_targets_route_not_focus_map():
    scene, plan = _actual_scene_for("T04")
    assert scene["staging"]["beat_sequence"][0]["focus_layer_id"].endswith("map_backdrop")
    e = scene["events"][0]
    assert e["preset_id"] == "route-line-draw"
    assert e["layer_id"].endswith("route_overlay")
    assert e["params"]["route_geometry_ref"] == plan["template_payload"]["route_geometry_ref"]
    assert e["motion_space"] == "map_world"


def test_b1_authored_t06_document_crop_is_non_destructive():
    scene, plan = _actual_scene_for("T06")
    document = next(x for x in scene["layers"] if x["layer_kind"] == "document")
    assert document["crop_normalized"] == plan["template_payload"]["focus_region_uv"]
    assert document["asset_id"] is not None
    assert document["mask"]["kind"] == "none"


def test_b1_unsupported_motion_hint_fails_closed():
    from backend.app.director.compiler import _scene
    scene, plan = _actual_scene_for("T03")
    # Never mistake an unsupported effect for a generic photo-card fallback.
    beat = copy.deepcopy(plan["editorial_direction"]["visual_beats"][0])
    beat["staging"][0]["motion_hint"] = "unregistered_motion"
    plan["editorial_direction"]["visual_beats"] = [beat]
    requirements = {r["requirement_id"]: r for r in visual()[0]["asset_requirements"]}
    approved = {rid: {"candidate_id": "candidate_" + rid, "approval_record_id": "approval_" + rid,
                       "original_sha256": hashlib.sha256(rid.encode()).hexdigest(),
                       "asset_class": req["asset_class"], "source_kind": "SYNTHETIC"}
                for rid, req in requirements.items()}
    row = {"beat_id": beat["beat_id"], "focus_ref": beat["focus_ref"],
           "staging": beat["staging"], "start_frame": 0, "end_frame": 60,
           "cue_start_frame": 0, "word_ids": ["word_1"]}
    with pytest.raises(ContractViolation, match="MOTION_HINT_UNSUPPORTED"):
        _scene(plan, {"start_frame": 0, "end_frame": 60}, [row], approved,
               requirements, {}, lambda text,size: (len(text)*size//2, size))



def test_b1_production_compiler_all_ten_templates_native_samples_and_sources():
    """Execute actual compile_timeline for T01..T10, not schema-only contract fixtures."""
    from backend.tools.b1_smoke import synthetic_ten_template_inputs
    from backend.app.director.compiler import compile_timeline
    story, bp, words, final, assets, maps = synthetic_ten_template_inputs()
    import os
    from backend.app.director.layout import windows_font_measure
    if os.name != "nt":
        pytest.skip("Production font gate requires native Windows GDI")
    font = Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"
    measure, font_identity = windows_font_measure(str(font), hashlib.sha256(font.read_bytes()).hexdigest())
    kwargs = {"maps":maps, "font_measure":measure, "font_identity":font_identity,
              "expected_story_sha256":bp["story_revision_sha256"]}
    result = compile_timeline(story,bp,words,final,assets,**kwargs)
    validate_document("CompiledTimeline.v1",result)
    scenes = result["scenes"]
    assert len(scenes) == 10
    assert {s["template_id"] for s in scenes} == {f"T{i:02d}" for i in range(1,11)}
    assert result["total_frames"] == 3000
    assert all(s["layers"] and s["events"] and s["staging"]["beat_sequence"]
               and s["camera"]["focus_path"] for s in scenes)
    assert all(a["start_frame"] + a["duration_frames"] == b["start_frame"]
               for a,b in zip(scenes, scenes[1:]))
    t03 = next(s for s in scenes if s["template_id"] == "T03")
    assert t03["events"][0]["preset_id"] == "stagger-reveal"
    assert len(t03["events"][0]["affected_layer_ids"]) == 3
    t04 = next(s for s in scenes if s["template_id"] == "T04")
    assert t04["events"][0]["preset_id"] == "route-line-draw"
    assert t04["events"][0]["layer_id"].endswith("route_overlay")
    t06 = next(s for s in scenes if s["template_id"] == "T06")
    assert any(x["layer_kind"] == "document" and x["crop_normalized"]["w"] < 1
               for x in t06["layers"])
    t07 = next(s for s in scenes if s["template_id"] == "T07")
    assert len({x["asset_id"] for x in t07["layers"] if x["layer_kind"] == "map"}) == 2
    t10 = next(s for s in scenes if s["template_id"] == "T10")
    assert any(x["layer_kind"] == "annotation" and x["path_geometry_ref"].startswith("connector_")
               for x in t10["layers"])



def test_b1_g4_schema_invalid_staging_never_changes_sqlite_revision(tmp_path):
    """A correctly bound upstream identity cannot authorize a schema-invalid G4 edit."""
    from backend.app.projects.storage import ProjectStore
    from backend.app.director.compiler import revise_g4
    from backend.app.director.fingerprint import digest
    story, payloads = visual()
    original = normalize_story(story, payloads)
    pid = original["project_id"]
    store = ProjectStore(tmp_path/"state.sqlite", tmp_path/"originals")
    store.create_project(pid, "SYNTHETIC G4 schema gate")
    store.import_story(StoryCandidate.parse(story), 0)
    prior = {"story_sha256":original["story_revision_sha256"],
             "audio_sha256":"b"*64, "word_map_sha256":digest({"words":[]}),
             "asset_snapshot_sha256":digest({})}
    edited = copy.deepcopy(original)
    changed = edited["setup_plans"][0]
    changed["direction_revision"] = {
        "kind":"operator_visual_edit",
        "source_story_revision_sha256":prior["story_sha256"],
        "operator_confirmed":True, "edited_paths":["editorial_direction.visual_beats.0.staging"],
        "edit_reason":"Regression verification"}
    changed["editorial_direction"]["visual_beats"][0]["staging"][0]["operation"] = "not_registered"
    current_revision = store.revision(pid)
    with pytest.raises(ContractViolation) as err:
        revise_g4(store,pid,prior,original,edited,{"words":[]},
                  {"audio_sha256":"b"*64}, {},expected_revision=current_revision,
                  operator_reason="Validation regression")
    assert err.value.code != "COMPILER_GATE_UNAPPROVED"
    assert store.revision(pid) == current_revision



def test_b1_thirty_variants_actual_compiler_geometry_on_windows():
    """B1-04: A/B/C geometry must execute through the compiler for every template."""
    from backend.tools.b1_smoke import synthetic_ten_template_inputs
    from backend.app.director.compiler import compile_timeline
    from backend.app.director.layout import windows_font_measure
    import os
    if os.name != "nt":
        pytest.skip("Real measured font and 30 variants require native Windows")
    font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
    story,base,words,final,assets,maps=synthetic_ten_template_inputs()
    outputs={}
    for variant in ("A","B","C"):
        bp=copy.deepcopy(base)
        for plan in bp["setup_plans"]:
            plan["variant_id"]=variant
            plan["layout_control"]["layout_id"]=f'{plan["template_id"]}.{variant}.v1.1'
        out=compile_timeline(story,bp,words,final,assets,maps=maps,
              font_measure=measure,font_identity=identity,
              expected_story_sha256=bp["story_revision_sha256"])
        assert len(out["scenes"])==10 and out["total_frames"]==3000
        for scene in out["scenes"]:
            assert scene["variant_id"]==variant
            assert all(x["rect_px"]["w"]>0 and x["rect_px"]["h"]>0 for x in scene["layers"])
            outputs[(scene["template_id"],variant)] = [
                (x["template_slot_id"],x["rect_px"]) for x in scene["layers"]]
    assert len(outputs)==30
    for tid in (f"T{i:02d}" for i in range(1,11)):
        assert len({json.dumps(outputs[(tid,v)],sort_keys=True) for v in ("A","B","C")})==3



def test_b1_cold_process_compiler_bytes_and_sha_identity():
    """B1-06: deterministic identity across two native, fresh Python processes."""
    import os
    import subprocess
    import sys
    if os.name!="nt":
        pytest.skip("Cold Windows GDI process fingerprint comparison requires Windows")
    script = """
import hashlib, json, os
from pathlib import Path
from backend.tools.b1_smoke import synthetic_ten_template_inputs
from backend.app.director.compiler import compile_timeline
from backend.app.director.layout import windows_font_measure
from backend.app.director.fingerprint import canonical
font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
story,bp,words,final,assets,maps=synthetic_ten_template_inputs()
out=compile_timeline(story,bp,words,final,assets,maps=maps,
    font_measure=measure,font_identity=identity,
    expected_story_sha256=bp["story_revision_sha256"])
print(json.dumps({"bytes_sha":hashlib.sha256(canonical(out)).hexdigest(),
                  "fingerprint":out["dependency_fingerprint"],
                  "scene_sha":[hashlib.sha256(canonical(x)).hexdigest() for x in out["scenes"]]}))
"""
    results = [
        subprocess.run([sys.executable,"-c",script],cwd=ROOT,
                       check=True,capture_output=True,text=True).stdout.strip()
        for _ in range(2)]
    assert results[0] == results[1]
    parsed=json.loads(results[0])
    assert len(parsed["scene_sha"])==10
    assert len(parsed["bytes_sha"])==64 and len(parsed["fingerprint"])==64



def test_b1_g4_real_sqlite_positive_selective_revision_and_stale_sources(tmp_path):
    """B1-06: local SQLite G1/G2/G3 approvals are controlled, never human/live."""
    import os
    from unittest.mock import patch
    if os.name != "nt":
        pytest.skip("Native GDI + FFmpeg + SQLite integration needs Windows")
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
    from backend.app.director.compiler import compile_from_store, revise_g4
    from backend.app.director.layout import windows_font_measure
    from backend.app.director.fingerprint import canonical
    from backend.app.maps.ingest import ingest_current_approved
    import base64

    story=fixture("contracts/examples/StoryPackage.v1.valid.json")
    second=copy.deepcopy(story["visual_setups"][0])
    second["setup_id"]="setup_002"
    second["direction"]["visual_beats"][0]["beat_id"]="beat_setup_002"
    second["direction"]["visual_beats"][0]["cue"]={
        "section_id":"sec_001","phrase":"the","occurrence":0}
    second["direction"]["visual_beats"][0]["continuity"]["group_id"]="group_setup_002"
    second["direction"]["reveal_plan"][0]["beat_id"]="beat_sec_002"
    second["direction"]["reveal_plan"][0]["cue"]={
        "section_id":"sec_001","phrase":"the","occurrence":0}
    story["visual_setups"].append(second)
    pid=story["project"]["project_id"]
    store=ProjectStore(tmp_path/"g4.sqlite",tmp_path/"media")
    store.create_project(pid,"Controlled local integration")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    voice=VoiceService(store,gates,JobQueue(store))
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"synthetic"}):
        voice.enqueue(pid,"sec_001","kokoro_local","am_adam",1.0,
                      "Local controlled TTS",store.revision(pid),"test_g4_voice_001")
        assert voice.process_one(lambda *_:wav_fixture(4.0))["state"]=="SUCCEEDED"
    g2=gates.board(pid)[1]
    gates.decide(pid,"G2",{"decision":"APPROVED",
        "candidate_sha256":g2["candidate_sha256"],
        "dependency_fingerprint":g2["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    workflow=FinalVoiceWorkflow(store,gates,JobQueue(store))
    assert workflow.process_one()["state"]=="SUCCEEDED"
    frozen=workflow.status(pid)["final_audio"]
    assert workflow.process_one(lambda audio,text:mock_alignment(frozen,text))["state"]=="SUCCEEDED"
    words=workflow.status(pid)["word_map"]
    assert words
    resolver=AssetResolution(store)
    resolver.choose(pid,"req_001","MANUAL_UPLOAD","Synthetic source",store.revision(pid))
    image=base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC")
    candidate=AssetCandidates(store).manual(
        pid,"req_001",image,"Synthetic period map","Fixture 1871","Test-only rights")
    review=resolver.approve_batch(pid,[{
        "requirement_id":"req_001","candidate_id":candidate["candidate_id"],
        "original_sha256":candidate["original_sha256"],"rights_status":"ELIGIBLE",
        "rights_evidence_note":"Synthetic review only",
        "historical_context_note":"Local test map"}],store.revision(pid))
    g3=gates.board(pid)[2]
    gates.decide(pid,"G3",{"decision":"APPROVED",
        "candidate_sha256":g3["candidate_sha256"],
        "dependency_fingerprint":g3["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    record=fixture("contracts/examples/HistoricalMap.v1.valid.json")
    record.update(source_asset_id=candidate["candidate_id"],
         source_original_sha256=candidate["original_sha256"],
         raster_asset_sha256=candidate["original_sha256"],
         geometry_format="RASTER",geography_mode="raster_georeferenced",
         geometry_object_sha256=None,approved_feature_ids=[],labels=[],
         user_approved=True,rights_review_record_id=review["approved"][0]["approval_record_id"])
    ingested=ingest_current_approved(store,pid,"req_001",record,year=1871,feature_ids=[])
    ctx={"reviewed_period_map":True,"sources":{"req_001":ingested},
         "historical_map_id":ingested["historical_map"]["historical_map_id"],
         "era_year":1871,"approved_feature_ids":[]}
    authored=fixture("contracts/examples/VisualBlueprint.v1.valid.json")["setup_plans"][0]["template_payload"]
    bp=normalize_story(story,{"setup_001":authored,"setup_002":authored})
    font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
    measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
    requests={"req_001":{"year":1871,"map_record":record,"feature_ids":[]}}
    original=compile_from_store(store,pid,bp,words,frozen,map_requests=requests,
                                font_measure=measure,font_identity=identity)
    assert len(original["scenes"])==2
    with store._connection() as db:
        source=AssetCandidates._source_tx(db,pid,"req_001")
        head=AssetResolution._head(db,pid,"req_001",source["requirement_sha256"])
    current={"req_001":{**head,"asset_class":"HISTORICAL_MAP",
                        "source_kind":head.get("evidence",{}).get("source_kind","")}}
    edited=copy.deepcopy(bp)
    edited["setup_plans"][0]["variant_id"]="B"
    edited["setup_plans"][0]["layout_control"]["layout_id"]="T01.B.v1.1"
    edited["setup_plans"][0]["direction_revision"]={
        "kind":"operator_visual_edit","source_story_revision_sha256":original["story_sha256"],
        "edited_paths":["variant_id","layout_control.layout_id"],
        "operator_confirmed":True,"edit_reason":"Improve map framing"}
    revision=store.revision(pid)
    changed=revise_g4(store,pid,original,bp,edited,words,frozen,current,
               expected_revision=revision,operator_reason="Variant framing change",
               maps={"setup_001":ctx,"setup_002":ctx},font_measure=measure)
    assert changed["recomputed_setup_ids"]==["setup_001"]
    assert changed["retained_setup_ids"]==["setup_002"]
    assert canonical(changed["timeline"]["scenes"][1])==canonical(original["scenes"][1])
    assert canonical(changed["timeline"]["scenes"][0])!=canonical(original["scenes"][0])
    assert changed["timeline"]["word_map_sha256"]==original["word_map_sha256"]
    assert changed["timeline"]["asset_snapshot_sha256"]==original["asset_snapshot_sha256"]
    assert store.revision(pid)==revision+1
    assert gates.board(pid)[3]["state"]!="APPROVED"
    assert gates.board(pid)[4]["state"]!="APPROVED"
    with pytest.raises(ContractViolation,match="APPROVAL_REVISION_CONFLICT"):
        revise_g4(store,pid,original,bp,edited,words,frozen,current,
                  expected_revision=revision,operator_reason="Stale update",
                  maps={"setup_001":ctx,"setup_002":ctx},font_measure=measure)
