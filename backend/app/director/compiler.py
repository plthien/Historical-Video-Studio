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
        target = next(x for x in layers if x["layer_id"] == focus)
        allowed = layout["allowed_presets"]
        if target["layer_kind"] in ("headline", "text") and "title-mask-reveal" in allowed:
            kind = "title-mask-reveal"
        elif target["layer_kind"] in ("archival_photo", "portrait", "document") and "photo-card-enter" in allowed:
            kind = "photo-card-enter"
        elif target["layer_kind"] == "route" and "route-line-draw" in allowed:
            kind = "route-line-draw"
        else:
            kind = "freeze-hold" if "freeze-hold" in allowed else next(
                (preset for preset in allowed if target["layer_kind"] in presets()[preset]["compatible_layer_kinds"]), None)
        if not kind:
            _block("MOTION_PRESET_UNKNOWN", sid, "No compatible registered grammar for the authored focus.")
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
    approved = {}
    with store._connection() as db:
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
    return compile_timeline(story_obj.data(), blueprint, word_map, final_audio, approved,
                            maps=maps, font_measure=font_measure, font_identity=font_identity,
                            expected_story_sha256=story_obj.sha256)
