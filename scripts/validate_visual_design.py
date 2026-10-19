"""Executable *design* checks for historical video visual contracts v1.1.

This module validates structure, referential consistency and template/motion
grammar. It does NOT approve factual historical claims, archival licenses,
final-WAV timing or a real Remotion render.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError
from check_design_contracts import ROOT, ContractError, validate_schema, validate_story


def _fail(code: str, place: str, hint: str) -> None:
    raise ContractError(code, place, hint)


def _unique(values: list[str], code: str, place: str) -> None:
    if len(values) != len(set(values)):
        _fail(code, place, "All identifiers must be unique within their declared scope.")


def load_visual_fixtures() -> tuple[dict, dict, dict]:
    p = ROOT / "contracts" / "examples" / "visual_cases"
    names = [
        "StoryPackage.visual_cases.synthetic.json",
        "VisualBlueprint.visual_cases.synthetic.json",
        "CompiledTimeline.visual_cases.synthetic.json",
    ]
    return tuple(json.loads((p / n).read_text(encoding="utf-8")) for n in names)


def load_registries() -> tuple[dict, dict]:
    root = ROOT / "contracts" / "registries"
    return (
        json.loads((root / "layouts.v1.json").read_text(encoding="utf-8")),
        json.loads((root / "motion-presets.v1.json").read_text(encoding="utf-8")),
    )


def validate_directed_story(story: dict) -> None:
    validate_story(story)
    section_ids = {s["section_id"] for s in story["sections"]}
    claim_ids = {c["claim_id"] for c in story["claims"]}
    setup_ids = {s["setup_id"] for s in story["visual_setups"]}
    global_beats = []
    for setup in story["visual_setups"]:
        direction = setup["direction"]
        refs = {a["slot_id"] for a in direction["asset_slots"]} | {
            t["text_id"] for t in direction["on_screen_text"]
        }
        _unique([a["slot_id"] for a in direction["asset_slots"]], "DUPLICATE_ASSET_SLOT", setup["setup_id"])
        _unique([t["text_id"] for t in direction["on_screen_text"]], "DUPLICATE_TEXT_ID", setup["setup_id"])
        reuse = direction["reuse_setup_id"]
        if reuse is not None and (reuse not in setup_ids or reuse == setup["setup_id"]):
            _fail("CONTINUITY_SETUP_INVALID", setup["setup_id"], "Reuse only an existing other setup.")
        for beat in direction["visual_beats"]:
            global_beats.append(beat["beat_id"])
            if beat["section_ref"] not in setup["section_refs"] or beat["cue"]["section_id"] not in section_ids:
                _fail("VISUAL_BEAT_SECTION_INVALID", beat["beat_id"], "Beat must cite included narration section.")
            if beat["focus_ref"] not in refs:
                _fail("VISUAL_BEAT_FOCUS_UNKNOWN", beat["beat_id"], "Focus must be a declared text or asset slot.")
            if not set(beat["source_claim_refs"]) <= claim_ids:
                _fail("VISUAL_BEAT_CLAIM_UNKNOWN", beat["beat_id"], "Use a claim from G1 story.")
            for rel in beat["relationships"]:
                if rel["from_ref"] not in refs or rel["to_ref"] not in refs:
                    _fail("VISUAL_RELATION_UNKNOWN", beat["beat_id"], "Both relationship anchors must be present.")
                if rel["from_ref"] == rel["to_ref"]:
                    _fail("VISUAL_RELATION_SELF", beat["beat_id"], "Self-relation is not meaningful.")
            seen_staging = set()
            for step in beat["staging"]:
                if step["ref"] not in refs or (step["after_ref"] is not None and step["after_ref"] not in refs):
                    _fail("VISUAL_STAGING_REF_UNKNOWN", beat["beat_id"], "All staged objects must be declared.")
                if step["after_ref"] == step["ref"] or step["ref"] in seen_staging:
                    _fail("VISUAL_STAGING_ORDER_INVALID", beat["beat_id"], "No duplicate/self-dependent staging step.")
                seen_staging.add(step["ref"])
            if not set(beat["continuity"]["carry_refs"]) <= refs:
                _fail("CONTINUITY_REF_UNKNOWN", beat["beat_id"], "Carry-over objects must exist in this setup.")
    _unique(global_beats, "VISUAL_BEAT_DUPLICATE", "StoryPackage")


def _assert_ids(values: list[str], valid: set[str], code: str, loc: str) -> None:
    if not set(values) <= valid:
        _fail(code, loc, f"Unknown IDs: {sorted(set(values) - valid)}")


def _verify_payload(plan: dict, story: dict, story_claims: dict[str, dict]) -> None:
    p = plan["template_payload"]
    tid, loc = plan["template_id"], plan["setup_id"]
    if p["template_id"] != tid:
        _fail("TEMPLATE_PAYLOAD_MISMATCH", loc, "Tagged template payload must match selected template.")
    reqs = set(plan["requirement_refs"])
    claim_ids = set(story_claims)
    d = plan["editorial_direction"]
    asset_slots = {x["slot_id"] for x in d["asset_slots"]}
    text_ids = {x["text_id"] for x in d["on_screen_text"]}
    beat_ids = {b["beat_id"] for b in d["visual_beats"]}
    def rq(*keys):
        _assert_ids(list(keys), reqs, "TEMPLATE_REQUIREMENT_MISSING", loc)
    def cl(*keys):
        _assert_ids(list(keys), claim_ids, "TEMPLATE_CLAIM_MISSING", loc)
    def tx(*keys):
        _assert_ids([x for x in keys if x is not None], text_ids, "TEMPLATE_TEXT_MISSING", loc)
    def sl(*keys):
        _assert_ids([x for x in keys if x is not None], asset_slots, "TEMPLATE_SLOT_MISSING", loc)
    def beat(*keys):
        _assert_ids(list(keys), beat_ids, "TEMPLATE_BEAT_MISSING", loc)
    def check_map(m):
        rq(m["map_requirement_id"])
        evidence = next(x for x in story["asset_requirements"] if x["requirement_id"] == m["map_requirement_id"])
        if not evidence["start_year"] <= m["year"] <= evidence["end_year"]:
            _fail("MAP_PERIOD_MISMATCH", loc, "Map year is outside its claimed evidence period.")
        for c in m["label_source_claim_refs"]:
            cl(c)
    if tid == "T01":
        check_map(p["map"])
        for v in p["location_labels"]:
            cl(v["source_claim_id"])
    elif tid == "T02":
        sl(p["portrait_slot_id"], p["secondary_evidence_slot_id"])
        tx(p["name_text_id"], p["role_text_id"])
        cl(p["identity_claim_id"])
    elif tid == "T03":
        cards = p["cards"]
        ids = [c["card_id"] for c in cards]
        _unique(ids, "COLLAGE_CARD_DUPLICATE", loc)
        if p["focus_card_id"] not in ids or len(p["card_reveal_order"]) != len(ids) or set(p["card_reveal_order"]) != set(ids):
            _fail("COLLAGE_ORDER_INVALID", loc, "Order must be a permutation including all approved card candidates.")
        if sum(c["card_role"] == "hero" for c in cards) != 1:
            _fail("COLLAGE_HERO_INVALID", loc, "Exactly one card must define visual hero.")
        for c in cards:
            sl(c["asset_slot_id"])
            tx(c["caption_text_id"])
            cl(c["evidence_claim_id"])
    elif tid == "T04":
        check_map(p["map"])
        cl(p["route_provenance_claim_id"])
        wps = p["waypoints"]
        _unique([w["waypoint_id"] for w in wps], "WAYPOINT_DUPLICATE", loc)
        _unique([w["coordinate_ref"] for w in wps], "WAYPOINT_COORD_DUPLICATE", loc)
        for w in wps:
            beat(w["cue_beat_id"])
            cl(w["source_claim_id"])
        sl(p["moving_marker_slot_id"])
        if not p["route_geometry_ref"]:
            _fail("ROUTE_GEOMETRY_MISSING", loc, "Routes must have G3-reviewable geometry.")
    elif tid == "T05":
        events = p["timeline_events"]
        ids = [e["event_id"] for e in events]
        _unique(ids, "CHRONOLOGY_EVENT_DUPLICATE", loc)
        if p["active_event_id"] not in ids:
            _fail("CHRONOLOGY_ACTIVE_UNKNOWN", loc, "Active event must exist.")
        order = [e["chronology_order"] for e in events]
        if order != sorted(set(order)):
            _fail("CHRONOLOGY_ORDER_INVALID", loc, "Events must have strictly increasing order.")
        for e in events:
            cl(e["source_claim_id"])
            tx(e["label_text_id"])
            beat(e["cue_beat_id"])
            sl(e["optional_asset_slot_id"])
    elif tid == "T06":
        sl(p["document_slot_id"])
        tx(p["excerpt_text_id"], p["attribution_text_id"])
        beat(p["annotation_beat_id"])
        cl(p["document_claim_id"])
        if p["excerpt_kind"] == "verbatim_verified" and story_claims[p["document_claim_id"]]["status"] != "VERIFIED":
            _fail("QUOTE_SOURCE_NOT_VERIFIED", loc, "Verbatim quote requires verified source before publication.")
        crop = p["focus_region_uv"]
        if crop["x"] + crop["w"] > 1 or crop["y"] + crop["h"] > 1:
            _fail("DOCUMENT_CROP_OUTSIDE", loc, "Excerpt crop must remain within original.")
    elif tid == "T07":
        check_map(p["before_map"])
        check_map(p["after_map"])
        if (p["before_map"]["map_requirement_id"] == p["after_map"]["map_requirement_id"]
                or p["before_map"]["year"] == p["after_map"]["year"]):
            _fail("MAP_PAIR_NOT_DISTINCT", loc, "Compare two different period snapshots.")
        cl(p["comparison_claim_id"])
        tx(p["date_before_text_id"], p["date_after_text_id"])
    elif tid == "T08":
        cl(p["fact_claim_id"])
        tx(p["fact_text_id"], p["unit_text_id"], p["source_text_id"])
    elif tid == "T09":
        tx(p["headline_text_id"], p["attribution_text_id"], *p["emphasis_text_ids"])
        sl(p["document_slot_id"])
        cl(p["attributed_claim_id"])
        if p["quote_kind"] == "verbatim_verified" and story_claims[p["attributed_claim_id"]]["status"] != "VERIFIED":
            _fail("QUOTE_SOURCE_NOT_VERIFIED", loc, "Do not present unverified words as verbatim quote.")
    elif tid == "T10":
        cl(p["origin_claim_id"])
        entities = {e["entity_id"]: e for e in p["entities"]}
        if len(entities) != len(p["entities"]):
            _fail("CAUSAL_ENTITY_DUPLICATE", loc, "Entities must be distinct.")
        for e in p["entities"]:
            tx(e["name_text_id"])
            cl(e["source_claim_id"])
        for link in p["causal_links"]:
            if (link["from_entity_id"] not in entities or link["to_entity_id"] not in entities
                    or link["from_entity_id"] == link["to_entity_id"]):
                _fail("CAUSAL_LINK_INVALID", loc, "Links require two known distinct entities.")
            cl(link["relationship_claim_id"])
            if link["certainty"] == "documented" and story_claims[link["relationship_claim_id"]]["status"] == "UNVERIFIED":
                _fail("CAUSAL_UNVERIFIED", loc, "Unverified linkage cannot be documented.")
        if p["map_requirement_id"] is not None:
            rq(p["map_requirement_id"])


def validate_blueprint(story: dict, blueprint: dict) -> None:
    validate_directed_story(story)
    validate_schema("VisualBlueprint.v1", blueprint)
    if blueprint["project_id"] != story["project"]["project_id"]:
        _fail("PROJECT_ID_MISMATCH", "VisualBlueprint", "Use same approved project.")
    setups = {s["setup_id"]: s for s in story["visual_setups"]}
    claims = {c["claim_id"]: c for c in story["claims"]}
    plans = blueprint["setup_plans"]
    _unique([x["setup_id"] for x in plans], "BLUEPRINT_SETUP_DUPLICATE", "VisualBlueprint")
    if set(x["setup_id"] for x in plans) != set(setups):
        _fail("BLUEPRINT_SETUP_MISSING", "VisualBlueprint", "Each authored setup must be normalized.")
    for plan in plans:
        source = setups[plan["setup_id"]]
        if (set(plan["section_refs"]) != set(source["section_refs"])
                or set(plan["claim_refs"]) != set(source["claim_refs"])
                or set(plan["requirement_refs"]) != set(source["requirement_refs"])):
            _fail("BLUEPRINT_SOURCE_DRIFT", plan["setup_id"], "Do not silently alter G1 story references.")
        current = plan["editorial_direction"]
        original = source["direction"]
        rev = plan.get("direction_revision")
        if rev is not None:
            if rev["source_story_revision_sha256"] != blueprint["story_revision_sha256"]:
                _fail("DIRECTION_SOURCE_STALE", plan["setup_id"], "Visual edit must cite current approved G1 story hash.")
            changed = {key for key in original if current.get(key) != original[key]}
            if rev["kind"] == "inherited":
                if changed or rev["edited_paths"] or rev["operator_confirmed"]:
                    _fail("BLUEPRINT_DIRECTION_DRIFT", plan["setup_id"], "Inherited direction cannot contain unrecorded edits.")
            else:
                allowed = {"visual_beats", "camera_intent", "composition_intent",
                           "layout_variant_hint", "transition_intent", "reuse_setup_id"}
                if (not rev["operator_confirmed"] or not rev["edit_reason"]
                        or not changed or changed != set(rev["edited_paths"]) or not changed <= allowed):
                    _fail("G4_EDIT_UNAUTHORIZED", plan["setup_id"], "Operator must confirm and itemize presentation-only changes.")
                before = {b["beat_id"]: b for b in original["visual_beats"]}
                after = {b["beat_id"]: b for b in current["visual_beats"]}
                if set(before) != set(after):
                    _fail("G1_SEMANTICS_PROTECTED", plan["setup_id"], "Visual draft cannot create/delete G1 factual beats.")
                for beat_id, b in before.items():
                    new = after[beat_id]
                    for protected in ("beat_id", "section_ref", "cue", "source_claim_refs"):
                        if b[protected] != new[protected]:
                            _fail("G1_SEMANTICS_PROTECTED", beat_id, "Narration/claim/cue changes require G1 revision.")
        elif current != original:
            _fail("BLUEPRINT_DIRECTION_DRIFT", plan["setup_id"], "Changed editorial direction needs signed G4 draft provenance.")
        _verify_payload(plan, story, claims)


def validate_visual_registry(layouts: dict, motions: dict) -> None:
    variants = layouts["layouts"]
    if len(variants) != 30 or len(motions["presets"]) != 18:
        _fail("REGISTRY_INCOMPLETE", "registries", "Exactly 10 templates × 3 and 18 motion grammars.")
    signatures = set()
    geometry_signatures = set()
    for l in variants:
        validate_schema("TemplateLayout.v1", l)
        key = l["template_id"] + l["variant_id"]
        if l["visual_variation_signature"] in signatures:
            _fail("LAYOUT_VARIANTS_CLONED", key, "Variants need distinct compositional signatures.")
        signatures.add(l["visual_variation_signature"])
        geom = tuple((slot["role"], slot["required"], tuple(slot["rect_normalized"][k] for k in ("x","y","w","h")))
                     for slot in l["slots"])
        if geom in geometry_signatures:
            _fail("LAYOUT_VARIANTS_CLONED", key, "Two variants share identical composition geometry despite different labels.")
        geometry_signatures.add(geom)
        ids = [s["slot_id"] for s in l["slots"]]
        _unique(ids, "LAYOUT_SLOT_DUPLICATE", key)
        cnt = Counter(s["role"] for s in l["slots"] if s["required"])
        for role in l["composition_rules"]["required_role_counts"]:
            if role["min_count"] != cnt[role["role"]]:
                _fail("LAYOUT_ROLE_RULE_MISMATCH", key, "Required role count must agree with layout slots.")
            if role["min_count"] > role["max_count"]:
                _fail("LAYOUT_ROLE_RULE_MISMATCH", key, "min_count > max_count")
        for rel in l["layer_relations"]:
            if rel["from_slot"] not in ids or rel["to_slot"] not in ids:
                _fail("LAYOUT_RELATION_UNKNOWN", key, "Relation must reference declared layout slots.")
    for preset in motions["presets"]:
        schema = preset["parameter_schema"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(preset["default_params"])
        phases = preset["phase_recipe"]
        if not phases or phases[0]["start_fraction"] != 0 or phases[-1]["end_fraction"] != 1:
            _fail("MOTION_RECIPE_GAP", preset["preset_id"], "Phase recipe must span entire event.")
        for a, b in zip(phases, phases[1:]):
            if a["end_fraction"] != b["start_fraction"]:
                _fail("MOTION_RECIPE_GAP", preset["preset_id"], "Phases must be contiguous.")
    sig = [x["visual_variation_signature"] for x in variants]
    if len(sig) != len(set(sig)):
        _fail("LAYOUT_VARIANTS_CLONED", "registries", "30 independent compositional signatures required.")


def validate_visual_timeline(blueprint: dict, timeline: dict, layouts: dict, motions: dict) -> None:
    validate_schema("CompiledTimeline.v1", timeline)
    layout_idx = {(x["template_id"], x["variant_id"]): x for x in layouts["layouts"]}
    motion_idx = {x["preset_id"]: x for x in motions["presets"]}
    plan_idx = {x["setup_id"]: x for x in blueprint["setup_plans"]}
    scenes = timeline["scenes"]
    _unique([x["scene_id"] for x in scenes], "SCENE_DUPLICATE", "CompiledTimeline")
    if not scenes or max(x["start_frame"] + x["duration_frames"] for x in scenes) > timeline["total_frames"]:
        _fail("SCENE_RANGE_INVALID", "CompiledTimeline", "Every scene must fit actual timeline.")
    for scene in scenes:
        loc = scene["scene_id"]
        plan = plan_idx.get(scene["setup_id"])
        if not plan or scene["template_id"] != plan["template_id"] or scene["variant_id"] != plan["variant_id"]:
            _fail("SCENE_PLAN_MISMATCH", loc, "Selected template and source setup must agree.")
        layout = layout_idx[(scene["template_id"], scene["variant_id"])]
        cnt = Counter(x["layer_kind"] for x in scene["layers"])
        for role in layout["composition_rules"]["required_role_counts"]:
            if not role["min_count"] <= cnt[role["role"]] <= role["max_count"]:
                _fail("LAYOUT_REQUIRED_ROLE_MISSING", loc, f"Role {role['role']} count outside valid range.")
        layers = {x["layer_id"]: x for x in scene["layers"]}
        _unique([x["layer_id"] for x in scene["layers"]], "LAYER_DUPLICATE", loc)
        slot_index = {x["slot_id"]: x for x in layout["slots"]}
        approved_slot_ids = {x["slot_id"] for x in plan["editorial_direction"]["asset_slots"]}
        group_ids = set(scene["staging"]["composition_graph"]["group_ids"])
        for l in scene["layers"]:
            template_slot = slot_index.get(l["template_slot_id"])
            if template_slot is None or template_slot["role"] != l["layer_kind"]:
                _fail("TEMPLATE_LAYER_SLOT_DRIFT", l["layer_id"], "Render layer must bind a declared same-role template slot.")
            if l["asset_id"] and l["source_asset_slot_id"] not in approved_slot_ids:
                _fail("RENDER_SOURCE_SLOT_MISSING", l["layer_id"], "Asset layer must cite authored source slot and G3 binding.")
            if l["group_id"] is not None and l["group_id"] not in group_ids:
                _fail("RENDER_GROUP_UNKNOWN", loc, "Layer group must exist.")
            if l["parent_layer_id"] is not None:
                if l["parent_layer_id"] not in layers or l["parent_layer_id"] == l["layer_id"]:
                    _fail("RENDER_PARENT_INVALID", l["layer_id"], "Parent must be another layer in scene.")
            if l["path_geometry_ref"] and l["layer_kind"] not in {"route", "map", "territory"}:
                _fail("GEOMETRY_ROLE_INVALID", l["layer_id"], "Path requires geographic or route layer.")
            if l["text"] and l["text_layout"] is None:
                _fail("TEXT_LAYOUT_MISSING", l["layer_id"], "Text requires measured typography.")
            if l["rect_px"]["w"] <= 0 or l["rect_px"]["h"] <= 0:
                _fail("LAYER_BOUNDS_INVALID", l["layer_id"], "Nonempty layer rectangle required.")
        for edge in scene["staging"]["composition_graph"]["edges"]:
            if edge["from_id"] not in layers or edge["to_id"] not in layers:
                _fail("COMPOSITION_EDGE_UNKNOWN", loc, "Graph nodes must exist.")
        allowed_beats = {b["beat_id"] for b in plan["editorial_direction"]["visual_beats"]}
        bs = scene["staging"]["beat_sequence"]
        if set(b["beat_id"] for b in bs) != allowed_beats:
            _fail("STAGING_BEAT_DRIFT", loc, "Must compile all authoring beats, no fabricated stage.")
        last = 0
        for beat in bs:
            if beat["local_start_frame"] != last or not last < beat["local_end_frame"] <= scene["duration_frames"]:
                _fail("STAGING_TIME_INVALID", beat["beat_id"], "Staging beats need contiguous positive local time.")
            last = beat["local_end_frame"]
            if beat["focus_layer_id"] not in layers or not set(beat["activated_layer_ids"] + beat["hidden_layer_ids"]) <= set(layers):
                _fail("STAGING_LAYER_UNKNOWN", beat["beat_id"], "Focus/activated layer must be in scene.")
        if last != scene["duration_frames"]:
            _fail("STAGING_TIME_INVALID", loc, "Stage must cover whole scene.")
        for f in scene["camera"]["focus_path"]:
            if f["focus_layer_id"] not in layers or f["at_frame"] >= scene["duration_frames"]:
                _fail("CAMERA_TARGET_UNKNOWN", loc, "Camera focus must reference known layer and valid frame.")
        for event in scene["events"]:
            p = motion_idx.get(event["preset_id"])
            if p is None or p["preset_id"] not in layout["allowed_presets"]:
                _fail("MOTION_PRESET_UNSUPPORTED", event["event_id"], "Preset not registered for this layout.")
            if event["layer_id"] not in layers or layers[event["layer_id"]]["layer_kind"] not in p["compatible_layer_kinds"]:
                _fail("MOTION_TARGET_INVALID", event["event_id"], "Preset not compatible with target layer.")
            try:
                Draft202012Validator(p["parameter_schema"]).validate(event["params"])
            except ValidationError as exc:
                _fail("MOTION_PARAMS_INVALID", event["event_id"], exc.message)
            if event["motion_space"] != p["render_recipe"]["transform_space"]:
                _fail("MOTION_SPACE_INVALID", event["event_id"], "Use prescribed coordinate space.")
            if not set(event["affected_layer_ids"]) <= set(layers):
                _fail("MOTION_LAYER_UNKNOWN", event["event_id"], "Affected layers not present.")
            phases = event["phases"]
            if [x["kind"] for x in phases] != [x["phase"] for x in p["phase_recipe"]]:
                _fail("MOTION_PHASE_MISMATCH", event["event_id"], "Compiled phases must follow preset recipe.")
            last_phase = 0
            for q in phases:
                if q["start_offset_frames"] != last_phase or q["duration_frames"] < 0:
                    _fail("MOTION_PHASE_INVALID", event["event_id"], "Phase timeline must be contiguous.")
                last_phase += q["duration_frames"]
            if last_phase != event["duration_frames"]:
                _fail("MOTION_PHASE_INVALID", event["event_id"], "Phases must end at event end.")
            if p["geometry_requirement"] == "approved_ordered_linestring":
                if layers[event["layer_id"]]["path_geometry_ref"] != event["params"]["route_geometry_ref"]:
                    _fail("MOTION_ROUTE_UNBOUND", event["event_id"], "Draw the G3-reviewed route geometry bound to target layer.")
            if event["preset_id"] == "parallax-layers":
                if event["depth_parallax"] is None:
                    _fail("PARALLAX_DEPTH_MISSING", event["event_id"], "Depth-separated layers required.")
                near = set(event["params"]["near_layer_ids"])
                far = set(event["params"]["far_layer_ids"])
                if near & far or not near | far <= set(layers):
                    _fail("PARALLAX_LAYER_INVALID", event["event_id"], "Parallax planes must be distinct scene layers.")


def validate_visual_case_package(story: dict, blueprint: dict, timeline: dict) -> None:
    validate_blueprint(story, blueprint)
    a, b = load_registries()
    validate_visual_registry(a, b)
    validate_visual_timeline(blueprint, timeline, a, b)


if __name__ == "__main__":
    story, blue, render = load_visual_fixtures()
    validate_visual_case_package(story, blue, render)
    print(f"Visual-contract fixtures PASS: {len(blue['setup_plans'])} typed templates, "
          f"{len(render['scenes'])} multi-layer scenes, 30 variants, 18 motion grammars.")
