"""B1-06: source-frozen 30fps G1/G2/G3->G4 compiler, not a renderer."""
from __future__ import annotations

import copy

from backend.app.contracts import ContractViolation, validate_document, validate_visual_blueprint
from backend.app.director.layout import selected_layout
from backend.app.director.layers import build_layers
from backend.app.director.motion import compile_event, presets
from backend.app.director.camera import build_camera
from backend.app.director.fingerprint import canonical, digest, dependency_identity
from backend.app.director.timing import bind_beats
from backend.app.director.staging import group_staging
from backend.app.projects.models import StoryCandidate

STYLE_VERSION = "HistoryEditorialPaper.v1"


def _block(code, entity, help_text):
    raise ContractViolation(code, entity, help_text)


def _scene(plan, staging, beats, assets, requirements, maps, font_measure):
    layout = selected_layout(plan)
    sid = plan["setup_id"]
    layers, refs = build_layers(plan, assets, requirements, maps=maps, font_measure=font_measure)
    scene_start, scene_end = staging["start_frame"], staging["end_frame"]
    duration = scene_end - scene_start
    if not layers:
        _block("LAYOUT_SOURCE_MISSING", sid, "A compiled scene cannot have zero real layers.")
    sequence = []
    events = []
    relations = []
    groups = {"group_" + sid}
    for i, beat in enumerate(beats):
        focus = refs.get(beat["focus_ref"])
        if not focus:
            _block("FOCUS_LAYER_MISSING", beat["beat_id"],
                   "Author a focus reference that maps to a real registered template layer.")
        origin = beat["start_frame"] - scene_start
        end = beat["end_frame"] - scene_start
        if origin < 0 or end > duration or end <= origin:
            _block("FRAME_INTERVAL_INVALID", beat["beat_id"], "Native WAV beat must remain inside its owning scene.")
        active = list(dict.fromkeys([focus] + [refs[r["ref"]] for r in beat["staging"]
                                          if r["ref"] in refs]))
        sequence.append({"beat_id": beat["beat_id"], "local_start_frame": origin,
                         "local_end_frame": end, "focus_layer_id": focus,
                         "activated_layer_ids": active, "hidden_layer_ids": []})
        for item in beat["staging"]:
            if item["ref"] not in refs:
                _block("STAGING_LAYER_UNKNOWN", beat["beat_id"],
                       "Every staged ref must resolve to an actual compiled layer.")
        for relation in plan["editorial_direction"]["visual_beats"][i]["relationships"]:
            a, b = refs.get(relation["from_ref"]), refs.get(relation["to_ref"])
            if a and b and relation["relation"] in ("foreground_of", "inside", "follows",
                                                      "clips", "tracks", "aligns_with",
                                                      "evidence_for", "compares_to"):
                rel = {"from_id": a, "to_id": b, "relation": relation["relation"]}
                if rel not in relations:
                    relations.append(rel)
        # Dispatch from authored stage direction. Never substitute an unrelated preset.
        authored = plan["editorial_direction"]["visual_beats"][i]
        stage = authored["staging"]
        hints = {step["motion_hint"] for step in stage}
        if len(hints) != 1:
            _block("MOTION_HINT_UNSUPPORTED", beat["beat_id"],
                   "Use one coherent authored motion for this cue.")
        hint = next(iter(hints))
        target = next(x for x in layers if x["layer_id"] == focus)
        allowed = layout["allowed_presets"]
        kind = None
        params = {}
        if hint == "stagger":
            order = []
            if plan["template_id"] == "T03":
                cards = {c["card_id"]: c for c in plan["template_payload"]["cards"]}
                order = [refs[cards[cid]["asset_slot_id"]]
                         for cid in plan["template_payload"]["card_reveal_order"]]
            else:
                order = [refs[step["ref"]] for step in sorted(stage, key=lambda x: x["priority"])
                         if step["ref"] in refs]
            if len(order) < 2 or len(set(order)) != len(order):
                _block("MOTION_STAGGER_INVALID", beat["beat_id"],
                       "Stagger must identify at least two distinct registered layers.")
            kind = "stagger-reveal"
            params["ordered_layer_ids"] = order
            target = next(x for x in layers if x["layer_id"] == order[0])
        elif hint == "line_draw":
            if plan["template_id"] == "T04":
                target = next((x for x in layers if x["layer_kind"] == "route"), None)
                kind = "route-line-draw"
            elif plan["template_id"] == "T10":
                target = next((x for x in layers if x["layer_kind"] == "annotation"), None)
                kind = "editorial-connector-draw"
            if target is None or kind is None:
                _block("MOTION_HINT_UNSUPPORTED", beat["beat_id"],
                       "Line drawing needs a registered geographic route or editorial connector.")
        elif hint == "subtle_push":
            if target["layer_kind"] in ("map", "archival_photo", "portrait", "document"):
                kind = "camera-push" if "camera-push" in allowed else None
            elif "title-mask-reveal" in allowed:
                kind = "title-mask-reveal"
            else:
                kind = "freeze-hold" if "freeze-hold" in allowed else None
        elif hint == "parallax":
            kind = "parallax-layers"
        elif hint == "wipe":
            kind = ("map-region-wipe" if target["layer_kind"] in ("map", "territory")
                    else "mask-transition")
        elif hint == "cut":
            kind = "hard-cut"
        elif hint == "track":
            kind = "camera-pan"
        elif hint == "zoom":
            kind = "camera-push"
        elif hint == "none":
            kind = "freeze-hold"
        if kind not in allowed or kind not in presets() or target is None:
            _block("MOTION_HINT_UNSUPPORTED", beat["beat_id"],
                   "Motion hint is incompatible with this template, layer or registered grammar.")
        if target["layer_kind"] not in presets()[kind]["compatible_layer_kinds"]:
            _block("MOTION_KIND_INVALID", beat["beat_id"],
                   "Authored motion cannot target this layer kind.")
        cue_start = beat["cue_start_frame"] - scene_start
        event_at = max(origin, cue_start)
        if event_at >= end:
            _block("MOTION_TIME_INVALID", beat["beat_id"], "Spoken cue occurs after its authored beat window.")
        spec = presets()[kind]
        length = min(end-event_at, spec["default_duration_frames"], spec["max_duration_frames"])
        if length < spec["min_duration_frames"]:
            _block("MOTION_TIME_INVALID", beat["beat_id"], "No native frames remain for this authored event.")
        evidence = {"source_sha": next((r["original_sha256"] for r in assets.values()
                                        if r["candidate_id"] == target["asset_id"]), ""),
                    "claim_ids": plan["claim_refs"],
                    **(maps or {}).get(sid, {})}
        event = compile_event(kind, target, layers,
                              event_id="event_" + beat["beat_id"],
                              start_frame=event_at, duration_frames=length,
                              cue_word_id=beat["word_ids"][0], evidence=evidence)
        events.append(event)
    camera = build_camera(plan, layers, beats, refs, duration_frames=duration,
                          limits=layout["camera_limits"])
    if camera["focus_path"][-1]["at_frame"] >= duration:
        _block("CAMERA_FRAME_INVALID", sid, "Camera focus may not exceed its scene.")
    extra_carry = plan["editorial_direction"]["visual_beats"][-1]["continuity"]["carry_refs"]
    carry = [refs[r] for r in extra_carry if r in refs]
    transition = {"hard_cut": "hard_cut", "cross_dissolve": "cross_dissolve",
                  "match_cut": "match_cut", "mask_reveal": "mask_reveal"}.get(
        plan["editorial_direction"]["transition_intent"], "hard_cut")
    return {
        "scene_id": "scene_" + sid, "setup_id": sid,
        "template_id": plan["template_id"], "variant_id": plan["variant_id"],
        "start_frame": scene_start, "duration_frames": duration,
        "asset_ids": list(dict.fromkeys(layer["asset_id"] for layer in layers if layer["asset_id"])),
        "layers": layers, "events": events, "camera": camera,
        "transition_out": {"type": transition, "duration_frames": 0},
        "story_cue_span": {"first_word_id": beats[0]["word_ids"][0],
                           "last_word_id": beats[-1]["word_ids"][-1]},
        "staging": {"composition_graph": {"group_ids": sorted(groups), "edges": relations},
                    "beat_sequence": sequence,
                    "continuity_group_id": plan["editorial_direction"]["visual_beats"][0]["continuity"]["group_id"],
                    "carry_layer_ids": carry, "entry_focus_layer_id": sequence[0]["focus_layer_id"],
                    "exit_focus_layer_id": sequence[-1]["focus_layer_id"]},
    }


def compile_timeline(story: dict, blueprint: dict, word_map: dict, final_audio: dict,
                     approved_assets: dict, *,
                     maps: dict | None = None, font_measure=None,
                     font_identity: dict | None = None,
                     expected_story_sha256: str | None = None) -> dict:
    """Compile explicitly frozen inputs, supplied only from current approved store
    or a clearly marked synthetic integration harness. No implicit G3 approval."""
    story_id = StoryCandidate.parse(story).sha256
    if expected_story_sha256 is None or expected_story_sha256 != story_id or blueprint["story_revision_sha256"] != story_id:
        _block("STORY_SHA_MISMATCH", story["project"]["project_id"],
               "Load and pin the current G1 StoryPackage SHA before compiling.")
    validate_visual_blueprint(story, blueprint)
    validate_document("WordTimingMap.v1", word_map)
    validate_document("FinalAudio.v1", final_audio)
    if (final_audio["project_id"] != blueprint["project_id"] or
            final_audio["audio_sha256"] != word_map["audio_sha256"] or
            final_audio["transcript_sha256"] != word_map["transcript_sha256"] or
            final_audio["sample_rate"] != word_map["sample_rate"] or
            final_audio["story_revision_sha256"] != story_id):
        _block("ALIGNMENT_SOURCE_STALE", blueprint["project_id"],
               "Word map and final approved WAV must share project/story/audio/transcript identities.")
    if not approved_assets or font_measure is None or not font_identity:
        _block("COMPILER_DEPENDENCY_MISSING", blueprint["project_id"],
               "Bind current approved G3 sources and measured pinned font identity.")
    required = {r["requirement_id"]: r for r in story["asset_requirements"]}
    if any(r not in required for r in approved_assets):
        _block("G3_ASSET_UNAPPROVED", blueprint["project_id"], "G3 snapshot references an unknown G1 requirement.")
    maps = maps or {}
    for plan in blueprint["setup_plans"]:
        sid = plan["setup_id"]
        current = maps.get(sid, {})
        for binding in plan["asset_slot_bindings"]:
            rid = binding["requirement_id"]
            if required[rid]["asset_class"] != "HISTORICAL_MAP":
                continue
            source = current.get("sources", {}).get(rid)
            head = approved_assets.get(rid)
            if head is None:
                _block("G3_ASSET_UNAPPROVED", rid,
                       "Required historical map has no current approved G3 original.")
            if (not source or
                    source["source_original_sha256"] != head["original_sha256"]
                    or source["historical_map"]["source_asset_id"] != head["candidate_id"]
                    or source["historical_map"]["rights_review_record_id"] != head["approval_record_id"]):
                _block("MAP_GEOMETRY_INVALID", sid,
                       "Compile only validated B1-02 period maps with exact original and G3 source identity.")
    windows = bind_beats(blueprint, word_map, audio_sha256=final_audio["audio_sha256"],
                         transcript_sha256=final_audio["transcript_sha256"],
                         audio_total_samples=final_audio["duration_samples"])
    staged = group_staging(windows, final_audio["duration_samples"], word_map["sample_rate"])
    by_setup = {s["setup_id"]: s for s in staged}
    scenes = []
    for plan in blueprint["setup_plans"]:
        beats = [w for w in windows if w["setup_id"] == plan["setup_id"]]
        if not beats or plan["setup_id"] not in by_setup:
            _block("CUE_MISSING", plan["setup_id"], "Every setup needs bound spoken words.")
        scenes.append(_scene(plan, by_setup[plan["setup_id"]], beats,
                             approved_assets, required, maps, font_measure))
    total = (final_audio["duration_samples"]*30 + word_map["sample_rate"]-1)//word_map["sample_rate"]
    last = 0
    for s in scenes:
        if s["start_frame"] != last or s["duration_frames"] < 1:
            _block("FRAME_INTERVAL_INVALID", s["scene_id"], "Scenes must own all WAV frames exactly once.")
        last += s["duration_frames"]
    if last != total:
        _block("FRAME_INTERVAL_INVALID", blueprint["project_id"], "Scene coverage must end at exact WAV frame ceiling.")
    identity = dependency_identity(story_id, final_audio, word_map, approved_assets, maps,
                                   font_identity=font_identity, style_version=STYLE_VERSION)
    result = {"schema_version": "CompiledTimeline.v1",
              "project_id": blueprint["project_id"], "fps": 30,
              "width": 1920, "height": 1080, "total_frames": total,
              "style_version": STYLE_VERSION, "template_registry_version": "1.1.0",
              "motion_registry_version": "1.2.0",
              "story_sha256": story_id, "audio_sha256": final_audio["audio_sha256"],
              "word_map_sha256": digest(word_map),
              "asset_snapshot_sha256": digest(approved_assets),
              "dependency_fingerprint": digest({**identity, "blueprint": blueprint}),
              "scenes": scenes}
    validate_document("CompiledTimeline.v1", result)
    return result


def compile_from_store(store, project_id: str, blueprint: dict, word_map: dict,
                       final_audio: dict, *, maps: dict | None = None,
                       map_requests: dict | None = None,
                       font_measure=None, font_identity: dict | None = None) -> dict:
    """Production authorization: SQLite G1/G2/G3 heads, immutable audio, G3 assets."""
    from backend.app.assets.provenance import AssetCandidates
    from backend.app.assets.resolution import AssetResolution
    from backend.app.projects.gates import GateService
    gate = {x["gate_id"]: x for x in GateService(store).board(project_id)}
    if any(gate[k]["state"] != "APPROVED" for k in ("G1", "G2", "G3")):
        _block("COMPILER_GATE_UNAPPROVED", project_id, "Approve current G1/G2/G3 before compiling G4.")
    story_obj = store.get_story(project_id)
    if story_obj.sha256 != blueprint["story_revision_sha256"]:
        _block("STORY_SHA_MISMATCH", project_id, "Only the current approved StoryPackage may be compiled.")
    # Proof of the exact FINAL WAV artifact, not a caller-provided approved=true flag.
    wav = store.get_artifact(final_audio["audio_sha256"])
    import hashlib
    if hashlib.sha256(wav).hexdigest() != final_audio["audio_sha256"]:
        _block("ALIGNMENT_SOURCE_STALE", project_id, "The immutable approved WAV hash does not match.")
    from backend.app.voice.workflow import word_map_ready
    approved = {}
    with store._connection() as db:
        if not word_map_ready(db, project_id):
            _block("WORD_MAP_STALE", project_id, "Current successful G2 alignment job and word map are required.")
        g2_head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                             (project_id,)).fetchone()
        row = db.execute(
            "SELECT f.final_json,w.map_json,w.map_sha256 FROM final_audio f JOIN word_maps w "
            "ON w.approval_id=f.approval_id AND w.project_id=f.project_id "
            "WHERE f.project_id=? AND f.approval_id=?",
            (project_id, g2_head[0])).fetchone()
        from backend.app.director.fingerprint import digest
        import json
        if (not row or json.loads(row[0]) != final_audio or
                json.loads(row[1]) != word_map or digest(word_map) != row[2]):
            _block("WORD_MAP_STALE", project_id, "Caller supplied non-current or modified G2 WAV/WordTimingMap.")
        for requirement in story_obj.data()["asset_requirements"]:
            rid = requirement["requirement_id"]
            source = AssetCandidates._source_tx(db, project_id, rid)
            head = AssetResolution._head(db, project_id, rid, source["requirement_sha256"])
            if not head:
                if requirement["required"]:
                    _block("G3_ASSET_UNAPPROVED", rid, "G3 must approve the current required asset source.")
                continue
            original = store.get_artifact(head["original_sha256"])
            if hashlib.sha256(original).hexdigest() != head["original_sha256"]:
                _block("G3_ASSET_UNAPPROVED", rid, "Immutable approved original bytes failed SHA validation.")
            approved[rid] = {**head, "asset_class": requirement["asset_class"],
                             "source_kind": head.get("evidence", {}).get("source_kind", "")}
    # Caller-supplied map booleans are not G3 source truth. Re-ingest every
    # requested geographic layer against the current project/requirement head.
    from backend.app.maps.ingest import ingest_current_approved
    from backend.app.maps.projection import common_viewport
    if maps:
        _block("MAP_GEOMETRY_INVALID", project_id,
               "Production map contexts must be derived from the current SQLite G3 approvals, not caller JSON.")
    trusted_maps = {}
    for plan in blueprint["setup_plans"]:
        map_payload = plan["template_payload"]
        requested = []
        if "map" in map_payload and isinstance(map_payload["map"], dict):
            requested.append(map_payload["map"])
        for key in ("before_map","after_map"):
            if key in map_payload:
                requested.append(map_payload[key])
        if not requested:
            continue
        sid = plan["setup_id"]
        ctx = {"sources": {}, "reviewed_period_map": True}
        for item in requested:
            rid = item["map_requirement_id"]
            request = (map_requests or {}).get(rid)
            if not request or request.get("year") != item["year"]:
                _block("MAP_GEOMETRY_INVALID", sid,
                       "Supply an explicit period-map ingest request matching authored map year.")
            result = ingest_current_approved(
                store, project_id, rid, request["map_record"], year=request["year"],
                feature_ids=request["feature_ids"],
                route_feature_id=request.get("route_feature_id"),
                reviewed_tie_points=request.get("reviewed_tie_points"))
            ctx["sources"][rid] = result
            ctx["historical_map_id"] = result["historical_map"]["historical_map_id"]
            ctx["era_year"] = request["year"]
            ctx["approved_feature_ids"] = [x["id"] for x in result["features"]]
            ctx["route_feature_id"] = result.get("route_feature_id")
            ctx["geometry_type"] = "LineString" if ctx["route_feature_id"] else None
        if plan["template_id"] == "T07":
            source = list(ctx["sources"].values())
            viewport = common_viewport(source[0]["historical_map"], source[1]["historical_map"])
            ctx["shared_projection"] = viewport["projection"]
            ctx["shared_viewport"] = viewport["bbox"]
        trusted_maps[sid] = ctx
    return compile_timeline(story_obj.data(), blueprint, word_map, final_audio, approved,
                            maps=trusted_maps, font_measure=font_measure, font_identity=font_identity,
                            expected_story_sha256=story_obj.sha256)



def revise_g4(store, project_id: str, previous: dict, original_blueprint: dict,
              edited_blueprint: dict, word_map: dict, final_audio: dict,
              approved_assets: dict, *, expected_revision: int, operator_reason: str,
              maps: dict | None = None, font_measure=None, crop_overrides: dict | None = None) -> dict:
    """CAS-guarded presentation-only local edit; never auto-approve G4/G5.

    Only changed scenes are compiled anew. The unchanged scene dictionaries
    are retained byte-for-byte from the previous immutable timeline.
    """
    from backend.app.projects.gates import GateService
    from backend.app.projects.revisions import mark_stale
    if not isinstance(operator_reason, str) or not operator_reason.strip():
        _block("G4_EDIT_INTENT_MISSING", project_id, "Operator must record a meaningful presentation edit reason.")
    if store.revision(project_id) != expected_revision:
        _block("APPROVAL_REVISION_CONFLICT", project_id, "Reload project revision before revising G4.")
    if previous["story_sha256"] != original_blueprint["story_revision_sha256"]:
        _block("STORY_SHA_MISMATCH", project_id, "Prior timeline does not match frozen G1 story.")
    if (digest(word_map) != previous["word_map_sha256"] or
            final_audio["audio_sha256"] != previous["audio_sha256"] or
            digest(approved_assets) != previous["asset_snapshot_sha256"]):
        _block("G4_SOURCE_EDIT_FORBIDDEN", project_id,
               "G4 cannot replace the frozen approved WAV, word map or G3 asset snapshot.")
    old = original_blueprint["setup_plans"]
    revised = edited_blueprint["setup_plans"]
    if (edited_blueprint["project_id"] != original_blueprint["project_id"] or
            edited_blueprint["story_revision_sha256"] != original_blueprint["story_revision_sha256"] or
            len(old) != len(revised)):
        _block("G4_SOURCE_EDIT_FORBIDDEN", project_id, "G4 edits cannot change project or frozen G1 setup identity.")
    allowed_plan = {"variant_id", "layout_control", "direction_revision", "editorial_direction"}
    changed = set()
    for a, b in zip(old, revised):
        if {k:v for k,v in a.items() if k not in allowed_plan} != {
                k:v for k,v in b.items() if k not in allowed_plan}:
            _block("G4_SOURCE_EDIT_FORBIDDEN", a["setup_id"],
                   "Cannot edit G1 claim, source requirement, template or G3 slot binding at G4.")
        da, db = a["editorial_direction"], b["editorial_direction"]
        for key in da:
            if key == "camera_intent":
                continue
            if key == "visual_beats":
                aa, bb = da[key], db[key]
                if len(aa) != len(bb):
                    _block("G4_SOURCE_EDIT_FORBIDDEN", a["setup_id"],
                           "Cannot add or delete authored cue beats at G4.")
                for source_beat, edited_beat in zip(aa, bb):
                    if ({k:v for k,v in source_beat.items() if k != "staging"} !=
                            {k:v for k,v in edited_beat.items() if k != "staging"}):
                        _block("G4_SOURCE_EDIT_FORBIDDEN", a["setup_id"],
                               "G1 narration cues, word identity and claim connections remain immutable.")
            elif da[key] != db.get(key):
                _block("G4_SOURCE_EDIT_FORBIDDEN", a["setup_id"],
                       "G4 cannot change authored on-screen factual text, source or voice timing.")
        if a != b:
            revision = b["direction_revision"]
            if (revision["kind"] != "operator_visual_edit" or not revision["operator_confirmed"]
                    or revision["source_story_revision_sha256"] != previous["story_sha256"]
                    or not revision["edit_reason"]):
                _block("G4_EDIT_INTENT_MISSING", a["setup_id"],
                       "Record an authorized operator direction_revision and source SHA.")
            changed.add(a["setup_id"])
    crop_overrides = crop_overrides or {}
    changed.update(crop_overrides.keys())
    if not changed or not changed <= {p["setup_id"] for p in old}:
        _block("G4_EDIT_INVALID", project_id, "Select at least one existing scene to revise.")
    # Reject presentation-only input when current upstream approvals have changed.
    states = {x["gate_id"]: x["state"] for x in GateService(store).board(project_id)}
    if any(states[k] != "APPROVED" for k in ("G1", "G2", "G3")):
        _block("COMPILER_GATE_UNAPPROVED", project_id, "Current G1/G2/G3 must be approved at G4 edit.")
    story = store.get_story(project_id).data()
    validate_visual_blueprint(story, edited_blueprint)
    if StoryCandidate.parse(story).sha256 != previous["story_sha256"]:
        _block("STORY_SHA_MISMATCH", project_id, "Current G1 story changed since prior compiled timeline.")
    # Reject stale caller snapshots against the current persisted G2/G3 approval heads.
    # Equality among caller dictionaries is not sufficient authorization.
    from backend.app.assets.provenance import AssetCandidates
    from backend.app.assets.resolution import AssetResolution
    from backend.app.voice.workflow import word_map_ready
    import hashlib
    import json
    with store._connection() as db:
        if not word_map_ready(db, project_id):
            _block("WORD_MAP_STALE", project_id, "G4 requires current persisted G2 alignment.")
        g2_head = db.execute(
            "SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
            (project_id,)).fetchone()
        row = db.execute(
            "SELECT f.final_json,w.map_json,w.map_sha256 FROM final_audio f JOIN word_maps w "
            "ON f.project_id=w.project_id AND f.approval_id=w.approval_id "
            "WHERE f.project_id=? AND f.approval_id=?",
            (project_id, g2_head[0] if g2_head else None)).fetchone()
        if (not row or json.loads(row[0]) != final_audio
                or json.loads(row[1]) != word_map or row[2] != digest(word_map)):
            _block("WORD_MAP_STALE", project_id, "Edited blueprint must use persisted current G2 WAV and word map.")
        if hashlib.sha256(store.get_artifact(final_audio["audio_sha256"])).hexdigest() != final_audio["audio_sha256"]:
            _block("ALIGNMENT_SOURCE_STALE", project_id, "Approved final WAV original bytes changed.")
        verified_assets = {}
        for requirement in story["asset_requirements"]:
            rid = requirement["requirement_id"]
            source = AssetCandidates._source_tx(db, project_id, rid)
            head = AssetResolution._head(db, project_id, rid, source["requirement_sha256"])
            if not head:
                if requirement["required"]:
                    _block("G3_ASSET_UNAPPROVED", rid, "The current G3 source has no eligible approved original.")
                continue
            if hashlib.sha256(store.get_artifact(head["original_sha256"])).hexdigest() != head["original_sha256"]:
                _block("G3_ASSET_UNAPPROVED", rid, "Current G3 original bytes are stale.")
            verified_assets[rid] = {**head, "asset_class": requirement["asset_class"],
                                    "source_kind": head.get("evidence", {}).get("source_kind", "")}
        if verified_assets != approved_assets:
            _block("G4_SOURCE_EDIT_FORBIDDEN", project_id,
                   "Caller G3 snapshot differs from current SQLite rights and approved originals.")
    windows = bind_beats(edited_blueprint, word_map,
                         audio_sha256=final_audio["audio_sha256"],
                         transcript_sha256=final_audio["transcript_sha256"],
                         audio_total_samples=final_audio["duration_samples"])
    staging = {x["setup_id"]: x for x in group_staging(
        windows, final_audio["duration_samples"], word_map["sample_rate"])}
    requirements = {r["requirement_id"]:r for r in story["asset_requirements"]}
    out = copy.deepcopy(previous)
    index = {s["setup_id"]: i for i,s in enumerate(out["scenes"])}
    for plan in revised:
        sid = plan["setup_id"]
        if sid not in changed:
            continue
        rows = [x for x in windows if x["setup_id"] == sid]
        scene = _scene(plan, staging[sid], rows, approved_assets, requirements,
                       maps or {}, font_measure)
        for layer in scene["layers"]:
            crop = crop_overrides.get(sid, {}).get(layer["layer_id"])
            if crop is not None:
                if (set(crop) != {"x","y","w","h"} or
                    any(type(x) not in (int,float) for x in crop.values()) or
                    not (0 <= crop["x"] < 1 and 0 <= crop["y"] < 1 and 0 < crop["w"] <= 1-crop["x"]
                         and 0 < crop["h"] <= 1-crop["y"])):
                    _block("G4_CROP_INVALID", layer["layer_id"], "Keep reviewed original and valid normalized crop.")
                layer["crop_normalized"] = dict(crop)
        unknown = set(crop_overrides.get(sid, {})) - {x["layer_id"] for x in scene["layers"]}
        if unknown:
            _block("G4_CROP_INVALID", sid, "Crop only layers that exist in the selected setup.")
        out["scenes"][index[sid]] = scene
    if all(canonical(out["scenes"][index[sid]]) == canonical(previous["scenes"][index[sid]])
           for sid in changed):
        _block("G4_EDIT_INVALID", project_id,
               "Presentation edit produced no observable scene change; do not bump revision.")
    out["dependency_fingerprint"] = digest({"prior_identity": previous["dependency_fingerprint"],
                                             "new_direction": edited_blueprint,
                                             "crop_overrides": crop_overrides})
    validate_document("CompiledTimeline.v1", out)
    with store._transaction() as db:
        gate = GateService(store)
        revision = gate._check_revision(db, project_id, expected_revision)
        mark_stale(db, project_id, "scene_layout" if edited_blueprint != original_blueprint else "scene_crop")
        db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision+1,project_id))
    return {"timeline": out, "recomputed_setup_ids": sorted(changed),
            "retained_setup_ids": sorted(set(index) - changed),
            "project_revision": expected_revision+1, "stale_gates": ["G4","G5"]}
