"""Export already approved B1 G4 bytes to a local-only Remotion media manifest.

Only the SQLite G4 compiled-draft head authorizes this operation.
Never registers new G3/G4 approvals or chooses archive candidates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from backend.app.projects.storage import ProjectStore
from backend.app.director import draft
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.director.fingerprint import canonical

parser=argparse.ArgumentParser()
parser.add_argument("--sqlite",type=Path,required=True)
parser.add_argument("--media-root",type=Path,required=True)
parser.add_argument("--project",required=True)
parser.add_argument("--output",type=Path,required=True)
args=parser.parse_args()
store=ProjectStore(args.sqlite,args.media_root)
head=draft.load(store,args.project)
if head["revision"]!=store.revision(args.project):
    raise RuntimeError("G4_SOURCE_STALE: project revision is not current draft")
if draft.current_gate_heads(store,args.project)!=head["manifest"]["gate_heads"]:
    raise RuntimeError("G4_SOURCE_STALE: approved source head changed")
timeline=head["timeline"]
if timeline["project_id"]!=args.project:
    raise RuntimeError("G4_PROJECT_MISMATCH")
story=store.get_story(args.project).data()
assets={}
with store._connection() as db:
    for requirement in story["asset_requirements"]:
        rid=requirement["requirement_id"]
        source=AssetCandidates._source_tx(db,args.project,rid)
        approval=AssetResolution._head(db,args.project,rid,source["requirement_sha256"])
        if approval is None:
            if requirement["required"]:
                raise RuntimeError("G3_ASSET_UNAPPROVED "+rid)
            continue
        original=store.get_artifact(approval["original_sha256"])
        if hashlib.sha256(original).hexdigest()!=approval["original_sha256"]:
            raise RuntimeError("G3_SOURCE_CORRUPT "+rid)
        assets[approval["candidate_id"]]=approval
# Exact G4 effective selection is independent of the frozen G3 primary map.
from backend.app.director.fingerprint import digest
if head["manifest"].get("effective_asset_snapshot_sha256") != digest([
        {"scene_id":s["scene_id"],"assets":s["asset_ids"]} for s in timeline["scenes"]]):
    raise RuntimeError("G4_EFFECTIVE_SOURCE_CORRUPT")
seen_selection=set()
for setup,patches in head["manifest"].get("asset_selection_overrides",{}).items():
    scene=next((s for s in timeline["scenes"] if s["setup_id"]==setup),None)
    if not scene:
        raise RuntimeError("G4_SELECTED_SCENE_MISSING "+setup)
    for layer_id,choice in patches.items():
        layer=next((l for l in scene["layers"] if l["layer_id"]==layer_id),None)
        if not layer or layer["asset_id"]!=choice["candidate_id"] or layer["source_asset_slot_id"]!=choice["slot_id"]:
            raise RuntimeError("G4_SELECTED_LAYER_MISMATCH "+layer_id)
        if layer["layer_kind"] in ("map","territory"):
            raise RuntimeError("G4_MAP_SELECTION_UNREVIEWED "+layer_id)
        plan=next(p for p in head["blueprint"]["setup_plans"] if p["setup_id"]==setup)
        authored=next((v for v in plan["editorial_direction"]["asset_slots"]
                       if v["slot_id"]==choice["slot_id"] and v["requirement_id"]==choice["requirement_id"]),None)
        if not authored:
            raise RuntimeError("G4_SOURCE_SLOT_MISMATCH "+layer_id)
        options=AssetResolution(store).approved_slot_options(args.project,choice["requirement_id"],choice["slot_id"])
        selected=next((v for v in options["options"] if
                       v["candidate_id"]==choice["candidate_id"] and
                       v["review_approval_id"]==choice["review_approval_id"] and
                       v["original_sha256"]==choice["original_sha256"]),None)
        if not selected or options["choice_set_id"]!=choice["choice_set_id"] or options["choice_set_sha256"]!=choice["choice_set_sha256"]:
            raise RuntimeError("G4_SELECTED_SOURCE_STALE "+layer_id)
        assets[choice["candidate_id"]]={"original_sha256":selected["original_sha256"],
            "approval_record_id":selected["review_approval_id"],"candidate_id":selected["candidate_id"]}
        seen_selection.add((setup,layer_id))
# Reviewed polygon derivative is a different asset from the immutable parent.
mask_derivatives=[]
for scene in timeline["scenes"]:
    plan=next(p for p in head["blueprint"]["setup_plans"] if p["setup_id"]==scene["setup_id"])
    for layer in scene["layers"]:
        mask=layer["mask"]
        if mask["kind"]!="polygon_asset":
            continue
        authored=next((s for s in plan["editorial_direction"]["asset_slots"]
                       if s["slot_id"]==layer["source_asset_slot_id"]),None)
        if not authored or not layer["asset_id"] or not mask["asset_id"]:
            raise RuntimeError("RENDER_MASK_DERIVATIVE_UNAPPROVED "+layer["layer_id"])
        item=AssetResolution(store).reviewed_mask(
            args.project,authored["requirement_id"],authored["slot_id"],layer["asset_id"])
        parent=assets.get(layer["asset_id"])
        if (not item or not parent or item["derivative_asset_id"]!=mask["asset_id"] or
            item["parent_original_sha256"]!=parent["original_sha256"] or
            item["source_crop"]!={"x":0,"y":0,"w":1,"h":1}):
            raise RuntimeError("RENDER_MASK_DERIVATIVE_UNAPPROVED "+layer["layer_id"])
        original=store.get_artifact(item["derivative_sha256"])
        from backend.app.assets.alpha_mask import rgba_alpha_extent
        if rgba_alpha_extent(original)!=(item["width"],item["height"]):
            raise RuntimeError("RENDER_MASK_DERIVATIVE_CORRUPT "+layer["layer_id"])
        if item["derivative_asset_id"] in assets and assets[item["derivative_asset_id"]]["original_sha256"]!=item["derivative_sha256"]:
            raise RuntimeError("RENDER_MASK_DERIVATIVE_AMBIGUOUS "+layer["layer_id"])
        assets[item["derivative_asset_id"]]={"candidate_id":item["derivative_asset_id"],
            "original_sha256":item["derivative_sha256"],
            "approval_record_id":item["review_id"]}
        mask_derivatives.append({
            "derivativeAssetId":item["derivative_asset_id"],
            "derivativeSha256":item["derivative_sha256"],
            "parentCandidateId":layer["asset_id"],
            "parentOriginalSha256":item["parent_original_sha256"],
            "reviewId":item["review_id"],"width":item["width"],"height":item["height"],
            "sourceCrop":item["source_crop"]})
referenced={aid for s in timeline["scenes"] for layer in s["layers"]
            for aid in (layer["asset_id"],layer["mask"]["asset_id"]) if aid}
if referenced-set(assets):
    raise RuntimeError("G4_ASSET_NOT_APPROVED "+str(referenced-set(assets)))
# Numeric evidence is a separate current G1-reviewed approval, never a render prop assertion.
from backend.app.projects.numeric_series import NumericSeries
owner=NumericSeries(store)
numeric={}
with store._connection() as db:
    current=db.execute("""SELECT e.claim_id,e.series_id,e.approval_id,e.series_sha256,e.snapshot_json
        FROM numeric_series_heads h JOIN numeric_series_events e
          ON h.approval_id=e.approval_id
        WHERE h.project_id=?""",(args.project,)).fetchall()
for claim,sid,approval,series_sha,raw in current:
    row=owner.get(args.project,claim,sid)
    record=json.loads(raw)
    if (row is None or not row["current"] or row["approval_id"]!=approval or
        row["series_sha256"]!=series_sha or
        hashlib.sha256(canonical(record)).hexdigest()!=series_sha):
        raise RuntimeError("RENDER_NUMBER_SERIES_STALE "+sid)
    for point in record["observations"]:
        store.get_artifact(point["source_evidence_sha256"])
    if sid in numeric:
        raise RuntimeError("RENDER_NUMBER_SERIES_AMBIGUOUS "+sid)
    numeric[sid]={
        "seriesId":sid,"claimId":claim,"storySha256":record["frozen_story_sha256"],
        "g1ApprovalId":record["g1_approval_id"],"approvalId":approval,
        "seriesSha256":series_sha,"durationFrames":record["authored_duration_frames"],
        "precision":record["precision"],"unit":record["unit"],
        "startValue":record["start_value"],"endValue":record["end_value"],
        "observations":[{"frameOffset":v["frame_offset"],"value":v["value"],
                         "evidenceSha256":v["source_evidence_sha256"]}
                        for v in record["observations"]]
    }
for scene in timeline["scenes"]:
    for event in scene["events"]:
        if event["preset_id"]!="number-count":
            continue
        sid=event["params"].get("approved_numeric_series_id")
        source=numeric.get(sid)
        layer=next((l for l in scene["layers"] if l["layer_id"]==event["layer_id"]),None)
        if (not source or not layer or layer["source_claim_id"]!=source["claimId"] or
            event["duration_frames"]!=source["durationFrames"] or
            event["params"]["source_claim_id"]!=source["claimId"]):
            raise RuntimeError("RENDER_NUMBER_SERIES_UNVERIFIED "+event["event_id"])
if draft.current_numeric_heads(store,args.project)!=head["manifest"].get("numeric_series_heads",{}):
    raise RuntimeError("G4_NUMERIC_SERIES_STALE")
records=[]
for aid in sorted(referenced):
    source=assets[aid]
    original=store.get_artifact(source["original_sha256"])
    signature=original[:8]
    if signature.startswith(b"\x89PNG"):
        mime="image/png"
    elif signature[:3]==b"\xff\xd8\xff":
        mime="image/jpeg"
    elif signature[:4]==b"RIFF" and original[8:12]==b"WEBP":
        mime="image/webp"
    else:
        raise RuntimeError("RENDER_UNSUPPORTED_MEDIA "+aid)
    # ArtifactStore's own hashed subdirectories and immutability are authoritative.
    path=store.artifacts.path(source["original_sha256"])
    records.append({"assetId":aid,"path":str(path.relative_to(store.artifacts.root)).replace("\\","/"),
                    "originalSha256":source["original_sha256"],"approvalRecordId":source["approval_record_id"],
                    "sourceKind":"APPROVED_LOCAL","mime":mime})
geometries=[]
reviewed_maps={}
for scene in timeline["scenes"]:
    ctx=head["manifest"]["maps"].get(scene["setup_id"],{})
    for layer in scene["layers"]:
        binding=layer.get("map_binding")
        if not binding:
            continue
        matching=[entry for entry in ctx.get("sources",{}).values()
                  if entry["historical_map"]["historical_map_id"]==binding["historical_map_id"]]
        if len(matching)!=1:
            raise RuntimeError("RENDER_PERIOD_MAP_UNREVIEWED "+scene["setup_id"])
        reviewed=matching[0]
        if reviewed["source_original_sha256"]!=assets[layer["asset_id"]]["original_sha256"]:
            raise RuntimeError("RENDER_MAP_SHA_STALE "+scene["setup_id"])
        record=reviewed["historical_map"]
        bbox=record["geography_bbox"]
        if scene["template_id"]=="T07":
            viewport=ctx.get("shared_viewport")
            projection=ctx.get("shared_projection")
            if not viewport or not projection:
                raise RuntimeError("RENDER_PERIOD_VIEWPORT_UNREVIEWED")
        else:
            projection=record["map_projection"]
            viewport=[bbox["min_lon"],bbox["min_lat"],bbox["max_lon"],bbox["max_lat"]]
        reviewed_maps[binding["historical_map_id"]]={
            "historicalMapId":binding["historical_map_id"],"projection":projection,
            "viewport":viewport,"reviewedYear":ctx["era_year"],
            "sourceOriginalSha256":reviewed["source_original_sha256"],
            "coordinateKind":binding["coordinate_kind"]
        }
for scene in timeline["scenes"]:
    ctx=head["manifest"]["maps"].get(scene["setup_id"],{})
    for layer in scene["layers"]:
        ref=layer.get("path_geometry_ref")
        if not ref:
            continue
        if layer["layer_kind"]=="route":
            matched=[]
            for m in ctx.get("sources",{}).values():
                matched.extend((m,f) for f in m.get("features",[]) if f["id"]==ref)
            if len(matched)!=1 or matched[0][1]["geometry"]["type"]!="LineString":
                raise RuntimeError("RENDER_ROUTE_UNREVIEWED "+ref)
            m,feat=matched[0]
            bbox=m["historical_map"]["geography_bbox"]
            geometries.append({"geometryRef":ref,"coordinates":feat["geometry"]["coordinates"],
                  "coordinateSpace":"WGS84","historicalMapId":m["historical_map"]["historical_map_id"],
                  "reviewedYear":ctx["era_year"],
                  "bbox":[bbox["min_lon"],bbox["min_lat"],bbox["max_lon"],bbox["max_lat"]],
                  "sourceOriginalSha256":m["source_original_sha256"]})
        elif layer["layer_kind"]=="annotation":
            # Editorial path derived from frozen node rectangles only, never a
            # synthetic geographic route or new causal/factual assertion.
            nodes=[l for l in scene["layers"] if l["layer_kind"] in ("callout","date","headline")]
            if len(nodes)<2 or not layer.get("source_claim_id"):
                raise RuntimeError("RENDER_EDITORIAL_UNSOURCED "+ref)
            a,b=nodes[:2]
            ar,br=a["rect_px"],b["rect_px"]
            x0=(ar["x"]+ar["w"]/2-layer["rect_px"]["x"])/layer["rect_px"]["w"]
            y0=(ar["y"]+ar["h"]/2-layer["rect_px"]["y"])/layer["rect_px"]["h"]
            x1=(br["x"]+br["w"]/2-layer["rect_px"]["x"])/layer["rect_px"]["w"]
            y1=(br["y"]+br["h"]/2-layer["rect_px"]["y"])/layer["rect_px"]["h"]
            geometries.append({"geometryRef":ref,"coordinates":[[x0,y0],[x1,y1]],
                "coordinateSpace":"ANNOTATION_CANVAS","historicalMapId":None,
                "reviewedYear":None,"bbox":None,
                "sourceOriginalSha256":"0"*64})
        else:
            raise RuntimeError("RENDER_GEOMETRY_KIND_UNSUPPORTED "+layer["layer_kind"])
font=head["manifest"]["font_identity"]
font_path=Path(os.environ["WINDIR"])/"Fonts"/font["font_file"]
if hashlib.sha256(font_path.read_bytes()).hexdigest()!=font["font_sha256"]:
    raise RuntimeError("FONT_IDENTITY_STALE")
manifest={
 "projectId":args.project,"g4ManifestSha256":head["manifest_sha256"],
 "mediaRoot":str(store.artifacts.root.resolve()),
 "assets":records,"geometries":geometries,"maps":list(reviewed_maps.values()),
 "fontFile":str(font_path),"fontSha256":font["font_sha256"],
 "fontFamily":font["font_family"],"sourceKind":"APPROVED_LOCAL",
 "approvedNumericSeries":numeric,"maskDerivatives":mask_derivatives
}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_bytes(canonical({"timeline":timeline,"manifest":manifest}))
if (store.revision(args.project)!=head["revision"] or
    draft.current_gate_heads(store,args.project)!=head["manifest"]["gate_heads"] or
    draft.current_numeric_heads(store,args.project)!=head["manifest"].get("numeric_series_heads",{})):
    args.output.unlink(missing_ok=True)
    raise RuntimeError("G4_SOURCE_STALE: approval changed during media export")
print(json.dumps({"state":"APPROVED_LOCAL","g4Head":head["manifest_sha256"],
                  "assetCount":len(records),"geometryCount":len(geometries)}))
