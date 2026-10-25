"""B1-04: registered source-bound layers; originals remain immutable."""
from __future__ import annotations

from backend.app.contracts import ContractViolation
from backend.app.director.layout import pixel_geometry, role_bounds, selected_layout

TEXT_ROLES = {"text", "headline", "date", "callout"}
ASSET_CLASSES = {
    "map": {"HISTORICAL_MAP"}, "portrait": {"ARCHIVAL_PHOTO", "HISTORICAL_ARTWORK"},
    "archival_photo": {"ARCHIVAL_PHOTO", "HISTORICAL_ARTWORK"},
    "document": {"HISTORICAL_DOCUMENT"}, "decorative_paper": {"HISTORICAL_DOCUMENT"},
    "territory": {"HISTORICAL_MAP"},
}


def _blocked(code, path, what):
    raise ContractViolation(code, path, what)


def _text_layout(source, rect, font_measure):
    """Measure actual glyphs through a supplied pinned glyph-width provider.

    No character-count fitting and no quiet font replacement. B2 controls final
    browser font parity; this gate rejects missing metrics.
    """
    if font_measure is None or not callable(font_measure):
        _blocked("FONT_METRICS_REQUIRED", source["text_id"],
                 "Supply measured pinned-font glyph bounds before compiling text.")
    max_lines = min(source["max_lines"], 8)
    text = source["text"]
    options = (64, 56, 48, 40, 32, 28, 24, 20)
    for size in options:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            proposed = (current + " " + word).strip()
            if font_measure(proposed, size)[0] <= rect["w"]:
                current = proposed
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if (len(lines) <= max_lines and
                all(font_measure(line, size)[0] <= rect["w"] for line in lines) and
                len(lines) * font_measure("Hg", size)[1] * 1.16 <= rect["h"]):
            return {"font_token": "headline_sans", "font_size_px": size,
                    "line_height": 1.16, "letter_spacing_px": 0,
                    "horizontal_align": "left", "vertical_align": "center",
                    "max_lines": max_lines, "overflow": "block"}
    _blocked("TYPOGRAPHY_OVERFLOW", source["text_id"],
             "Actual measured glyph extents exceed this approved layout; revise text layout without changing G1 claims.")


def build_layers(plan: dict, approved: dict, requirements: dict, *,
                 maps: dict | None = None, font_measure=None,
                 reviewed_masks: dict | None = None) -> tuple[list[dict], dict[str,str]]:
    layout = selected_layout(plan)
    rects = pixel_geometry(plan)
    authored = plan["editorial_direction"]
    sources = {s["slot_id"]: s for s in authored["asset_slots"]}
    bindings = {s["slot_id"]: s for s in plan["asset_slot_bindings"]}
    texts = {t["text_id"].split("_", 2)[-1]: t for t in authored["on_screen_text"]}
    text_by_id = {t["text_id"]:t for t in authored["on_screen_text"]}
    layers = []
    ref_map = {}
    used_photo = set()
    for slot in layout["slots"]:
        sid, role = slot["slot_id"], slot["role"]
        source = next((x for x in sources.values() if x["semantic_role"] == sid or
                       x["slot_id"].endswith("_" + sid)), None)
        # Generic legacy synthetic setup slots can bind only when the single
        # authored G1 source has a compatible unambiguous registered role.
        if source is None and role in ASSET_CLASSES:
            possible = [x for x in sources.values()
                        if requirements.get(x["requirement_id"], {}).get("asset_class") in ASSET_CLASSES[role]]
            if len(possible)==1 and len([s for s in layout["slots"]
                   if s["required"] and s["role"] in ASSET_CLASSES and
                   requirements.get(possible[0]["requirement_id"], {}).get("asset_class")
                       in ASSET_CLASSES[s["role"]]]) == 1 and slot["required"]:
                source = possible[0]
        txt = texts.get(sid)
        payload = plan["template_payload"]
        if role in TEXT_ROLES and txt is None:
            text_ref = None
            if plan["template_id"] == "T07":
                text_ref = {"date_before": "date_before_text_id",
                            "date_after": "date_after_text_id"}.get(sid)
            elif plan["template_id"] == "T09":
                text_ref = {"quote_text": "headline_text_id",
                            "attribution": "attribution_text_id"}.get(sid)
            if text_ref:
                txt = text_by_id.get(payload[text_ref])
        if txt is None and role in TEXT_ROLES:
            if plan["template_id"] == "T08" and sid == "fact_value":
                payload = plan["template_payload"]
                txt = {"text_id": "text_" + plan["setup_id"] + "_value",
                       "text": payload["display_value"], "role":"date",
                       "claim_ref": payload["fact_claim_id"], "max_lines": 1}
            elif plan["template_id"] == "T06" and sid == "verified_excerpt":
                txt = text_by_id.get(plan["template_payload"]["excerpt_text_id"])
            else:
                matches = [x for x in authored["on_screen_text"] if
                           x["role"] == role or (role=="text" and x["role"]=="caption")]
                if len(matches)==1 and sum(1 for slot2 in layout["slots"] if
                         slot2["required"] and slot2["role"]==role)==1:
                    txt = matches[0]
        is_route = role == "route"
        is_editorial_connector = role == "annotation" and plan["template_id"] == "T10"
        if role in TEXT_ROLES and txt is None and not slot["required"]:
            continue
        if role in TEXT_ROLES and txt is None and slot["required"]:
            _blocked("LAYOUT_TEXT_MISSING", sid, "Supply the approved authored on-screen text for this required slot.")
        if not is_route and not is_editorial_connector and role not in TEXT_ROLES and source is None:
            if slot["required"]:
                _blocked("LAYOUT_SOURCE_MISSING", sid, "Bind the required template role to an authored source slot.")
            continue
        candidate = None
        if source is not None:
            bind = bindings.get(source["slot_id"])
            if bind is None or bind["requirement_id"] != source["requirement_id"]:
                _blocked("ASSET_SLOT_MISMATCH", sid, "Match the authored and blueprint source slot identities.")
            candidate = approved.get(bind["requirement_id"])
            req = requirements.get(bind["requirement_id"])
            if (not candidate or not req or candidate.get("asset_class") != req["asset_class"]
                    or role not in ASSET_CLASSES or req["asset_class"] not in ASSET_CLASSES[role]
                    or not candidate.get("approval_record_id") or not candidate.get("original_sha256")
                    or not candidate.get("candidate_id")
                    or (bind.get("approved_asset_id") and bind["approved_asset_id"] != candidate["candidate_id"])):
                _blocked("G3_ASSET_UNAPPROVED", sid,
                         "Resolve an exact current G3 approval, asset class, candidate and immutable original SHA.")
            if candidate.get("source_kind") == "AI_ILLUSTRATION" and role != "decorative_paper":
                _blocked("ASSET_PROVENANCE_INVALID", sid, "Do not substitute an AI illustration for archival material.")
            if role == "archival_photo":
                if candidate["candidate_id"] in used_photo:
                    _blocked("PHOTO_CARD_DUPLICATE", sid, "T03 cards require independent approved original sources.")
                used_photo.add(candidate["candidate_id"])
        if is_route and not (maps and maps.get(plan["setup_id"], {}).get("route_feature_id")):
            _blocked("MAP_ROUTE_INVALID", sid, "Require an approved ordered period route before adding route overlay.")
        ident = "layer_" + plan["setup_id"] + "_" + sid
        ref_map[sid] = ident
        if source is not None:
            ref_map[source["slot_id"]] = ident
        if txt is not None:
            ref_map[txt["text_id"]] = ident
        rect = rects[sid]
        map_binding = None
        if role in ("map", "territory") and candidate is not None:
            map_source = (maps or {}).get(plan["setup_id"], {}).get("sources", {}).get(source["requirement_id"])
            if map_source is not None:
                if (map_source.get("source_original_sha256") != candidate["original_sha256"]
                        or map_source["historical_map"]["source_asset_id"] != candidate["candidate_id"]
                        or map_source["historical_map"]["rights_review_record_id"] != candidate["approval_record_id"]):
                    _blocked("MAP_RIGHTS_UNREVIEWED", sid,
                             "Normalized historical map must match exact current G3 original and review event.")
                coord = ("raster_uv" if map_source["coordinate_space"]=="UV_ONLY" else "geo_wgs84")
                map_binding = {"historical_map_id":map_source["historical_map"]["historical_map_id"],
                               "feature_id":map_source["features"][0]["id"] if map_source["features"] else None,
                               "coordinate_kind":coord,"anchor_latlon":None}
        layer = {
            "layer_id": ident, "layer_kind": role,
            "asset_id": candidate["candidate_id"] if candidate else None,
            "text": txt["text"] if txt else None,
            "source_claim_id": (txt["claim_ref"] if txt else
                payload["causal_links"][0]["relationship_claim_id"] if is_editorial_connector else None),
            "z_index": slot["z_index"], "rect_px": rect,
            "anchor": "top_left",
            "crop_normalized": {"x": 0., "y": 0., "w": 1., "h": 1.},
            "object_fit": slot["fit"],
            "mask": {"kind": "none", "asset_id": None, "feather_px": 0},
            "style": {"font_token": "headline_sans" if txt else None,
                      "color_token": None, "stroke_token": None,
                      "max_lines": min(slot["max_lines"], 8)},
            "map_binding": map_binding,
            "parent_layer_id": None, "group_id": "group_" + plan["setup_id"],
            "transform_origin": {"x": .5, "y": .5}, "depth_order": slot["z_index"],
            "treatment": {"kind": ("headline_text" if txt else
                                   "ink_map" if role == "map" else
                                   "source_photo_card" if role in ("archival_photo", "portrait") else
                                   "paper_document" if role == "document" else "none"),
                          "source_preserving": True,
                          "evidence_badge": "archival" if candidate else "none"},
            "path_geometry_ref": (maps[plan["setup_id"]]["route_feature_id"] if is_route else
                                  "connector_" + plan["setup_id"] if is_editorial_connector else None),
            "text_layout": _text_layout(txt, rect, font_measure) if txt else None,
            "template_slot_id": sid,
            "source_asset_slot_id": source["slot_id"] if source else None,
        }
        layers.append(layer)
    # Only a current, separately G3-reviewed derivative may implement strict T02.
    # Other native masks and framed portraits retain their prior behavior.
    if plan["template_id"] == "T02" and plan["template_payload"]["cutout_policy"] == "use_reviewed_mask":
        portrait_slot=plan["template_payload"]["portrait_slot_id"]
        portrait=next((layer for layer in layers
                       if layer["source_asset_slot_id"]==portrait_slot and
                       layer["layer_kind"] in ("portrait","archival_photo")),None)
        reviewed=(reviewed_masks or {}).get(portrait_slot)
        if (not portrait or not reviewed or
            reviewed["parent_candidate_id"]!=portrait["asset_id"] or
            reviewed["source_crop"]!={"x":0,"y":0,"w":1,"h":1}):
            _blocked("PORTRAIT_MASK_UNREVIEWED",plan["setup_id"],
                     "Current G3 mask must exactly match the authored portrait and full source coordinate frame.")
        portrait["mask"]={"kind":"polygon_asset",
                          "asset_id":reviewed["derivative_asset_id"],"feather_px":0}
    # T06 excerpt UV is an explicit non-destructive crop on the approved original.
    if plan["template_id"] == "T06":
        payload = plan["template_payload"]
        document = next((x for x in layers
                         if x["source_asset_slot_id"] == payload["document_slot_id"]), None)
        if document is None:
            _blocked("DOCUMENT_CROP_INVALID", plan["setup_id"],
                     "The authored excerpt must resolve to the approved document layer.")
        crop = payload["focus_region_uv"]
        if (crop["x"] < 0 or crop["y"] < 0 or crop["w"] <= 0 or crop["h"] <= 0
                or crop["x"] + crop["w"] > 1 or crop["y"] + crop["h"] > 1):
            _blocked("DOCUMENT_CROP_INVALID", plan["setup_id"],
                     "Excerpt UV must remain strictly inside the original document.")
        document["crop_normalized"] = dict(crop)
    role_bounds(layout, layers)
    if plan["template_id"] == "T03":
        cards=plan["template_payload"]["cards"]
        by_source={x["asset_slot_id"]:x for x in cards}
        if (sum(x["card_role"]=="hero" for x in cards)!=1 or
                len({x["asset_slot_id"] for x in cards})!=len(cards)):
            _blocked("COLLAGE_HERO_INVALID", plan["setup_id"],
                     "T03 must preserve one hero and separately authored card source IDs.")
        source_layers=[x for x in layers if x["layer_kind"]=="archival_photo"]
        if len(source_layers)!=len(cards):
            _blocked("COLLAGE_SOURCE_MISSING", plan["setup_id"],
                     "Do not silently omit T03 authored approved evidence cards.")
        for layer in source_layers:
            card=by_source.get(layer["source_asset_slot_id"])
            if card is None:
                _blocked("COLLAGE_SOURCE_MISSING", layer["layer_id"],
                         "Card layout must resolve each authored G3 source slot.")
            layer["depth_order"]=card["depth_plane"]
    if plan["template_id"] == "T04":
        route=next((x for x in layers if x["layer_kind"]=="route"),None)
        backdrop=next((x for x in layers if x["layer_kind"]=="map"),None)
        active=(maps or {}).get(plan["setup_id"],{})
        if (route is None or backdrop is None or
                not active.get("reviewed_period_map") or
                route["path_geometry_ref"]!=plan["template_payload"]["route_geometry_ref"]):
            _blocked("MAP_ROUTE_INVALID", plan["setup_id"],
                     "T04 needs an approved period map and separately reviewed authored route geometry.")
        if route["z_index"]<=backdrop["z_index"]:
            _blocked("LAYOUT_ROLE_MISMATCH", plan["setup_id"], "Route must overlay the reviewed map.")
    if plan["template_id"] == "T07":
        names = [x for x in layers if x["layer_kind"] == "map"]
        if len(names) != 2 or names[0]["asset_id"] == names[1]["asset_id"]:
            _blocked("MAP_PAIR_NOT_DISTINCT", plan["setup_id"],
                     "T07 requires distinct reviewed before and after maps.")
        a = (maps or {}).get(plan["setup_id"], {})
        if not a.get("shared_viewport") or not a.get("shared_projection"):
            _blocked("MAP_PROJECTION_MISMATCH", plan["setup_id"],
                     "T07 period maps require a reviewed shared projection and viewport.")
    return layers, ref_map
