"""B1-05: deterministic bounded scene-local camera with authored focus references."""
from __future__ import annotations

from backend.app.contracts import ContractViolation


def build_camera(plan: dict, layers: list[dict], beat_rows: list[dict], refs: dict,
                 *, duration_frames: int, limits: dict) -> dict:
    ids = {x["layer_id"]: x for x in layers}
    focus = []
    for b in beat_rows:
        target = refs.get(b["focus_ref"])
        if target is None or target not in ids:
            raise ContractViolation("CAMERA_FOCUS_UNKNOWN", b["beat_id"],
                                    "Camera focus must reference an existing authored scene layer.")
        local = b["start_frame"] - beat_rows[0]["start_frame"]
        focus.append({"at_frame": local, "focus_layer_id": target,
                      "focus_geo_feature_id": None, "framing": "subject_center"})
    if not focus:
        raise ContractViolation("CAMERA_FOCUS_UNKNOWN", plan["setup_id"], "At least one authored focus beat is required.")
    intent = plan["editorial_direction"]["camera_intent"]
    mode = {"push_in": "push_in", "pan": "pan", "static": "static",
            "pull_out": "pull_out", "track_route": "track_route",
            "compare_locked": "compare_locked"}.get(intent)
    if mode is None:
        raise ContractViolation("CAMERA_MODE_UNKNOWN", plan["setup_id"], "Choose a supported authored camera intention.")
    min_scale = limits["min_scale"]
    max_scale = limits["max_scale"]
    if mode == "push_in":
        start_scale, end_scale = 1.0, min(1.06, max_scale)
    elif mode == "pull_out":
        start_scale, end_scale = min(1.06, max_scale), 1.0
    else:
        start_scale = end_scale = 1.0
    target = ids[focus[-1]["focus_layer_id"]]["rect_px"]
    # A conservative bounded move toward a real visible layer, never farther than
    # the canonical camera max_translation_px or the usable safe viewport.
    center_x = target["x"] + target["w"] / 2
    center_y = target["y"] + target["h"] / 2
    distance_x = max(-limits["max_translation_px"],
                     min(limits["max_translation_px"], (960-center_x) * .2))
    distance_y = max(-limits["max_translation_px"],
                     min(limits["max_translation_px"], (540-center_y) * .2))
    if mode in ("static", "compare_locked"):
        distance_x = distance_y = 0
    if duration_frames < 1:
        raise ContractViolation("CAMERA_FRAME_INVALID", plan["setup_id"], "Scene camera requires positive native WAV frames.")
    end_at = duration_frames - 1
    def key(t, x, y, scale, easing):
        return {"at_frame": t, "x_px": round(x, 5), "y_px": round(y, 5),
                "scale": scale, "rotation_deg": 0, "opacity": 1, "easing": easing}
    return {"mode": mode,
            "keyframes": [key(0, 0, 0, start_scale, "linear"),
                          key(end_at, distance_x, distance_y, end_scale, "ease_in_out")],
            "focus_entity_id": focus[0]["focus_layer_id"], "clamp_to_content": True,
            "focus_path": focus, "transform_order": "layer_then_group_then_camera"}
