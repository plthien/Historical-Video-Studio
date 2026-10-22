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
referenced={x["asset_id"] for s in timeline["scenes"] for x in s["layers"] if x["asset_id"]}
if referenced-set(assets):
    raise RuntimeError("G4_ASSET_NOT_APPROVED "+str(referenced-set(assets)))
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
 "fontFamily":font["font_family"],"sourceKind":"APPROVED_LOCAL"
}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_bytes(canonical({"timeline":timeline,"manifest":manifest}))
print(json.dumps({"state":"APPROVED_LOCAL","g4Head":head["manifest_sha256"],
                  "assetCount":len(records),"geometryCount":len(geometries)}))
