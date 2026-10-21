"""B1-02: provenance-checked local GeoJSON ingest; unchanged originals, derived WGS84."""
from __future__ import annotations
import hashlib
import json
import math
from backend.app.contracts import ContractViolation,validate_document
from backend.app.maps.projection import to_wgs84,project

def _canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def _geometry(g,crs,fid):
    if not isinstance(g,dict) or g.get("type") not in ("LineString","Polygon"):
        raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Supply reviewed LineString or Polygon GeoJSON.")
    kind=g["type"]
    coordinates=g.get("coordinates")
    tracks=[coordinates] if kind=="LineString" else coordinates
    if not isinstance(tracks,list) or not tracks:
        raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Geometry coordinates are missing.")
    paths=[]
    for track in tracks:
        if not isinstance(track,list) or len(track)<(2 if kind=="LineString" else 4):
            raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Route requires >=2, polygon ring >=4 vertices.")
        pts=[]
        for v in track:
            if not isinstance(v,list) or len(v)!=2 or any(type(n) not in (int,float) for n in v):
                raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Use strictly [x,y] numeric coordinates.")
            pts.append(list(to_wgs84(v[0],v[1],crs,fid)))
        if kind=="Polygon" and pts[0]!=pts[-1]:
            raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Close polygon rings explicitly.")
        if any(abs(a[0]-b[0])>180 for a,b in zip(pts,pts[1:])):
            raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Antimeridian crossing needs reviewed split geometry.")
        if kind=="Polygon":
            # Shoelace prevents collapsed/zero-area geometry, no silent healing.
            if abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts,pts[1:])))<1e-10:
                raise ContractViolation("MAP_GEOMETRY_INVALID",fid,"Polygon has zero area.")
        paths.append(pts)
    return {"type":kind,"coordinates":paths[0] if kind=="LineString" else paths}

def ingest(map_record:dict,original_bytes:bytes, *,year:int,feature_ids:list[str],
           approval:dict, route_feature_id:str|None=None) -> dict:
    """Approval must be the current G3 approval-head snapshot (AssetResolution._head).

    The caller retrieves this head from the existing ProjectStore; an arbitrary
    unreviewed rights string never authorizes geography. Synthetic tests pass
    an explicitly labelled synthetic review and do not claim actual source rights.
    """
    validate_document("HistoricalMap.v1",map_record)
    mid=map_record["historical_map_id"]
    digest=hashlib.sha256(original_bytes).hexdigest()
    if digest!=map_record["source_original_sha256"] or approval.get("original_sha256")!=digest or (
        approval.get("candidate_id")!=map_record["source_asset_id"] or
        approval.get("approval_record_id")!=map_record["rights_review_record_id"] or
        not map_record["user_approved"]):
        raise ContractViolation("MAP_RIGHTS_UNREVIEWED",mid,
                                "Match exact immutable original bytes and current G3 approval id/candidate.")
    if not map_record["valid_year_from"]<=year<=map_record["valid_year_to"]:
        raise ContractViolation("MAP_PERIOD_MISMATCH",mid,
                                "Select period-reviewed boundaries covering the requested event year; never substitute modern borders.")
    if any(x not in map_record["approved_feature_ids"] for x in feature_ids) or len(set(feature_ids))!=len(feature_ids):
        raise ContractViolation("MAP_FEATURE_UNKNOWN",mid,"Use only reviewed, unique historical feature IDs.")
    mode=map_record["geography_mode"]
    if mode=="schematic_approved" and not map_record["schematic_disclosure"]:
        raise ContractViolation("MAP_DISCLOSURE_MISSING",mid,"Disclose schematic geography visibly.")
    if mode=="raster_georeferenced":
        if map_record["geometry_format"]!="RASTER" or map_record["raster_asset_sha256"]!=digest:
            raise ContractViolation("MAP_GEOMETRY_INVALID",mid,"Raster source and immutable SHA must agree.")
        if feature_ids or route_feature_id:
            raise ContractViolation("MAP_GEOREFERENCE_REQUIRED",mid,
                                    "Raster coordinates remain image UV-only until G3-reviewed tie points are supplied.")
        return {"historical_map":map_record,"source_original_sha256":digest,
                "coordinate_space":"UV_ONLY","features":[],"projected":[],"geometry_sha256":None}
    if map_record["geometry_format"] not in ("GeoJSON","GPKG_DERIVED_GEOJSON"):
        raise ContractViolation("MAP_GEOMETRY_INVALID",mid,"Vector map requires reviewable GeoJSON source.")
    try:
        raw=json.loads(original_bytes)
    except (UnicodeError,ValueError) as exc:
        raise ContractViolation("MAP_GEOMETRY_INVALID",mid,"Original vector must contain valid JSON.") from exc
    if raw.get("type")!="FeatureCollection" or not isinstance(raw.get("features"),list):
        raise ContractViolation("MAP_GEOMETRY_INVALID",mid,"Expected GeoJSON FeatureCollection.")
    source_crs=raw.get("crs")
    if source_crs!=map_record["source_crs"] or source_crs not in ("EPSG:4326","EPSG:3857"):
        raise ContractViolation("MAP_CRS_UNSUPPORTED",mid,
                                "Use explicitly declared EPSG CRS; never assume WGS84 for unknown source.")
    source_ids=[f.get("id") for f in raw["features"]]
    if len(source_ids)!=len(set(source_ids)) or any(not isinstance(x,str) for x in source_ids):
        raise ContractViolation("MAP_FEATURE_INVALID",mid,"GeoJSON feature IDs must be nonempty and unique.")
    if any(x not in source_ids for x in feature_ids):
        raise ContractViolation("MAP_FEATURE_UNKNOWN",mid,"Approved feature missing from pinned original bytes.")
    normalized=[]
    for f in raw["features"]:
        if f["id"] not in feature_ids:continue
        geom=_geometry(f.get("geometry"),source_crs,f["id"])
        if route_feature_id==f["id"] and geom["type"]!="LineString":
            raise ContractViolation("MAP_ROUTE_INVALID",f["id"],"Historical routes require evidence-backed ordered LineString.")
        normalized.append({"type":"Feature","id":f["id"],"geometry":geom,
                           "properties":{"period_reviewed":True}})
    if route_feature_id and route_feature_id not in feature_ids:
        raise ContractViolation("MAP_FEATURE_UNKNOWN",route_feature_id,"Route must be an approved included feature.")
    vertices=[]
    for f in normalized:
        g=f["geometry"];paths=[g["coordinates"]] if g["type"]=="LineString" else g["coordinates"]
        vertices.extend(v for path in paths for v in path)
    bbox=map_record["geography_bbox"]
    if any(not (bbox["min_lon"]<=x<=bbox["max_lon"] and bbox["min_lat"]<=y<=bbox["max_lat"]) for x,y in vertices):
        raise ContractViolation("MAP_GEOMETRY_INVALID",mid,"Derived coordinates exceed reviewed period geography bbox.")
    derived={"type":"FeatureCollection","crs":"EPSG:4326","features":normalized}
    projected=[{"id":f["id"],"points":[list(project(*pt,map_record["map_projection"])) for pt in
        ([pt for ring in f["geometry"]["coordinates"] for pt in ring] if f["geometry"]["type"]=="Polygon"
         else f["geometry"]["coordinates"])]} for f in normalized]
    return {"historical_map":map_record,"source_original_sha256":digest,
            "coordinate_space":"EPSG:4326","features":normalized,"projected":projected,
            "geometry_sha256":hashlib.sha256(_canonical(derived)).hexdigest(),
            "event_year":year, "route_feature_id":route_feature_id,
            "disclosure_required":mode=="schematic_approved"}
