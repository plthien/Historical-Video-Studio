"""Step 01/02 executable contract checks. Not the production backend."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schema"
EXAMPLES = ROOT / "contracts" / "examples"


class ContractError(ValueError):
    def __init__(self, code: str, path: str, remediation: str) -> None:
        self.code, self.path, self.remediation = code, path, remediation
        super().__init__(f"{code} at {path}: {remediation}")


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.valid.json").read_text(encoding="utf-8"))


def validate_schema(name: str, data: dict[str, Any]) -> None:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)


def _unique(values: list[str], code: str, path: str) -> None:
    if len(values) != len(set(values)):
        raise ContractError(code, path, "Duplicate IDs must be replaced.")


def _validate_editorial_direction(setup: dict[str, Any], section_ids: set[str], reqs: set[str], claims: set[str]) -> None:
    d = setup["direction"]
    for role in d["asset_slots"]:
        if role["requirement_id"] not in reqs:
            raise ContractError("CROSS_REFERENCE_MISSING", setup["setup_id"], "Editorial asset slot references unknown requirement.")
    for item in d["on_screen_text"]:
        if item["claim_ref"] is not None and item["claim_ref"] not in claims:
            raise ContractError("CROSS_REFERENCE_MISSING", setup["setup_id"], "On-screen claim reference missing.")
    for beat in d["reveal_plan"]:
        if beat["cue"]["section_id"] not in section_ids:
            raise ContractError("CROSS_REFERENCE_MISSING", beat["beat_id"], "Reveal cue references unknown section.")
    if d["historical_map_requirement_id"] is not None and d["historical_map_requirement_id"] not in reqs:
        raise ContractError("CROSS_REFERENCE_MISSING", setup["setup_id"], "Historical map requirement missing.")


def validate_story(data: dict[str, Any]) -> None:
    validate_schema("StoryPackage.v1", data)
    sections = {s["section_id"] for s in data["sections"]}
    claims = {c["claim_id"] for c in data["claims"]}
    reqs = {r["requirement_id"] for r in data["asset_requirements"]}
    setups = {v["setup_id"] for v in data["visual_setups"]}
    for label, entries in [
        ("section", [x["section_id"] for x in data["sections"]]),
        ("claim", [x["claim_id"] for x in data["claims"]]),
        ("requirement", [x["requirement_id"] for x in data["asset_requirements"]]),
        ("setup", [x["setup_id"] for x in data["visual_setups"]]),
    ]:
        _unique(entries, "DUPLICATE_ID", label)
    for s in data["sections"]:
        if not set(s["claim_refs"]) <= claims or not set(s["asset_requirement_refs"]) <= reqs:
            raise ContractError("CROSS_REFERENCE_MISSING", s["section_id"], "Correct dangling claim/asset requirement refs.")
    for v in data["visual_setups"]:
        if not set(v["section_refs"]) <= sections or not set(v["claim_refs"]) <= claims or not set(v["requirement_refs"]) <= reqs:
            raise ContractError("CROSS_REFERENCE_MISSING", v["setup_id"], "Use existing approved IDs.")
        _validate_editorial_direction(v, sections, reqs, claims)
    for r in data["asset_requirements"]:
        if r["start_year"] > r["end_year"]:
            raise ContractError("PERIOD_INVALID", r["requirement_id"], "End year must not precede start year.")


def can_approve_story(data: dict[str, Any]) -> None:
    validate_story(data)
    for c in data["claims"]:
        if c["critical"] and c["status"] == "UNVERIFIED":
            raise ContractError("CLAIM_CRITICAL_UNRESOLVED", c["claim_id"], "Review, remove, or revise critical claim before G1.")


def validate_word_map(data: dict[str, Any], final_audio: dict[str, Any]) -> None:
    validate_schema("WordTimingMap.v1", data)
    validate_schema("FinalAudio.v1", final_audio)
    if (data["audio_sha256"] != final_audio["audio_sha256"] or
            data["transcript_sha256"] != final_audio["transcript_sha256"] or
            data["sample_rate"] != final_audio["sample_rate"]):
        raise ContractError("WORD_MAP_STALE", "audio_sha256", "Re-run ElevenLabs alignment on approved final WAV.")
    last_end = -1
    for word in data["words"]:
        begin, end = word["start_sample"], word["end_sample"]
        if begin < last_end or not (0 <= begin < end <= final_audio["duration_samples"]):
            raise ContractError("WORD_RANGE_INVALID", word["word_id"], "Correct alignment / re-align exact audio.")
        last_end = end


def validate_asset_resolution(data: dict[str, Any]) -> None:
    validate_schema("AssetResolution.v1", data)
    mode, status = data["resolution_mode"], data["status"]
    if mode == "MANAGED_FALLBACK" and not data["operator_authorized"]:
        raise ContractError("FALLBACK_NOT_AUTHORIZED", data["requirement_id"], "Request operator consent first.")
    if status == "MANAGED_FALLBACK_AUTHORIZED" and mode != "MANAGED_FALLBACK":
        raise ContractError("FALLBACK_NOT_AUTHORIZED", data["requirement_id"], "Set selected managed mode and consent.")
    if status == "APPROVED":
        if not data["approved_asset_id"] or not data["approved_candidate_sha256"] or not data["approval_record_id"]:
            raise ContractError("FALLBACK_NOT_APPROVED", data["requirement_id"], "Review exact candidate and create G3 approval.")
        if data["approved_asset_id"] not in data["candidate_asset_ids"]:
            raise ContractError("ASSET_BINDING_STALE", data["requirement_id"], "Approved candidate must belong to requirement.")


def validate_timeline(data: dict[str, Any], word_map: dict[str, Any], approved_asset_ids: set[str]) -> None:
    validate_schema("CompiledTimeline.v1", data)
    word_ids = {w["word_id"] for w in word_map["words"]}
    seen_scene_ids = set()
    for scene in data["scenes"]:
        sid = scene["scene_id"]
        if scene["transition_out"]["duration_frames"] > scene["duration_frames"]:
            raise ContractError("SCENE_RANGE_INVALID", sid, "Transition must fit scene duration.")
        previous_camera=-1
        for key in scene["camera"]["keyframes"]:
            if key["at_frame"] <= previous_camera or key["at_frame"] >= scene["duration_frames"]:
                raise ContractError("CAMERA_RANGE_INVALID", sid, "Camera keyframes must be strictly ordered inside scene.")
            previous_camera=key["at_frame"]
        if sid in seen_scene_ids:
            raise ContractError("DUPLICATE_ID", sid, "Use a unique scene ID.")
        seen_scene_ids.add(sid)
        if scene["start_frame"] + scene["duration_frames"] > data["total_frames"]:
            raise ContractError("SCENE_RANGE_INVALID", sid, "Scene must fit video timeline.")
        if not set(scene["asset_ids"]) <= approved_asset_ids:
            raise ContractError("ASSET_BINDING_STALE", sid, "Only approved asset versions may render.")
        layers = {lay["layer_id"] for lay in scene["layers"]}
        for lay in scene["layers"]:
            box = lay["rect_px"]
            if box["w"] <= 0 or box["h"] <= 0:
                raise ContractError("LAYOUT_INVALID", lay["layer_id"], "Layer rect must be nonempty.")
            if lay["map_binding"] is not None and lay["layer_kind"] not in {"map","route","territory","callout"}:
                raise ContractError("MAP_BINDING_INVALID", lay["layer_id"], "Only map-related layers may bind geographic coordinates.")
        for lay in scene["layers"]:
            if lay.get("asset_id") and lay["asset_id"] not in scene["asset_ids"]:
                raise ContractError("ASSET_BINDING_STALE", lay["layer_id"], "Layer source not in scene asset bindings.")
        for e in scene["events"]:
            if e["preset_id"] == "route-line-draw" and not any(lay["layer_id"] == e["layer_id"] and lay["layer_kind"] == "route" for lay in scene["layers"]):
                raise ContractError("INVALID_PRESET", e["event_id"], "Route line draw requires a route layer.")
            if ("scale" in e.get("params", {}) and
                    (not isinstance(e["params"]["scale"], (float, int)) or not 0.75 <= e["params"]["scale"] <= 1.3)):
                raise ContractError("INVALID_PRESET", e["event_id"], "Scale parameter exceeds conservative document bounds.")
            previous_keyframe=-1
            for key in e["keyframes"]:
                if key["frame"] < previous_keyframe or key["frame"] > e["duration_frames"]:
                    raise ContractError("MOTION_RANGE_INVALID", e["event_id"], "Motion keyframes must be ordered and fit event duration.")
                previous_keyframe=key["frame"]
            if e["layer_id"] not in layers:
                raise ContractError("LAYER_REF_MISSING", e["event_id"], "Refer to an existing scene layer.")
            if e.get("cue_word_id") and e["cue_word_id"] not in word_ids:
                raise ContractError("INVALID_CUE_WORD", e["event_id"], "Use an ID from frozen alignment map.")
            if e["start_frame"] + e["duration_frames"] > scene["duration_frames"]:
                raise ContractError("SCENE_RANGE_INVALID", e["event_id"], "Event local frames exceed scene length.")


def validate_gate_approval(gate_id: str, state: str, reviewed_sha: str, candidate_sha: str,
                           expected_revision: int, actual_revision: int,
                           predecessors_ok: bool) -> None:
    if gate_id not in {"G1", "G2", "G3", "G4", "G5"} or state != "READY_FOR_REVIEW" or not predecessors_ok:
        raise ContractError("GATE_ILLEGAL_TRANSITION", gate_id, "Review prerequisites and READY_FOR_REVIEW state.")
    if reviewed_sha != candidate_sha or expected_revision != actual_revision:
        raise ContractError("APPROVAL_REVISION_CONFLICT", gate_id, "Refresh exact candidate before approval.")



def validate_archival_candidate_for_g3(asset: dict[str, Any]) -> None:
    """G3 checks additional to shape validation; no automated legal certification."""
    validate_schema("HistoricalAsset.v1", asset)
    if asset["origin"] == "glabs_webhook" and asset["asset_class"] != "AI_ILLUSTRATION":
        raise ContractError("ASSET_CLASS_MISREPRESENTED", asset["asset_id"], "G-Labs output must remain AI_ILLUSTRATION.")
    if not asset["user_approved"]:
        raise ContractError("ASSET_UNAPPROVED", asset["asset_id"], "Human candidate review required.")
    if asset["rights_status"] != "ELIGIBLE" or asset["provenance_status"] != "REVIEWED":
        raise ContractError("RIGHTS_REVIEW_REQUIRED", asset["asset_id"], "Review rights and provenance before G3.")
    if asset["asset_class"] == "HISTORICAL_MAP":
        a, b = asset.get("period_start_year"), asset.get("period_end_year")
        if a is None or b is None or a > b:
            raise ContractError("MAP_PERIOD_MISMATCH", asset["asset_id"], "Provide supported, reviewed date span for this map.")


def validate_historical_map(data: dict[str, Any], event_year: int, feature_id: str | None = None) -> None:
    validate_schema("HistoricalMap.v1", data)
    bbox=data["geography_bbox"]
    if bbox["min_lon"] >= bbox["max_lon"] or bbox["min_lat"] >= bbox["max_lat"]:
        raise ContractError("MAP_GEOMETRY_INVALID", data["historical_map_id"], "BBox must use ordered longitude/latitude.")
    if data["valid_year_from"] > data["valid_year_to"] or not data["valid_year_from"] <= event_year <= data["valid_year_to"]:
        raise ContractError("MAP_PERIOD_MISMATCH", data["historical_map_id"], "Use a source supported at requested event year.")
    if not data["user_approved"]:
        raise ContractError("MAP_UNAPPROVED", data["historical_map_id"], "G3 review required for map geometry.")
    if data["geography_mode"]=="vector_period" and data["geometry_object_sha256"] is None:
        raise ContractError("MAP_GEOMETRY_INVALID", data["historical_map_id"], "Period vector data requires verified immutable geometry.")
    if data["geography_mode"]=="schematic_approved" and not data["schematic_disclosure"]:
        raise ContractError("MAP_DISCLOSURE_REQUIRED", data["historical_map_id"], "Label schema as reconstruction.")
    if feature_id and feature_id not in data["approved_feature_ids"]:
        raise ContractError("MAP_FEATURE_UNKNOWN", feature_id, "Feature reference not in reviewed source data.")


def validate_template_layout(data: dict[str, Any]) -> None:
    validate_schema("TemplateLayout.v1", data)
    slots=data["slots"]
    _unique([s["slot_id"] for s in slots],"DUPLICATE_ID",data["template_id"])
    lim=data["camera_limits"]
    if lim["min_scale"] > lim["max_scale"]:
        raise ContractError("LAYOUT_INVALID", data["template_id"], "Camera min_scale cannot exceed max_scale.")
    safe=data["safe_area_px"]
    if safe["left"]+safe["right"] >= data["canvas"]["width"] or safe["top"]+safe["bottom"] >= data["canvas"]["height"]:
        raise ContractError("LAYOUT_INVALID", data["template_id"], "Safe area leaves no visible canvas.")
    for slot in slots:
        rect=slot["rect_normalized"]
        if rect["x"]+rect["w"] > 1.0 or rect["y"]+rect["h"] > 1.0:
            raise ContractError("LAYOUT_INVALID", slot["slot_id"], "Normalized slot must fit canvas.")


def check_all() -> list[str]:
    completed = []
    for schema_path in sorted(SCHEMAS.glob("*.schema.json")):
        name = schema_path.name.removesuffix(".schema.json")
        data = load_example(name)
        validate_schema(name, data)
        completed.append(name)
    validate_story(load_example("StoryPackage.v1"))
    validate_word_map(load_example("WordTimingMap.v1"), load_example("FinalAudio.v1"))
    validate_asset_resolution(load_example("AssetResolution.v1"))
    return completed


if __name__ == "__main__":
    completed = check_all()
    print(f"Contract fixtures PASS: {len(completed)} schema(s).")
