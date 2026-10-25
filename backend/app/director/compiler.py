"""B1-06: source-frozen 30fps G1/G2/G3->G4 compiler, not a renderer."""
from __future__ import annotations

import copy

from backend.app.contracts import ContractViolation, validate_document, validate_visual_blueprint
from backend.app.director.layout import selected_layout
from backend.app.director.layers import build_layers
from backend.app.director.motion import compile_event, presets
from backend.app.director.camera import build_camera, compose_camera_events
from backend.app.director.fingerprint import canonical, digest, dependency_identity
from backend.app.director.timing import bind_beats
from backend.app.director.staging import group_staging
from backend.app.projects.models import StoryCandidate

STYLE_VERSION = "HistoryEditorialPaper.v1"


def _block(code, entity, help_text):
    raise ContractViolation(code, entity, help_text)


def _attach_verified_word_spans(layer: dict, event: dict, word_map: dict | None):
    """Derive optional B2 glyph offsets only from exact frozen G2 words and G1 text.

    Repeated/unmatched visible words have ambiguous identity and must not be
    guessed, even if their spelling happens to match a narrated word.
    """
    import re
    from backend.app.voice.word_map import normalized

    text = layer.get("text")
    if text is None or word_map is None:
        _block("MOTION_WORD_SPAN_UNVERIFIED", event["event_id"],
               "Word-level motion requires frozen G2 words and a G1 text layer.")
    ids = (event["params"].get("word_ids") if event["preset_id"] == "kinetic-type"
           else event["params"].get("source_word_ids"))
    if not isinstance(ids, list) or not ids:
        _block("MOTION_WORD_SPAN_UNVERIFIED", event["event_id"],
               "Select a nonempty frozen G2 word identity set.")
    g2 = {w["word_id"]: w for w in word_map["words"]}
    candidates = [(m.start(), m.end(), normalized(m.group()))
                  for m in re.finditer(r"\S+", text)]
    spans = []
    for word_id in ids:
        word = g2.get(word_id)
        if word is None:
            _block("MOTION_WORD_SPAN_UNVERIFIED", event["event_id"],
                   "Word identity is absent from the current immutable G2 map.")
        matching = [(a, b) for a, b, token in candidates
                    if token and token == normalized(word["text"])]
        if len(matching) != 1:
            _block("MOTION_WORD_SPAN_AMBIGUOUS", word_id,
                   "Visible text has no unique exact G2 word occurrence; no inferred glyph binding.")
        a, b = matching[0]
        if any(a < old["end"] and old["start"] < b for old in spans):
            _block("MOTION_WORD_SPAN_AMBIGUOUS", word_id,
                   "Two spoken identities cannot own the same source text glyphs.")
        spans.append({"word_id": word_id, "word_text": word["text"],
                      "start": a, "end": b})
    if layer.get("word_spans") and layer["word_spans"] != spans:
        _block("MOTION_WORD_SPAN_AMBIGUOUS", layer["layer_id"],
               "A second event conflicts with the already derived G2 glyph bindings.")
    layer["word_spans"] = sorted(spans, key=lambda span: span["start"])


def _scene(plan, staging, beats, assets, requirements, maps, font_measure, motion_patches=None, word_map=None, numeric_series=None, reviewed_masks=None):
    layout = selected_layout(plan)
    sid = plan["setup_id"]
    layers, refs = build_layers(plan, assets, requirements, maps=maps,
                                font_measure=font_measure, reviewed_masks=reviewed_masks)
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
        # Staging operations are executable instructions, not metadata to drop.
        # Unsupported animation semantics must block rather than appear as a
        # successful but visually inert compiled event.
        for step in stage:
            operation = step["operation"]
            if operation in ("exit", "reposition"):
                _block("STAGING_OPERATION_UNSUPPORTED", beat["beat_id"],
                       "Exit/reposition need an explicit supported transition; do not silently emit an enter event.")
            if ((operation == "draw_path" and hint != "line_draw")
                    or (operation == "reveal_mask" and hint != "wipe")
                    or (operation == "hold" and hint != "none")
                    or (operation == "focus" and hint not in ("subtle_push", "track", "zoom"))):
                _block("STAGING_OPERATION_UNSUPPORTED", beat["beat_id"],
                       "Authored staging operation and motion hint are incompatible.")
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
            if (plan["template_id"]=="T08" and target["layer_kind"]=="date" and
                    plan["template_payload"]["animation_rule"]=="count_if_intermediates_truthful"):
                kind="number-count"
            elif target["layer_kind"] in ("map", "archival_photo", "portrait", "document"):
                kind = "camera-push" if "camera-push" in allowed else None
            elif "title-mask-reveal" in allowed:
                kind = "title-mask-reveal"
            else:
                kind = None
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
                    **(maps or {}).get(sid, {}), "editorial_connector": plan["template_id"] == "T10"}
        # D01: only an actual authored T08 count cue can consume G1 auxiliary
        # numeric observations. The helper is resolved from SQLite, never from UI.
        if kind == "number-count":
            if target["source_claim_id"] != plan["template_payload"]["fact_claim_id"]:
                _block("MOTION_CLAIM_UNVERIFIED", beat["beat_id"],
                       "Numeric animation must target the frozen authored G1 value.")
            reviewed=(numeric_series or {}).get(target["source_claim_id"])
            if reviewed is None:
                _block("MOTION_NUMBER_SERIES_UNVERIFIED", beat["beat_id"],
                       "An authored count requires its current operator-reviewed G1 series.")
            series_end=reviewed["end_value"]
            if (target["text"].replace(",","") != series_end or
                    reviewed["authored_duration_frames"] != length):
                _block("MOTION_NUMBER_SERIES_INVALID", beat["beat_id"],
                       "Reviewed values must match the displayed source text and exact cue duration.")
            params.update(source_claim_id=target["source_claim_id"],
                          start_value=float(reviewed["start_value"]),
                          end_value=float(series_end),
                          precision=reviewed["precision"],
                          intermediate_truthful=True,
                          approved_numeric_series_id=reviewed["series_id"],
                          approved_numeric_start_text=reviewed["start_value"],
                          approved_numeric_end_text=reviewed["end_value"])
            evidence["number_value"]=float(series_end)
        # Distinct T07 period maps carry independent reviewed geographic truth.
        if target.get("map_binding") is not None:
            selected_map_id = target["map_binding"]["historical_map_id"]
            approved_map = next((source for source in (maps or {}).get(sid, {})
                                 .get("sources", {}).values()
                                 if source["historical_map"]["historical_map_id"] == selected_map_id), None)
            if approved_map is None:
                _block("MOTION_GEOGRAPHY_UNREVIEWED", beat["beat_id"],
                       "The animated map layer must resolve to its exact reviewed source.")
            evidence.update({
                "historical_map_id": selected_map_id,
                "era_year": approved_map.get("event_year",
                    approved_map["historical_map"]["valid_year_from"]),
                "approved_feature_ids": [feature["id"] for feature in approved_map["features"]],
                "reviewed_period_map": True,
            })
        if kind == "camera-pan":
            previous_focus = (refs.get(beats[i-1]["focus_ref"])
                              if i else focus)
            params.update(start_target_layer_id=previous_focus,
                          end_target_layer_id=focus)
        elif kind == "camera-push":
            params["focus_layer_id"] = focus
        event_id = "event_" + beat["beat_id"]
        # Re-enter the canonical grammar with the persisted G4 scalar patch.
        # Never mutate compiled JSON without recompiling its camera/track.
        params.update((motion_patches or {}).get(event_id, {}))
        event = compile_event(kind, target, layers,
                              event_id=event_id,
                              start_frame=event_at, duration_frames=length,
                              cue_word_id=beat["word_ids"][0], params=params, evidence=evidence)
        if kind in ("kinetic-type", "text-highlight"):
            _attach_verified_word_spans(target, event, word_map)
        events.append(event)
    camera = build_camera(plan, layers, beats, refs, duration_frames=duration,
                          limits=layout["camera_limits"])
    camera = compose_camera_events(camera, events, layers, duration_frames=duration,
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
        "asset_ids": list(dict.fromkeys(
            aid for layer in layers for aid in (layer["asset_id"],layer["mask"]["asset_id"]) if aid)),
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
                     expected_story_sha256: str | None = None,
                     numeric_series: dict | None = None,
                     reviewed_masks: dict | None = None) -> dict:
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
    if (font_measure is None or not font_identity or
        (not approved_assets and any(r["required"] for r in story["asset_requirements"]))):
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
                             approved_assets, required, maps, font_measure,
                             word_map=word_map, numeric_series=numeric_series,
                             reviewed_masks=(reviewed_masks or {}).get(plan["setup_id"])))
    # A two-surface wipe is authorized only by the outgoing G1-authored
    # transition intent AND an incoming boundary event at frame zero. Other
    # single-layer wipes are not silently promoted to a cross-scene transition.
    for index in range(1, len(scenes)):
        outgoing, incoming = scenes[index-1], scenes[index]
        boundary = [e for e in incoming["events"] if
                    e["preset_id"] == "mask-transition" and e["start_frame"] == 0]
        if (outgoing["transition_out"]["type"] == "mask_reveal" and
                len(boundary) == 1 and
                0 < boundary[0]["duration_frames"] <= min(
                    outgoing["duration_frames"], incoming["duration_frames"])):
            outgoing["transition_out"]["duration_frames"] = boundary[0]["duration_frames"]
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


def _derive_current_masks(store,project_id,blueprint,approved_assets):
    """Real G3-reviewed derivative resolver, never a caller-supplied raster/CSS."""
    from backend.app.assets.resolution import AssetResolution
    owner=AssetResolution(store)
    result={}
    for plan in blueprint["setup_plans"]:
        if plan["template_id"]!="T02" or plan["template_payload"]["cutout_policy"]!="use_reviewed_mask":
            continue
        slot=plan["template_payload"]["portrait_slot_id"]
        authored=next((x for x in plan["editorial_direction"]["asset_slots"]
                       if x["slot_id"]==slot),None)
        if not authored:
            _block("PORTRAIT_MASK_UNREVIEWED",slot,"No frozen authored T02 portrait source.")
        rid=authored["requirement_id"]
        primary=approved_assets.get(rid)
        if not primary:
            _block("PORTRAIT_MASK_UNREVIEWED",slot,"Approved original missing for reviewed derivative.")
        review=owner.reviewed_mask(project_id,rid,slot,primary["candidate_id"])
        if review is None:
            _block("PORTRAIT_MASK_UNREVIEWED",slot,"Current G3 approval must include this mask derivative.")
        if review["parent_original_sha256"]!=primary["original_sha256"]:
            _block("PORTRAIT_MASK_UNREVIEWED",slot,"Derivative parent G3 original bytes changed.")
        result[plan["setup_id"]]={slot:review}
    return result


def compile_from_store(store, project_id: str, blueprint: dict, word_map: dict,
                       final_audio: dict, *, maps: dict | None = None,
                       map_requests: dict | None = None,
                       font_measure=None, font_identity: dict | None = None) -> dict:
    """Production authorization: SQLite G1/G2/G3 heads, immutable audio, G3 assets."""
    from backend.app.assets.provenance import AssetCandidates
    from backend.app.assets.resolution import AssetResolution
    from backend.app.projects.gates import GateService
    start_revision = store.revision(project_id)
    gate = {x["gate_id"]: x for x in GateService(store).board(project_id)}
    if any(gate[k]["state"] != "APPROVED" for k in ("G1", "G2", "G3")):
        _block("COMPILER_GATE_UNAPPROVED", project_id, "Approve current G1/G2/G3 before compiling G4.")
    story_obj = store.get_story(project_id)
    # A caller-supplied measurement callback is not authoritative font evidence.
    # Reconstruct the pinned GDI face from actual Windows font file bytes.
    from backend.app.director.layout import windows_font_measure
    from pathlib import Path
    import os
    if not font_identity or font_identity.get("measurement_engine") != "win32_gdi":
        _block("FONT_IDENTITY_STALE", project_id, "Production G4 needs a pinned native Windows GDI font.")
    font_file = Path(os.environ["WINDIR"]) / "Fonts" / font_identity["font_file"]
    font_measure, actual_font = windows_font_measure(str(font_file), font_identity["font_sha256"])
    if actual_font != font_identity:
        _block("FONT_IDENTITY_STALE", project_id, "Font face or measurement bytes differ from pinned G4 baseline.")
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
    # Read G1 auxiliary heads AFTER G1/G2 approval and source verification.
    # No external HTTP supplied series dictionary is allowed in production.
    from backend.app.projects.numeric_series import NumericSeries
    numeric_owner=NumericSeries(store)
    numeric={}
    for plan in blueprint["setup_plans"]:
        if (plan["template_id"]=="T08" and
                plan["template_payload"]["animation_rule"]=="count_if_intermediates_truthful"):
            claim=plan["template_payload"]["fact_claim_id"]
            result=numeric_owner.resolved_for(project_id,claim)
            if result is None:
                _block("MOTION_NUMBER_SERIES_UNVERIFIED",claim,"Review a G1 numeric series before compiling authored counting.")
            numeric[claim]=result
    # Caller-supplied compiled map contexts cannot authorize historic geography.
    if maps:
        _block("MAP_GEOMETRY_INVALID", project_id,
               "Production map contexts must be re-ingested from current G3 source bytes.")
    trusted_maps = _derive_trusted_maps(store, project_id, story_obj.data(),
                                        blueprint, map_requests or {})
    trusted_masks = _derive_current_masks(store,project_id,blueprint,approved)
    result = compile_timeline(story_obj.data(), blueprint, word_map, final_audio, approved,
                              maps=trusted_maps, font_measure=font_measure,
                              font_identity=font_identity, expected_story_sha256=story_obj.sha256,
                              numeric_series=numeric,reviewed_masks=trusted_masks)
    from backend.app.director import draft
    draft.publish(store, project_id, result, blueprint, trusted_maps, map_requests or {},
                  font_identity, expected_revision=start_revision,
                  reviewed_masks=trusted_masks)
    return result


def _derive_trusted_maps(store, project_id, story: dict, blueprint: dict, map_requests: dict) -> dict:
    """Re-ingest B1-02 geometry from immutable G3 originals, never caller maps."""
    from backend.app.maps.ingest import ingest_current_approved
    from backend.app.maps.projection import common_viewport
    trusted_maps = {}
    for plan in blueprint["setup_plans"]:
        map_payload = plan["template_payload"]
        requested = []
        if "map" in map_payload and isinstance(map_payload["map"], dict):
            requested.append(map_payload["map"])
        for key in ("before_map","after_map"):
            if key in map_payload:
                requested.append(map_payload[key])
        if plan["template_id"] == "T10" and map_payload.get("map_requirement_id"):
            rid = map_payload["map_requirement_id"]
            requirement = next((r for r in story["asset_requirements"]
                                if r["requirement_id"] == rid), None)
            if (requirement is None or requirement["asset_class"] != "HISTORICAL_MAP"
                    or requirement["start_year"] != requirement["end_year"]):
                _block("MAP_PERIOD_MISMATCH", rid,
                       "T10 region backdrop needs one exact G1 year and current G3 source.")
            requested.append({"map_requirement_id": rid, "year": requirement["start_year"]})
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
    return trusted_maps




def revise_g4(store, project_id: str, previous: dict, original_blueprint: dict,
              edited_blueprint: dict, word_map: dict, final_audio: dict,
              approved_assets: dict, *, expected_revision: int, operator_reason: str,
              maps: dict | None = None, font_measure=None, crop_overrides: dict | None = None,
              layer_overrides: dict | None = None, motion_overrides: dict | None = None,
              asset_selection_overrides: dict | None = None) -> dict:
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
            # Operator's authorized variant selection is a presentation-only
            # field, never a change to G1 facts/claims/word cues or G3 sources.
            if key in ("camera_intent", "layout_variant_hint"):
                continue
            if key == "visual_beats":
                aa, bb = da[key], db[key]
                if len(aa) != len(bb):
                    _block("G4_SOURCE_EDIT_FORBIDDEN", a["setup_id"],
                           "Cannot add or delete authored cue beats at G4.")
                for source_beat, edited_beat in zip(aa, bb):
                    editable = {"staging", "focus_move"}
                    if ({k:v for k,v in source_beat.items() if k not in editable} !=
                            {k:v for k,v in edited_beat.items() if k not in editable}):
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
    layer_overrides = layer_overrides or {}
    motion_overrides = motion_overrides or {}
    asset_selection_overrides = asset_selection_overrides or {}
    changed.update(asset_selection_overrides.keys())
    changed.update(crop_overrides.keys())
    changed.update(layer_overrides.keys())
    changed.update(motion_overrides.keys())
    if not changed or not changed <= {p["setup_id"] for p in old}:
        _block("G4_EDIT_INVALID", project_id, "Select at least one existing scene to revise.")
    # Reject presentation-only input when current upstream approvals have changed.
    states = {x["gate_id"]: x["state"] for x in GateService(store).board(project_id)}
    if any(states[k] != "APPROVED" for k in ("G1", "G2", "G3")):
        _block("COMPILER_GATE_UNAPPROVED", project_id, "Current G1/G2/G3 must be approved at G4 edit.")
    story = store.get_story(project_id).data()
    validate_document("VisualBlueprint.v1", edited_blueprint)
    validate_visual_blueprint(story, edited_blueprint)
    if StoryCandidate.parse(story).sha256 != previous["story_sha256"]:
        _block("STORY_SHA_MISMATCH", project_id, "Current G1 story changed since prior compiled timeline.")
    # A self-declared source hash is not authorization. The head is committed
    # only by production compile_from_store after current G1/G2/G3 validation.
    from backend.app.director import draft
    trusted = draft.load(store, project_id)
    if trusted["revision"] != expected_revision:
        _block("G4_DRAFT_STALE", project_id, "Current SQLite revision no longer matches trusted G4 draft.")
    if canonical(previous) != canonical(trusted["timeline"]):
        _block("G4_DRAFT_TAMPERED", project_id,
               "The complete previous CompiledTimeline differs from the immutable current draft.")
    if canonical(original_blueprint) != canonical(trusted["blueprint"]):
        _block("G4_BLUEPRINT_TAMPERED", project_id,
               "Original visual blueprint does not match the registered draft source plan.")
    manifest = trusted["manifest"]
    persisted_layers = copy.deepcopy(manifest.get("layer_overrides", {}))
    persisted_crops = copy.deepcopy(manifest.get("crop_overrides", {}))
    persisted_motion = copy.deepcopy(manifest.get("motion_overrides", {}))
    persisted_selections = copy.deepcopy(manifest.get("asset_selection_overrides", {}))
    # A new registered variant owns a new geometry family; old operator pixel
    # offsets must not silently carry into a different frozen slot layout.
    for prior_plan, next_plan in zip(old, revised):
        if prior_plan["variant_id"] != next_plan["variant_id"]:
            persisted_layers.pop(next_plan["setup_id"], None)
    for sid, rows in layer_overrides.items():
        if not isinstance(rows, dict):
            _block("G4_LAYOUT_INVALID", sid, "Layer edits must identify reviewed scene layer IDs.")
        persisted_layers.setdefault(sid, {}).update(copy.deepcopy(rows))
    for sid, rows in crop_overrides.items():
        if not isinstance(rows, dict):
            _block("G4_CROP_INVALID", sid, "Crop edits must identify reviewed scene layer IDs.")
        persisted_crops.setdefault(sid, {}).update(copy.deepcopy(rows))
    for sid, rows in asset_selection_overrides.items():
        if not isinstance(rows, dict):
            _block("G4_ASSET_SELECTION_FORBIDDEN",sid,"Expected G3-authorized per-layer selection map.")
        persisted_selections.setdefault(sid, {}).update(copy.deepcopy(rows))
    for sid, rows in motion_overrides.items():
        if not isinstance(rows, dict):
            _block("G4_MOTION_INVALID", sid, "Motion edits must identify authored event IDs.")
        persisted_motion.setdefault(sid, {}).update(copy.deepcopy(rows))
    if manifest["gate_heads"] != draft.current_gate_heads(store, project_id):
        _block("G4_SOURCE_STALE", project_id,
               "A current G1/G2/G3 approval identity changed after the trusted draft.")
    from backend.app.director.layout import windows_font_measure
    from pathlib import Path
    import os
    font = manifest["font_identity"]
    if font.get("measurement_engine") != "win32_gdi":
        _block("FONT_IDENTITY_STALE", project_id, "Stored G4 draft lacks native pinned GDI font.")
    font_file = Path(os.environ["WINDIR"]) / "Fonts" / font["font_file"]
    font_measure, measured_identity = windows_font_measure(str(font_file), font["font_sha256"])
    if measured_identity != font:
        _block("FONT_IDENTITY_STALE", project_id, "G4 font source changed since initial compiler snapshot.")
    saved_maps = manifest["maps"]
    if maps is not None and canonical(maps) != canonical(saved_maps):
        _block("G4_MAP_CONTEXT_INVALID", project_id,
               "Caller map features/projection/period are not trusted G3 geography.")
    current_maps = _derive_trusted_maps(store, project_id, story,
                                       trusted["blueprint"], manifest["map_requests"])
    if canonical(current_maps) != canonical(saved_maps):
        _block("G4_MAP_SOURCE_STALE", project_id,
               "Historical map context differs from currently reviewed G3 source geometry.")
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
    from backend.app.projects.numeric_series import NumericSeries
    numeric_owner=NumericSeries(store)
    numeric={}
    for plan in revised:
        if plan["template_id"]=="T08" and plan["template_payload"]["animation_rule"]=="count_if_intermediates_truthful":
            claim=plan["template_payload"]["fact_claim_id"]
            result=numeric_owner.resolved_for(project_id,claim)
            if result is None:
                _block("MOTION_NUMBER_SERIES_UNVERIFIED",claim,"Current G1 auxiliary review is required.")
            numeric[claim]=result
    trusted_masks=_derive_current_masks(store,project_id,edited_blueprint,approved_assets)
    if trusted_masks != manifest.get("reviewed_masks",{}):
        _block("G4_MASK_SOURCE_STALE",project_id,"Current G3 mask review changed since frozen G4 baseline.")
    out = copy.deepcopy(trusted["timeline"])
    index = {s["setup_id"]: i for i,s in enumerate(out["scenes"])}
    for plan in revised:
        sid = plan["setup_id"]
        if sid not in changed:
            continue
        rows = [x for x in windows if x["setup_id"] == sid]
        scene = _scene(plan, staging[sid], rows, approved_assets, requirements,
                       current_maps, font_measure, persisted_motion.get(sid, {}), word_map,
                       numeric_series=numeric,
                       reviewed_masks=trusted_masks.get(sid))
        # G4 selects from an existing explicitly reapproved G3 same-slot pool.
        # It cannot alter G1 requirement/claim, G2 cues or G3 approval head.
        from backend.app.assets.resolution import AssetResolution
        resolver=AssetResolution(store)
        planned_selections=persisted_selections.get(sid,{})
        layers_by_id={layer["layer_id"]:layer for layer in scene["layers"]}
        if set(planned_selections)-set(layers_by_id):
            _block("G4_ASSET_SELECTION_FORBIDDEN",sid,"Only frozen existing scene layers are selectable.")
        for layer_id,choice in planned_selections.items():
            layer=layers_by_id[layer_id]
            if (layer["layer_kind"] in ("map","territory") or
                not layer["source_asset_slot_id"] or layer["source_asset_slot_id"]!=choice.get("slot_id") or
                layer["asset_id"] is None):
                _block("G4_ASSET_SELECTION_FORBIDDEN",layer_id,"No same-slot rights-backed source or map re-review.")
            authored=next((slot for slot in plan["editorial_direction"]["asset_slots"]
                           if slot["slot_id"]==layer["source_asset_slot_id"]),None)
            if not authored or authored["requirement_id"]!=choice.get("requirement_id"):
                _block("G4_ASSET_SELECTION_FORBIDDEN",layer_id,"Frozen G1 source requirement changed.")
            pool=resolver.approved_slot_options(project_id,choice["requirement_id"],choice["slot_id"])
            eligible=next((x for x in pool["options"] if
                           x["candidate_id"]==choice.get("candidate_id") and
                           x["review_approval_id"]==choice.get("review_approval_id") and
                           x["original_sha256"]==choice.get("original_sha256")),None)
            if (not eligible or pool["choice_set_id"]!=choice.get("choice_set_id") or
                pool["choice_set_sha256"]!=choice.get("choice_set_sha256") or
                eligible["asset_class"]!=requirements[choice["requirement_id"]]["asset_class"]):
                _block("G4_ASSET_SELECTION_FORBIDDEN",layer_id,"Source is not in current approved G3 same-slot set.")
            if layer["mask"]["kind"]=="polygon_asset":
                new_mask=resolver.reviewed_mask(project_id,choice["requirement_id"],choice["slot_id"],
                                                choice["candidate_id"])
                if not new_mask or new_mask["parent_original_sha256"]!=choice["original_sha256"]:
                    _block("G4_MASK_SOURCE_STALE",layer_id,"New original requires its own reviewed G3 cutout.")
                layer["mask"]["asset_id"]=new_mask["derivative_asset_id"]
            layer["asset_id"]=choice["candidate_id"]
            for i,event in enumerate(scene["events"]):
                if event["layer_id"]==layer_id and event["preset_id"]=="photo-card-enter":
                    params={**event["params"],"source_original_sha256":choice["original_sha256"]}
                    # Recompile against verified G3 original; preserve registered keys/phases.
                    scene["events"][i]=compile_event(
                        "photo-card-enter",layer,scene["layers"],
                        event_id=event["event_id"],start_frame=event["start_frame"],
                        duration_frames=event["duration_frames"],cue_word_id=event["cue_word_id"],
                        params=params,evidence={"source_sha":choice["original_sha256"],
                                                "claim_ids":plan["claim_refs"]})
        scene["asset_ids"]=list(dict.fromkeys(
            aid for layer in scene["layers"] for aid in (layer["asset_id"],layer["mask"]["asset_id"]) if aid))
        previous_layers = {item["layer_id"]: item for item in previous["scenes"][index[sid]]["layers"]}
        chosen_layers = persisted_layers.get(sid, {})
        if set(chosen_layers) - {x["layer_id"] for x in scene["layers"]}:
            _block("G4_LAYOUT_INVALID", sid, "Layout edit references an unregistered compiled layer.")
        for layer in scene["layers"]:
            patch = chosen_layers.get(layer["layer_id"])
            if patch is not None:
                if not isinstance(patch, dict) or not patch or set(patch)-{"x", "y", "w", "h"}:
                    _block("G4_LAYOUT_INVALID", layer["layer_id"], "Pixel edit must contain only position or dimensions.")
                original = previous_layers.get(layer["layer_id"])
                if (not original or original["source_asset_slot_id"] != layer["source_asset_slot_id"] or
                    original["source_claim_id"] != layer["source_claim_id"]):
                    _block("G4_LAYOUT_INVALID", layer["layer_id"], "Only the same frozen factual layer can be repositioned.")
                rectangle = {**layer["rect_px"], **patch}
                if any(type(v) is not int for v in rectangle.values()) or rectangle["x"] < 0 or rectangle["y"] < 0 or rectangle["w"] < 1 or rectangle["h"] < 1 or rectangle["x"]+rectangle["w"] > 1920 or rectangle["y"]+rectangle["h"] > 1080:
                    _block("G4_LAYOUT_INVALID", layer["layer_id"], "Keep amended geometry inside the 1920x1080 canvas.")
                if layer["text"] is not None and (rectangle["w"] != layer["rect_px"]["w"] or rectangle["h"] != layer["rect_px"]["h"]):
                    _block("TYPOGRAPHY_OVERFLOW", layer["layer_id"], "Pinned GDI glyph layout cannot be resized without remeasurement.")
                layer["rect_px"] = rectangle
            crop = persisted_crops.get(sid, {}).get(layer["layer_id"])
            if crop is not None:
                if (set(crop) != {"x","y","w","h"} or
                    any(type(x) not in (int,float) for x in crop.values()) or
                    not (0 <= crop["x"] < 1 and 0 <= crop["y"] < 1 and 0 < crop["w"] <= 1-crop["x"]
                         and 0 < crop["h"] <= 1-crop["y"])):
                    _block("G4_CROP_INVALID", layer["layer_id"], "Keep reviewed original and valid normalized crop.")
                layer["crop_normalized"] = dict(crop)
        unknown = set(persisted_crops.get(sid, {})) - {x["layer_id"] for x in scene["layers"]}
        if unknown:
            _block("G4_CROP_INVALID", sid, "Crop only layers that exist in the selected setup.")
        prior_events = {event["event_id"]: event for event in previous["scenes"][index[sid]]["events"]}
        current_events = {event["event_id"]: event for event in scene["events"]}
        unknown_events = set(persisted_motion.get(sid, {})) - set(current_events)
        if unknown_events:
            _block("G4_MOTION_INVALID", sid, "Motion edit references an event absent from the selected setup.")
        for event_id, patch in persisted_motion.get(sid, {}).items():
            event = current_events[event_id]
            prior = prior_events.get(event_id)
            if not prior or event["preset_id"] != prior["preset_id"] or event["layer_id"] != prior["layer_id"]:
                _block("G4_MOTION_INVALID", event_id, "G4 cannot rebind an authored event to another source layer.")
            if not isinstance(patch, dict) or not patch:
                _block("G4_MOTION_INVALID", event_id, "Choose one authorized scalar motion parameter.")
            original_params = prior["params"]
            # Parameters which name source entities can never be changed by a
            # presentation edit. Arrays/objects are deliberately excluded by
            # the published scalar StoryboardEdit transport.
            forbidden = {key for key in original_params if key.endswith("_id") or key.endswith("_ids") or "sha" in key or "claim" in key or "word" in key or "geometry" in key or "map" in key or "era" in key}
            if set(patch) - set(original_params) or set(patch) & forbidden:
                _block("G4_MOTION_FORBIDDEN", event_id, "G4 motion edits cannot alter source identity, cue, map or geometry.")
            for key, value in patch.items():
                if type(value) not in (int, float, str, bool) or isinstance(original_params[key], (dict, list)):
                    _block("G4_MOTION_INVALID", event_id, "Only registered scalar presentation parameters are editable.")
            candidate = {**original_params, **patch}
            # A typed patch is only acceptable when the rebuilt event truly
            # contains the full registered canonical parameter grammar.
            if event["params"] != candidate:
                _block("G4_MOTION_INERT", event_id,
                       "The compiler did not apply the complete registered motion edit.")
            from backend.app.director.motion import presets
            from jsonschema import Draft202012Validator
            errors = list(Draft202012Validator(presets()[event["preset_id"]]["parameter_schema"]).iter_errors(candidate))
            if errors:
                _block("G4_MOTION_INVALID", event_id, "Registered motion bounds rejected this presentation edit.")
            # Event params, phase keys and camera track were rebuilt by _scene.
        requested_camera = [event_id for event_id in motion_overrides.get(sid, {})
                            if event_id in current_events and
                            current_events[event_id]["preset_id"] in ("camera-pan", "camera-push")]
        if requested_camera and (scene["camera"]["keyframes"] ==
                                 previous["scenes"][index[sid]]["camera"]["keyframes"]):
            _block("G4_MOTION_INERT", requested_camera[0],
                   "Camera scalar edit did not change real compiled keyframes; do not persist inert JSON.")
        out["scenes"][index[sid]] = scene
    if all(canonical(out["scenes"][index[sid]]) == canonical(previous["scenes"][index[sid]])
           for sid in changed):
        _block("G4_EDIT_INVALID", project_id,
               "Presentation edit produced no observable scene change; do not bump revision.")
    out["dependency_fingerprint"] = digest({"prior_identity": previous["dependency_fingerprint"],
                                             "new_direction": edited_blueprint,
                                             "crop_overrides": persisted_crops,
                                             "layer_overrides": persisted_layers,
                                             "motion_overrides": persisted_motion,
                                             "asset_selection_overrides": persisted_selections})
    validate_document("CompiledTimeline.v1", out)
    draft.publish(store, project_id, out, edited_blueprint, current_maps,
                  manifest["map_requests"], manifest["font_identity"],
                  expected_revision=expected_revision, previous=trusted,
                  edit_kind="scene_layout" if edited_blueprint != original_blueprint or layer_overrides or motion_overrides or asset_selection_overrides else "scene_crop",
                  layer_overrides=persisted_layers, crop_overrides=persisted_crops,
                  motion_overrides=persisted_motion,
                  asset_selection_overrides=persisted_selections,
                  reviewed_masks=trusted_masks)
    return {"timeline": out, "recomputed_setup_ids": sorted(changed),
            "retained_setup_ids": sorted(set(index) - changed),
            "project_revision": expected_revision+1, "stale_gates": ["G4","G5"]}
