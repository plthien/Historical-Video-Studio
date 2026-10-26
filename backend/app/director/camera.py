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
    moves = [b.get("focus_move", "none") for b in beat_rows
             if b.get("focus_move", "none") not in ("none", "static")]
    move_mode = {"subject_to_subject": "pan", "detail_to_overview": "pull_out",
                 "overview_to_detail": "push_in", "follow_path": "track_route"}
    intent = move_mode.get(moves[-1], plan["editorial_direction"]["camera_intent"]) if moves else plan["editorial_direction"]["camera_intent"]
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


def compose_camera_events(camera: dict, events: list[dict], layers: list[dict],
                          *, duration_frames: int, limits: dict) -> dict:
    """Compile registered screen camera events into the *single* sampled camera track.

    The authored focus camera remains the baseline. Event displacement is relative
    to its authored starting target; it is never applied a second time by a layer.
    Freeze and G2 cue timing are unaffected. Keyframes are sampled once per real
    scene frame so event boundaries and their easing cannot drift between Player
    and Node.
    """
    import math

    camera_events = sorted((e for e in events if e["preset_id"] in
                            ("camera-pan", "camera-push")),
                           key=lambda e: (e["start_frame"], e["event_id"]))
    if not camera_events:
        return camera
    by_id = {layer["layer_id"]: layer for layer in layers}
    previous_end = -1
    for event in camera_events:
        start = event["start_frame"]
        end = start + event["duration_frames"]
        if (event["motion_space"] != "screen" or start < 0 or
                end > duration_frames or start < previous_end):
            raise ContractViolation("CAMERA_EVENT_INVALID", event["event_id"],
                                    "Screen camera event must have a nonoverlapping scene-local interval.")
        previous_end = end
        params = event["params"]
        targets = (("start_target_layer_id", "end_target_layer_id")
                   if event["preset_id"] == "camera-pan" else ("focus_layer_id",))
        if any(params.get(key) not in by_id for key in targets):
            raise ContractViolation("CAMERA_TARGET_UNAPPROVED", event["event_id"],
                                    "Camera movement must target an existing frozen layer.")
        if event["preset_id"] == "camera-pan" and params["keep_context_visible"] is not True:
            raise ContractViolation("CAMERA_CONTEXT_INVALID", event["event_id"],
                                    "Retain the registered camera context constraint.")

    def sample_baseline(frame):
        keys = camera["keyframes"]
        a = keys[0]
        for b in keys[1:]:
            if frame <= b["at_frame"]:
                span = b["at_frame"] - a["at_frame"]
                t = max(0.0, min(1.0, (frame - a["at_frame"]) / span)) if span > 0 else 1.0
                if b["easing"] == "ease_in_out":
                    t = t * t * (3 - 2 * t)
                elif b["easing"] == "ease_in":
                    t = t * t
                elif b["easing"] == "ease_out":
                    t = 1 - (1 - t) ** 2
                return {key: a[key] + (b[key] - a[key]) * t
                        for key in ("x_px", "y_px", "scale", "rotation_deg", "opacity")}
            a = b
        return {key: keys[-1][key] for key in
                ("x_px", "y_px", "scale", "rotation_deg", "opacity")}

    def center(layer_id):
        r = by_id[layer_id]["rect_px"]
        return (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)

    result = []
    for frame in range(duration_frames):
        row = sample_baseline(frame)
        dx = dy = ds = 0.0
        for event in camera_events:
            start, length = event["start_frame"], event["duration_frames"]
            if frame < start:
                continue
            p = max(0.0, min(1.0, (frame-start) / max(1, length-1)))
            p = p * p * (3 - 2 * p)
            params = event["params"]
            if event["preset_id"] == "camera-pan":
                ax, ay = center(params["start_target_layer_id"])
                bx, by = center(params["end_target_layer_id"])
                vx, vy = (ax - bx) * .2, (ay - by) * .2
                magnitude = math.hypot(vx, vy)
                bound = min(float(params["max_translate_px"]), limits["max_translation_px"])
                factor = min(1.0, bound / magnitude) if magnitude else 0.0
                dx += vx * factor * p
                dy += vy * factor * p
            else:
                cx, cy = center(params["focus_layer_id"])
                vx, vy = (960-cx) * .2, (540-cy) * .2
                magnitude = math.hypot(vx, vy)
                bound = min(float(params["max_drift_px"]), limits["max_translation_px"])
                factor = min(1.0, bound / magnitude) if magnitude else 0.0
                dx += vx * factor * p
                dy += vy * factor * p
                ds += (float(params["to_scale"]) - float(params["from_scale"])) * p
        x, y, scale = row["x_px"] + dx, row["y_px"] + dy, row["scale"] + ds
        if (not all(math.isfinite(v) for v in (x, y, scale)) or
                abs(x) > limits["max_translation_px"] + 1e-6 or
                abs(y) > limits["max_translation_px"] + 1e-6 or
                not limits["min_scale"] <= scale <= limits["max_scale"]):
            raise ContractViolation("CAMERA_TRAJECTORY_OUT_OF_BOUNDS", camera_events[0]["event_id"],
                                    "An event exceeds the authored viewport camera limits.")
        result.append({"at_frame": frame, "x_px": round(x, 5),
                       "y_px": round(y, 5), "scale": round(scale, 6),
                       "rotation_deg": round(row["rotation_deg"], 5),
                       "opacity": round(row["opacity"], 5), "easing": "linear"})
    if len(result) < 2:
        raise ContractViolation("CAMERA_EVENT_INVALID", camera_events[0]["event_id"],
                                "A camera animation needs two real frames.")
    return {**camera, "mode": ("pan" if camera_events[-1]["preset_id"] == "camera-pan"
                              else "push_in" if camera_events[-1]["params"]["to_scale"] >=
                              camera_events[-1]["params"]["from_scale"] else "pull_out"),
            "keyframes": result}
