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
                 geometry_object_sha256=None,
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
    if case=="compile-layout":
        from backend.app.director.layout import windows_font_measure, pixel_geometry
        from backend.app.director.layers import build_layers
        import os
        if os.name!="nt":
            raise ContractViolation("FONT_METRICS_REQUIRED",case,"B1 native font smoke requires Windows.")
        font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
        measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
        story=fixture("contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json")
        source=fixture("contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json")
        plans=normalize_story(story,{p["setup_id"]:p["template_payload"] for p in source["setup_plans"]})
        p=plans["setup_plans"][0]
        rid=p["asset_slot_bindings"][0]["requirement_id"]
        approved={rid:{"candidate_id":"candidate_synthetic_map","approval_record_id":"approval_synthetic_map",
                       "original_sha256":"a"*64,"asset_class":"HISTORICAL_MAP","source_kind":"ARCHIVE"}}
        requirements={r["requirement_id"]:r for r in story["asset_requirements"]}
        layers,_=build_layers(p,approved,requirements,font_measure=measure)
        if (len(layers)<2 or not layers[0]["source_asset_slot_id"] or
                not layers[1]["text_layout"] or layers[0]["rect_px"]!=pixel_geometry(p)[layers[0]["template_slot_id"]]):
            raise RuntimeError("Registered geometry, real font measurement or G3 slot binding missing.")
        print("compile-layout: LOCAL_PASS SYNTHETIC slots="+str(len(layers))+
              " first_rect="+str(layers[0]["rect_px"])+" font_sha="+identity["font_sha256"])
        return
    if case=="compile-motion":
        from backend.app.director.motion import presets,compile_event
        target={"layer_id":"layer_smoke","layer_kind":"headline","source_claim_id":"claim_001"}
        e=compile_event("title-mask-reveal",target,[target],
                        event_id="event_smoke",start_frame=10,duration_frames=18,
                        cue_word_id="word_001",evidence={"claim_ids":["claim_001"]})
        if (len(presets())!=19 or e["start_frame"]!=10 or e["keyframes"][0]["frame"]!=0 or
                e["keyframes"][-1]["frame"]!=18 or
                sum(x["duration_frames"] for x in e["phases"])!=18):
            raise RuntimeError("Registered motion did not produce a real bounded frame-local recipe.")
        print("compile-motion: LOCAL_PASS SYNTHETIC registered=19 primitive="+e["preset_id"]+
              " keyframes="+str(e["keyframes"]))
        return
    if case=="compile-longform":
        from backend.app.director.compiler import compile_timeline
        from backend.app.director.layout import windows_font_measure
        import os
        if os.name!="nt":
            raise ContractViolation("FONT_METRICS_REQUIRED",case,"B1 native font smoke requires Windows.")
        font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
        measure,identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
        story,bp,words,final,assets,maps=synthetic_longform_inputs()
        result=compile_timeline(story,bp,words,final,assets,maps=maps,
                                font_measure=measure,font_identity=identity,
                                expected_story_sha256=bp["story_revision_sha256"])
        if (len(result["scenes"])!=48 or result["total_frames"]!=10800 or
                any(not s["layers"] or not s["events"] or not s["camera"]["focus_path"] for s in result["scenes"]) or
                any(a["start_frame"]+a["duration_frames"]!=b["start_frame"]
                    for a,b in zip(result["scenes"],result["scenes"][1:]))):
            raise RuntimeError("The actual 48-scene compiler produced a gap or inert scene.")
        repeat=compile_timeline(story,bp,words,final,assets,maps=maps,font_measure=measure,
                                font_identity=identity,
                                expected_story_sha256=bp["story_revision_sha256"])
        if json.dumps(result,sort_keys=True)!=json.dumps(repeat,sort_keys=True):
            raise RuntimeError("Repeated approved synthetic inputs must produce identical timeline bytes.")
        print("compile-longform: LOCAL_PASS SYNTHETIC scenes=48 frames="+
              str(result["total_frames"])+" sha="+result["dependency_fingerprint"]+
              " LIVE_HISTORY=NOT_RUN MP4=NOT_RUN")
        return
    raise ContractViolation("B1_SMOKE_CASE_UNKNOWN",case,"Use the six B1 smoke cases.")



def synthetic_longform_inputs():
    """Explicitly synthetic boundary adapter for the original 24-section/48-setup fixtures.

    These G2/G3 approvals and samples are NOT production proof. The checked-in
    longform fixture anchors BOTH setups of each section to the SAME 'In'/0 cue;
    here its SECOND synthetic cue is re-authored to an actually spoken mid-section
    word so B1-03 correctly receives non-overlapping, native-sample boundaries.
    G1 source narration and claims are never edited.
    """
    from backend.app.director.blueprint import normalize_story
    from backend.app.projects.models import StoryCandidate
    from backend.app.voice.word_map import normalized
    import copy
    story=fixture("contracts/examples/longform/StoryPackage.longform.synthetic.json")
    bp_base=fixture("contracts/examples/longform/VisualBlueprint.longform.synthetic.json")
    params={p["setup_id"]:p["template_payload"] for p in bp_base["setup_plans"]}
    second_by_section={}
    for setup in story["visual_setups"]:
        section=setup["section_refs"][0]
        if section in second_by_section:
            narration=next(s["narration"] for s in story["sections"] if s["section_id"]==section)
            tokens=narration.split()
            chosen=len(tokens)//2
            token=tokens[chosen]
            occurrence=sum(1 for word in tokens[:chosen] if normalized(word)==normalized(token))
            cue={"section_id":section,"phrase":token,"occurrence":occurrence}
            setup["direction"]["visual_beats"][0]["cue"]=cue
            # Legacy synthetic direction points at a non-visible background asset
            # for T08. Use its explicitly authored fact_text_id instead.
            if setup["preferred_template"]=="T08":
                payload=params[setup["setup_id"]]
                setup["direction"]["visual_beats"][0]["focus_ref"]=payload["fact_text_id"]
                setup["direction"]["visual_beats"][0]["staging"][0]["ref"]=payload["fact_text_id"]
        else:
            second_by_section[section]=setup["setup_id"]
            narration=next(s["narration"] for s in story["sections"] if s["section_id"]==section)
            first_word=narration.split()[0]
            setup["direction"]["visual_beats"][0]["cue"]={
                "section_id":section,"phrase":first_word,"occurrence":0}
            if setup["preferred_template"]=="T08":
                payload=params[setup["setup_id"]]
                setup["direction"]["visual_beats"][0]["focus_ref"]=payload["fact_text_id"]
                setup["direction"]["visual_beats"][0]["staging"][0]["ref"]=payload["fact_text_id"]
    blueprint=normalize_story(story,params)
    sample_rate=24000
    per_section=360000
    words=[]
    offsets=[]
    for sec_index,section in enumerate(story["sections"]):
        tokens=section["narration"].split()
        start=sec_index*per_section
        offsets.append({"section_id":section["section_id"],
                        "start_sample":start,"end_sample":start+per_section})
        for i,word in enumerate(tokens):
            a=start+(i*per_section)//len(tokens)
            b=start+((i+1)*per_section)//len(tokens)
            words.append({"word_id":f"word_{len(words)+1:05d}",
                          "section_id":section["section_id"],"text":word,
                          "start_sample":a,"end_sample":b})
    audio_hash=hashlib.sha256(b"SYNTHETIC B1 G2 WAV for fixture, NOT actual TTS").hexdigest()
    transcript_hash=hashlib.sha256(b"SYNTHETIC transcript identity").hexdigest()
    word_map={"schema_version":"WordTimingMap.v1","project_id":blueprint["project_id"],
              "provider_id":"elevenlabs_forced_alignment",
              "audio_sha256":audio_hash,"transcript_sha256":transcript_hash,
              "sample_rate":sample_rate,"words":words,"anomalies":[]}
    final={"schema_version":"FinalAudio.v1","project_id":blueprint["project_id"],
           "story_revision_sha256":blueprint["story_revision_sha256"],
           "selected_attempt_ids":[f"attempt_{i+1:03d}" for i in range(len(offsets))],
           "audio_sha256":audio_hash,"transcript_sha256":transcript_hash,
           "sample_rate":sample_rate,"channels":1,
           "duration_samples":per_section*len(offsets),"section_offsets":offsets}
    approvals={}
    for requirement in story["asset_requirements"]:
        rid=requirement["requirement_id"]
        approvals[rid]={"candidate_id":"candidate_"+rid,
                        "approval_record_id":"approval_"+rid,
                        "original_sha256":hashlib.sha256(("SYNTHETIC original "+rid).encode()).hexdigest(),
                        "asset_class":requirement["asset_class"],"source_kind":"SYNTHETIC"}
    from backend.app.maps.ingest import ingest
    maps={}
    geom_bytes=json.dumps({
        "type":"FeatureCollection","crs":"EPSG:4326",
        "features":[{"type":"Feature","id":"feature_001",
                     "geometry":{"type":"Polygon","coordinates":[[
                         [10,50],[12,50],[12,52],[10,52],[10,50]]]},"properties":{}}]
    },sort_keys=True,separators=(",",":")).encode()
    for plan in blueprint["setup_plans"]:
        sid=plan["setup_id"]
        for rid in plan["requirement_refs"]:
            if approvals[rid]["asset_class"]!="HISTORICAL_MAP":
                continue
            approvals[rid]["original_sha256"]=hashlib.sha256(geom_bytes).hexdigest()
            rec=fixture("contracts/examples/HistoricalMap.v1.valid.json")
            rec.update(historical_map_id="map_"+rid,
                       source_original_sha256=approvals[rid]["original_sha256"],
                       source_asset_id=approvals[rid]["candidate_id"],
                       rights_review_record_id=approvals[rid]["approval_record_id"],
                       user_approved=True,source_crs="EPSG:4326",
                       valid_year_from=1914,valid_year_to=1914,
                       geometry_object_sha256=None,
                       approved_feature_ids=["feature_001"],
                       geography_bbox={"min_lon":9,"min_lat":49,"max_lon":13,"max_lat":53})
            head={"original_sha256":approvals[rid]["original_sha256"],
                  "candidate_id":approvals[rid]["candidate_id"],
                  "approval_record_id":approvals[rid]["approval_record_id"]}
            ingested=ingest(rec,geom_bytes,year=1914,feature_ids=["feature_001"],approval=head)
            maps[sid]={"sources":{rid:ingested},"reviewed_period_map":True,
                       "historical_map_id":ingested["historical_map"]["historical_map_id"],
                       "approved_feature_ids":["feature_001"],"era_year":1914}
    return story,blueprint,word_map,final,approvals,maps



def synthetic_ten_template_inputs():
    """SYNTHETIC G1/G2/G3 boundary for production compile of all ten visual cases.

    No actual TTS, original historical rights review, or operator gate approval.
    Aligned synthetic words have distinct occurrence IDs and exact native samples.
    """
    from backend.app.projects.models import StoryCandidate
    from backend.app.voice.word_map import normalized
    import copy
    story = fixture("contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json")
    reference = fixture("contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json")
    # The checked-in illustrative beats reuse the first 'the'. Each subsequent
    # beat must resolve a different actually spoken word occurrence.
    for setup in story["visual_setups"]:
        beats = setup["direction"]["visual_beats"]
        if len(beats) >= 3:
            beats[2]["cue"]["occurrence"] = 1
    # This synthetic authoring harness deliberately chooses supported motion.
    # The original illustrative T07/T09/T10 'subtle_push' hint is not
    # universally registered for their map/text/document layers; production
    # rejects that unsupported request rather than pretending to execute it.
    for setup in story["visual_setups"]:
        tid = setup["preferred_template"]
        for beat in setup["direction"]["visual_beats"]:
            ref = beat["focus_ref"]
            if tid == "T07":
                hint = "wipe" if "map_" in ref else "none"
            elif tid == "T09" and "source_page" in ref:
                hint = "none"
            elif tid == "T10" and "entity_b" in ref:
                hint = "line_draw"
            elif tid == "T10" and "entity_" in ref:
                hint = "none"
            else:
                continue
            for step in beat["staging"]:
                step["motion_hint"] = hint
    payloads = {p["setup_id"]:p["template_payload"] for p in reference["setup_plans"]}
    bp = normalize_story(story, payloads)
    sample_rate = 24000
    section_samples = 240000
    words, offsets = [], []
    for si, section in enumerate(story["sections"]):
        start = si * section_samples
        tokens = section["narration"].split()
        offsets.append({"section_id": section["section_id"],
                        "start_sample": start, "end_sample": start + section_samples})
        for i, token in enumerate(tokens):
            words.append({"word_id":f"word_{len(words)+1:05d}",
                          "section_id":section["section_id"],"text":token,
                          "start_sample":start + i*section_samples//len(tokens),
                          "end_sample":start + (i+1)*section_samples//len(tokens)})
    audio_hash = hashlib.sha256(b"SYNTHETIC ten-template audio identity").hexdigest()
    transcript_hash = hashlib.sha256(b"SYNTHETIC ten-template transcript identity").hexdigest()
    word_map = {"schema_version":"WordTimingMap.v1","project_id":bp["project_id"],
                "provider_id":"elevenlabs_forced_alignment","audio_sha256":audio_hash,
                "transcript_sha256":transcript_hash,"sample_rate":sample_rate,
                "words":words,"anomalies":[]}
    final = {"schema_version":"FinalAudio.v1","project_id":bp["project_id"],
             "story_revision_sha256":bp["story_revision_sha256"],
             "selected_attempt_ids":[f"attempt_{i+1:03d}" for i in range(len(offsets))],
             "audio_sha256":audio_hash,"transcript_sha256":transcript_hash,
             "sample_rate":sample_rate,"channels":1,
             "duration_samples":section_samples*len(offsets),"section_offsets":offsets}
    raw = json.dumps({"type":"FeatureCollection","crs":"EPSG:4326",
        "features":[
            {"type":"Feature","id":"feature_001",
             "geometry":{"type":"Polygon","coordinates":[[
                 [10,50],[12,50],[12,52],[10,52],[10,50]]]},"properties":{}},
            {"type":"Feature","id":"geometry_route_001",
             "geometry":{"type":"LineString","coordinates":[[10,50],[11,51],[12,52]]},
             "properties":{}}
        ]}, sort_keys=True, separators=(",",":")).encode()
    approved = {}
    map_bytes = {}
    for req in story["asset_requirements"]:
        rid = req["requirement_id"]
        if req["asset_class"]=="HISTORICAL_MAP":
            unique_source=json.loads(raw)
            unique_source["features"][0]["properties"]["synthetic_requirement_id"]=rid
            map_bytes[rid]=json.dumps(unique_source,sort_keys=True,separators=(",",":")).encode()
        approved[rid] = {"candidate_id":"candidate_"+rid,
                         "approval_record_id":"approval_"+rid,
                         "original_sha256":(hashlib.sha256(map_bytes[rid]).hexdigest()
                            if rid in map_bytes
                            else hashlib.sha256(("SYNTHETIC "+rid).encode()).hexdigest()),
                         "asset_class":req["asset_class"],"source_kind":"SYNTHETIC"}
    maps = {}
    for plan in bp["setup_plans"]:
        sid = plan["setup_id"]
        payload = plan["template_payload"]
        map_refs = []
        if "map" in payload:
            map_refs.append(payload["map"])
        for key in ("before_map","after_map"):
            if key in payload:
                map_refs.append(payload[key])
        if plan["template_id"]=="T10" and payload.get("map_requirement_id"):
            req=next(x for x in story["asset_requirements"]
                     if x["requirement_id"]==payload["map_requirement_id"])
            if req["start_year"]!=req["end_year"]:
                raise ContractViolation("MAP_PERIOD_MISMATCH",sid,
                    "T10 region overview requires an exact reviewed fixture period.")
            map_refs.append({"map_requirement_id":req["requirement_id"],"year":req["start_year"]})
        if not map_refs:
            continue
        ctx = {"sources":{}, "reviewed_period_map":True}
        for item in map_refs:
            rid, year = item["map_requirement_id"], item["year"]
            record = fixture("contracts/examples/HistoricalMap.v1.valid.json")
            record.update(historical_map_id="map_"+rid,
                source_original_sha256=approved[rid]["original_sha256"],
                source_asset_id=approved[rid]["candidate_id"],
                rights_review_record_id=approved[rid]["approval_record_id"],
                user_approved=True, source_crs="EPSG:4326",
                geometry_object_sha256=None, valid_year_from=year,
                valid_year_to=year, approved_feature_ids=["feature_001","geometry_route_001"],
                geography_bbox={"min_lon":9,"min_lat":49,"max_lon":13,"max_lat":53})
            original = {k:approved[rid][k] for k in
                        ("original_sha256","candidate_id","approval_record_id")}
            route = "geometry_route_001" if plan["template_id"]=="T04" else None
            record["geometry_format"]="GeoJSON"
            result = ingest(record,map_bytes[rid],year=year,feature_ids=["feature_001","geometry_route_001"],
                            route_feature_id=route,approval=original)
            ctx["sources"][rid] = result
            ctx["historical_map_id"] = result["historical_map"]["historical_map_id"]
            ctx["era_year"] = year
            ctx["approved_feature_ids"] = ["feature_001","geometry_route_001"]
            if route:
                ctx["route_feature_id"] = route
                ctx["geometry_type"] = "LineString"
        if plan["template_id"]=="T07":
            ctx["shared_projection"] = "mercator"
            ctx["shared_viewport"] = [9,49,13,53]
        maps[sid]=ctx
    return story,bp,word_map,final,approved,maps
