"""B1-05: 19 registered, typed, frame-local deterministic motion recipes."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app.contracts import ContractViolation

REGISTRY = Path(__file__).resolve().parents[3] / "contracts/registries/motion-presets.v1.json"
# Primitive -> rendered track. These are deliberately not all a generic fade.
TRACK = {
    "layer_scale": ("scale", "from_scale", "to_scale"),
    "layer_stagger": ("opacity", None, None),
    "svg_path_length": ("path_progress", "start_progress", "end_progress"),
    "mask_progress": ("mask_progress", None, None),
    "verified_text_reveal": ("mask_progress", None, None),
    "number_interpolate": ("highlight_progress", None, None),
    "word_transform": ("translate_y_px", None, "max_offset_px"),
    "layer_depth_separation": ("translate_x_px", None, "max_drift_px"),
    "two_scene_mask_wipe": ("mask_progress", None, None),
    "camera_focus_tracking": ("translate_x_px", None, "max_translate_px"),
    "camera_focus_push": ("scale", "from_scale", "to_scale"),
    "static_hold": ("opacity", None, None),
    "short_transition_pan": ("translate_x_px", None, "sweep_px"),
    "dual_opacity_mix": ("opacity", None, None),
    "frame_cut": ("opacity", None, None),
    "word_mask_highlight": ("highlight_progress", None, None),
    "verified_geometry_mask": ("mask_progress", None, None),
    "paper_card_transform": ("rotation_deg", "start_rotation_deg", "end_rotation_deg"),
    "editorial_bezier_or_line_draw": ("path_progress", "progress_start", "progress_end"),
}


def _fail(code, entity, message):
    raise ContractViolation(code, entity, message)


@lru_cache(maxsize=1)
def presets() -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    idx = {p["preset_id"]: p for p in data["presets"]}
    if len(idx) != 19 or data["registry_version"] != "1.2.0":
        _fail("MOTION_REGISTRY_INCOMPLETE", "motion", "Load all 19 canonical typed preset grammars v1.2.0.")
    if set(p["render_recipe"]["primitive"] for p in idx.values()) != set(TRACK):
        _fail("MOTION_PRIMITIVE_UNKNOWN", "motion", "Every registered grammar needs its own bounded track.")
    return idx


def compile_event(preset_id: str, layer: dict, layers: list[dict], *,
                  event_id: str, start_frame: int, duration_frames: int,
                  cue_word_id: str | None, params: dict | None = None,
                  evidence: dict | None = None) -> dict:
    spec = presets().get(preset_id)
    if spec is None:
        _fail("MOTION_PRESET_UNKNOWN", preset_id, "Select a pinned motion grammar.")
    if layer["layer_kind"] not in spec["compatible_layer_kinds"]:
        _fail("MOTION_KIND_INVALID", layer["layer_id"], "Preset is incompatible with the target layer kind.")
    if (type(start_frame) != int or start_frame < 0 or type(duration_frames) != int or
            not spec["min_duration_frames"] <= duration_frames <= spec["max_duration_frames"]):
        _fail("MOTION_TIME_INVALID", event_id, "Respect the registered preset duration and scene-local start.")
    by_id = {x["layer_id"]: x for x in layers}
    if layer["layer_id"] not in by_id:
        _fail("MOTION_LAYER_UNKNOWN", event_id, "The animated layer must exist in this scene.")
    evidence = evidence or {}
    p = copy.deepcopy(spec["default_params"])
    if params is not None:
        p.update(params)
    # Placeholder identifiers in registry defaults are never valid compile-time layer references.
    for field in ("focus_layer_id", "text_layer_id", "start_target_layer_id", "end_target_layer_id",
                  "in_layer_id", "out_layer_id"):
        if field in p and field not in (params or {}):
            p[field] = layer["layer_id"]
    if "ordered_layer_ids" in p and "ordered_layer_ids" not in (params or {}):
        p["ordered_layer_ids"] = list(by_id)[:2]
    if "near_layer_ids" in p and "near_layer_ids" not in (params or {}):
        p["near_layer_ids"] = [layer["layer_id"]]
        p["far_layer_ids"] = [x for x in by_id if x != layer["layer_id"]][:1]
    if "source_word_ids" in p and "source_word_ids" not in (params or {}):
        p["source_word_ids"] = [cue_word_id] if cue_word_id else []
    if "word_ids" in p and "word_ids" not in (params or {}):
        p["word_ids"] = [cue_word_id] if cue_word_id else []
    if "quoted_source_claim_id" in p and "quoted_source_claim_id" not in (params or {}):
        p["quoted_source_claim_id"] = layer.get("source_claim_id")
    if "source_claim_id" in p and "source_claim_id" not in (params or {}):
        p["source_claim_id"] = layer.get("source_claim_id")
    if "text_layer_id" in p and p["text_layer_id"] not in by_id:
        _fail("MOTION_TEXT_INVALID", event_id, "Typewriter must bind an actual text layer.")
    if "route_geometry_ref" in p and "route_geometry_ref" not in (params or {}):
        p["route_geometry_ref"] = layer.get("path_geometry_ref")
    if "historical_map_id" in p and "historical_map_id" not in (params or {}):
        p["historical_map_id"] = evidence.get("historical_map_id")
    if "era_year" in p and "era_year" not in (params or {}):
        p["era_year"] = evidence.get("era_year")
    if "approved_feature_ids" in p and "approved_feature_ids" not in (params or {}):
        p["approved_feature_ids"] = evidence.get("approved_feature_ids", [])
    if "connector_geometry_ref" in p and "connector_geometry_ref" not in (params or {}):
        p["connector_geometry_ref"] = layer.get("path_geometry_ref")
    if "source_original_sha256" in p and "source_original_sha256" not in (params or {}):
        p["source_original_sha256"] = evidence.get("source_sha", "")
    errors = list(Draft202012Validator(spec["parameter_schema"]).iter_errors(p))
    if errors:
        _fail("MOTION_PARAMS_INVALID", event_id, "Fix preset parameters: " + errors[0].message)
    ids = [layer["layer_id"]]
    stagger = depth = None
    if preset_id == "stagger-reveal":
        ids = p["ordered_layer_ids"]
        if len(ids) < 2 or len(set(ids)) != len(ids):
            _fail("MOTION_STAGGER_INVALID", event_id, "Stagger needs two or more distinct layers.")
        stagger = {"order": ids, "offset_frames": p["gap_frames"]}
    if preset_id == "parallax-layers":
        near, far = p["near_layer_ids"], p["far_layer_ids"]
        if not near or not far or set(near) & set(far):
            _fail("MOTION_PARALLAX_INVALID", event_id, "Near and far layers must be independent.")
        ids = near + far
        depth = {"near_layer_ids": near, "far_layer_ids": far, "strength": p["near_strength"]}
    for key in ("start_target_layer_id", "end_target_layer_id", "focus_layer_id",
                "out_layer_id", "in_layer_id", "text_layer_id", "follow_marker_layer_id"):
        if p.get(key) and p[key] not in by_id:
            _fail("MOTION_LAYER_UNKNOWN", event_id, "Every motion-referenced layer must exist in scene.")
    if any(item not in by_id for item in ids):
        _fail("MOTION_LAYER_UNKNOWN", event_id, "Preset layer ordering contains an unknown scene layer.")
    if preset_id in ("typewriter", "number-count") and p.get("source_claim_id", p.get("quoted_source_claim_id")) not in evidence.get("claim_ids", []):
        _fail("MOTION_CLAIM_UNVERIFIED", event_id, "Animated quotation or value must retain a G1 claim reference.")
    if preset_id in ("text-highlight", "kinetic-type") and (not cue_word_id or
            cue_word_id not in p.get("source_word_ids", p.get("word_ids", []))):
        _fail("MOTION_WORD_UNVERIFIED", event_id, "Text emphasis must reference the original spoken word.")
    if preset_id == "photo-card-enter" and p["source_original_sha256"] != evidence.get("source_sha"):
        _fail("MOTION_SOURCE_STALE", event_id, "Card animation must use the exact G3 original SHA.")
    if preset_id == "number-count" and (not p["intermediate_truthful"] or
            p["end_value"] != evidence.get("number_value")):
        _fail("MOTION_NUMBER_INVALID", event_id, "Animated number must end at the evidenced G1 claim value.")
    if preset_id in ("route-line-draw", "map-region-wipe"):
        if not evidence.get("reviewed_period_map"):
            _fail("MOTION_GEOGRAPHY_UNREVIEWED", event_id, "Require actual approved period geography.")
        if preset_id == "route-line-draw" and (p["route_geometry_ref"] != evidence.get("route_feature_id")
                or evidence.get("geometry_type") != "LineString"):
            _fail("MOTION_ROUTE_INVALID", event_id, "Use a reviewed ordered geographic LineString.")
        if preset_id == "map-region-wipe" and (p["historical_map_id"] != evidence.get("historical_map_id")
                or p["era_year"] != evidence.get("era_year")
                or not set(p["approved_feature_ids"]) <= set(evidence.get("approved_feature_ids", []))):
            _fail("MOTION_MAP_INVALID", event_id, "Map wipe must match approved era, map and region IDs.")
    if preset_id == "editorial-connector-draw" and (not evidence.get("editorial_connector")
            or evidence.get("geometry_type") == "LineString"):
        _fail("MOTION_EDITORIAL_INVALID", event_id, "Editorial canvas connectors cannot masquerade as geographic routes.")
    primitive = spec["render_recipe"]["primitive"]
    prop, key_a, key_b = TRACK[primitive]
    start = p[key_a] if key_a else (1 if preset_id in ("freeze-hold", "hard-cut") else 0)
    end = p[key_b] if key_b else (0 if preset_id in ("hard-cut", "cross-dissolve") else 1)
    if preset_id == "number-count":
        start = 0
        end = 1   # normalized progression; source-truthful value lives in validated params
    if preset_id == "layer_stagger":  # explicit 0..1 progression, offsets in 'stagger'
        start, end = 0, 1
    phase_rows = []
    previous = 0
    for i, phase in enumerate(spec["phase_recipe"]):
        cut = duration_frames if i == len(spec["phase_recipe"])-1 else int(round(phase["end_fraction"] * duration_frames))
        cut = max(previous, min(duration_frames, cut))
        phase_rows.append({"phase_id": "phase_" + event_id + "_" + str(i),
                           "kind": phase["phase"], "start_offset_frames": previous,
                           "duration_frames": cut-previous,
                           "depends_on_phase_ids": [phase_rows[-1]["phase_id"]] if phase_rows else []})
        previous = cut
    easing = "ease_in_out" if "ease_in_out" in spec["allowed_easing"] else spec["allowed_easing"][0]
    return {
        "event_id": event_id, "layer_id": layer["layer_id"], "preset_id": preset_id,
        "start_frame": start_frame, "duration_frames": duration_frames,
        "cue_word_id": cue_word_id, "params": p,
        "animated_property": prop,
        "keyframes": [{"frame": 0, "value": start, "easing": "linear"},
                      {"frame": duration_frames, "value": end, "easing": easing}],
        "cue_binding": {"word_id": cue_word_id, "offset_frames": 0},
        "phases": phase_rows,
        "motion_space": spec["render_recipe"]["transform_space"],
        "affected_layer_ids": ids, "stagger": stagger, "depth_parallax": depth,
    }
