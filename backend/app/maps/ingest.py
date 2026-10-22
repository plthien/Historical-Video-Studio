"""B1-02: provenance-checked local GeoJSON ingest; unchanged originals, derived WGS84."""
from __future__ import annotations
import hashlib
import json
import math
from backend.app.contracts import ContractViolation,validate_document
from backend.app.maps.projection import to_wgs84,project

def _canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


def _valid_polygon_rings(paths, fid):
    """Exact topology checks on the existing 10-decimal WGS84 coordinate grid."""
    scale = 10**10
    rings = [[(round(x*scale), round(y*scale)) for x,y in path] for path in paths]
    def invalid(reason):
        raise ContractViolation("MAP_GEOMETRY_INVALID", fid,
                                reason + " Supply independently reviewed valid polygon rings.")
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,p):
        return cross(a,b,p)==0 and (min(a[0],b[0])<=p[0]<=max(a[0],b[0])
                                    and min(a[1],b[1])<=p[1]<=max(a[1],b[1]))
    def intersect(a,b,c,d):
        q=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)]
        return ((q[0]*q[1]<0 and q[2]*q[3]<0)
                or any((q[0]==0 and on(a,b,c),q[1]==0 and on(a,b,d),
                        q[2]==0 and on(c,d,a),q[3]==0 and on(c,d,b))))
    def inside(p,ring):
        if any(on(a,b,p) for a,b in zip(ring,ring[1:])):
            return False
        state=False
        for a,b in zip(ring,ring[1:]):
            if (a[1]>p[1])!=(b[1]>p[1]) and (cross(a,b,p)>0)==(b[1]>a[1]):
                state=not state
        return state

    for r in rings:
        n=len(r)-1
        if r[0]!=r[-1] or len(set(r[:-1]))!=n:
            invalid("Polygon rings must close without repeated nonconsecutive vertices.")
        if any(a==b for a,b in zip(r,r[1:])):
            invalid("Polygon has zero-length edges.")
        area2=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(r,r[1:]))
        if abs(area2)<10**10:
            invalid("Polygon has zero or negligible area.")
        for i in range(n):
            a,b,c=r[i],r[(i+1)%n],r[(i+2)%n]
            if cross(a,b,c)==0 and ((a[0]-b[0])*(c[0]-b[0])
                                      +(a[1]-b[1])*(c[1]-b[1]))>0:
                invalid("Adjacent polygon edges cannot backtrack or overlap.")
            for j in range(i+2,n):
                if i==0 and j==n-1:
                    continue  # One shared ring endpoint is valid.
                if intersect(a,b,r[j],r[j+1]):
                    invalid("Polygon has nonadjacent crossing, contact, or overlap.")
    # Every hole must be strictly inside the exterior and holes must be disjoint.
    for i in range(1,len(rings)):
        if not inside(rings[i][0],rings[0]):
            invalid("Polygon interior ring is not strictly within the exterior.")
        for j in range(i):
            if j>0 and (inside(rings[i][0],rings[j]) or inside(rings[j][0],rings[i])):
                invalid("Polygon interior rings cannot contain one another.")
            if any(intersect(a,b,c,d)
                   for a,b in zip(rings[i],rings[i][1:])
                   for c,d in zip(rings[j],rings[j][1:])):
                invalid("Polygon rings cannot touch or intersect.")


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
        paths.append(pts)
    if kind=="Polygon":
        _valid_polygon_rings(paths,fid)
    return {"type":kind,"coordinates":paths[0] if kind=="LineString" else paths}

def ingest(map_record:dict,original_bytes:bytes, *,year:int,feature_ids:list[str],
           approval:dict, route_feature_id:str|None=None,
           reviewed_tie_points:list[dict]|None=None) -> dict:
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
                                    "Raster cannot expose GeoJSON features or route without a separate reviewed vector source.")
        if not reviewed_tie_points:
            return {"historical_map":map_record,"source_original_sha256":digest,
                    "coordinate_space":"UV_ONLY","features":[],"projected":[],"geometry_sha256":None}
        if len(reviewed_tie_points)<3:
            raise ContractViolation("MAP_GEOREFERENCE_REQUIRED",mid,"At least 3 reviewed noncollinear UV/lonlat tie points required.")
        if any(p.get("rights_review_record_id")!=map_record["rights_review_record_id"] or
               p.get("source_original_sha256")!=digest or not p.get("user_approved") or
               any(type(p.get(k)) not in (int,float) for k in ("u","v","lon","lat")) or
               not (0<=p["u"]<=1 and 0<=p["v"]<=1)
               for p in reviewed_tie_points):
            raise ContractViolation("MAP_GEOREFERENCE_REQUIRED",mid,"Bind reviewed tie points to exact original SHA and G3 rights evidence.")
        p0,p1,p2=reviewed_tie_points[:3]
        d=(p1["u"]-p0["u"])*(p2["v"]-p0["v"])-(p2["u"]-p0["u"])*(p1["v"]-p0["v"])
        if abs(d)<1e-9:
            raise ContractViolation("MAP_GEOREFERENCE_REQUIRED",mid,"Reviewed tie points cannot be collinear.")
        def affine(attr):
            dx=p1[attr]-p0[attr];dy=p2[attr]-p0[attr]
            a=(dx*(p2["v"]-p0["v"])-dy*(p1["v"]-p0["v"]))/d
            b=(dy*(p1["u"]-p0["u"])-dx*(p2["u"]-p0["u"]))/d
            return (a,b,p0[attr]-a*p0["u"]-b*p0["v"])
        lon=affine("lon");lat=affine("lat")
        def uv(u,v):return (lon[0]*u+lon[1]*v+lon[2],lat[0]*u+lat[1]*v+lat[2])
        bbox=map_record["geography_bbox"]
        corners=[uv(u,v) for u,v in ((0,0),(1,0),(0,1),(1,1))]
        if any(not (bbox["min_lon"]<=a<=bbox["max_lon"] and bbox["min_lat"]<=b<=bbox["max_lat"])
               for a,b in corners):
            raise ContractViolation("MAP_GEOREFERENCE_REQUIRED",mid,"Georeference corners exceed reviewed historical bbox.")
        geo={"uv_lon_coefficients":lon,"uv_lat_coefficients":lat,
             "source_original_sha256":digest,
             "rights_review_record_id":map_record["rights_review_record_id"]}
        return {"historical_map":map_record,"source_original_sha256":digest,
                "coordinate_space":"REVIEWED_RASTER_UV_TO_GEO","features":[],
                "projected":[list(project(a,b,map_record["map_projection"])) for a,b in corners],
                "georeference":geo,"geometry_sha256":hashlib.sha256(_canonical(geo)).hexdigest()}
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
    normalized_sha=hashlib.sha256(_canonical(derived)).hexdigest()
    if map_record["geometry_object_sha256"] not in (None,normalized_sha):
        raise ContractViolation("MAP_GEOMETRY_SHA_MISMATCH",mid,
                                "Derived WGS84 geometry differs from the reviewed, pinned map geometry fingerprint.")
    frozen_record={**map_record,"geometry_object_sha256":normalized_sha}
    return {"historical_map":frozen_record,"source_original_sha256":digest,
            "coordinate_space":"EPSG:4326","features":normalized,"projected":projected,
            "geometry_sha256":normalized_sha,
            "event_year":year, "route_feature_id":route_feature_id,
            "disclosure_required":mode=="schematic_approved"}



def ingest_current_approved(store, project_id:str, requirement_id:str, map_record:dict,
                            *, year:int, feature_ids:list[str],
                            route_feature_id:str|None=None,
                            reviewed_tie_points:list[dict]|None=None) -> dict:
    """Retrieve actual G3 approval and original from the existing local SQLite/SHA store.

    Pure ingest() below is suitable for explicitly synthetic fixtures; this
    integration entry refuses a stale/foreign/unapproved asset snapshot.
    """
    from backend.app.assets.resolution import AssetResolution
    from backend.app.assets.provenance import AssetCandidates
    from backend.app.projects.gates import GateService
    story=store.get_story(project_id).data()
    requirement=next((x for x in story["asset_requirements"]
                      if x["requirement_id"]==requirement_id),None)
    if not requirement or requirement["asset_class"]!="HISTORICAL_MAP" or not (
            requirement["start_year"]<=year<=requirement["end_year"]):
        raise ContractViolation("MAP_PERIOD_MISMATCH",requirement_id,
                                "Requested year and map type must fit the current G1 authored map requirement.")
    if (requirement["map_reconstruction_policy"]=="exact_period_map"
            and map_record["geography_mode"]=="schematic_approved"):
        raise ContractViolation("MAP_POLICY_MISMATCH",requirement_id,
                                "An exact period-map request cannot silently use schematic reconstruction.")
    board=GateService(store).board(project_id)
    if board[2]["state"]!="APPROVED":
        raise ContractViolation("G3_APPROVAL_REQUIRED",requirement_id,
                                "Operator must approve the current G3 source snapshot before geographic use.")
    with store._connection() as db:
        current=AssetCandidates._source_tx(db,project_id,requirement_id)
        head=AssetResolution._head(db,project_id,requirement_id,current["requirement_sha256"])
    if not head or (head["candidate_id"]!=map_record["source_asset_id"] or
                    head["original_sha256"]!=map_record["source_original_sha256"] or
                    head["approval_record_id"]!=map_record["rights_review_record_id"]):
        raise ContractViolation("MAP_RIGHTS_UNREVIEWED",requirement_id,
                                "Map does not match current project/requirement G3 approval event and original SHA.")
    original=store.get_artifact(head["original_sha256"])
    return ingest(map_record,original,year=year,feature_ids=feature_ids,approval=head,
                  route_feature_id=route_feature_id,reviewed_tie_points=reviewed_tie_points)
