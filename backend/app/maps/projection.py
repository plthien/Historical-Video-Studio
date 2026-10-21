"""B1-02: deterministic offline geographic projection, never a routing service."""
from __future__ import annotations
import math
from backend.app.contracts import ContractViolation

R = 6378137.0

def to_wgs84(x: float, y: float, source_crs: str, feature_id: str) -> tuple[float,float]:
    if not all(math.isfinite(v) for v in (x,y)):
        raise ContractViolation("MAP_GEOMETRY_INVALID",feature_id,"Use finite source coordinates.")
    if source_crs == "EPSG:4326":
        lon,lat=x,y
    elif source_crs == "EPSG:3857":
        if abs(x)>math.pi*R or abs(y)>20037508.342789244:
            raise ContractViolation("MAP_GEOMETRY_INVALID",feature_id,"Mercator coordinates outside supported extent.")
        lon=math.degrees(x/R)
        lat=math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)
    else:
        raise ContractViolation("MAP_CRS_UNSUPPORTED",feature_id,
                                "Declare EPSG:4326 or EPSG:3857 source CRS; convert other CRS offline with reviewed tooling.")
    if not -180 <= lon <= 180 or not -85.051129 <= lat <= 85.051129:
        raise ContractViolation("MAP_GEOMETRY_INVALID",feature_id,
                                "Longitude/latitude or polar extent invalid; review datum and coordinate order.")
    return (round(lon,10),round(lat,10))

def project(lon:float, lat:float, projection:str) -> tuple[float,float]:
    if not (-180<=lon<=180 and -85.051129<=lat<=85.051129):
        raise ContractViolation("MAP_GEOMETRY_INVALID","projection","Invalid geographic coordinate.")
    x,y=math.radians(lon),math.radians(lat)
    if projection=="equirectangular":
        return x,y
    if projection=="mercator":
        return x,math.log(math.tan(math.pi/4+y/2))
    if projection=="equal_earth":
        # Natural Earth's Equal Earth forward polynomial, fixed WGS84 spherical datum.
        a1,a2,a3,a4=1.340264,-0.081106,0.000893,0.003796
        t=math.asin((math.sqrt(3)/2)*math.sin(y))
        t2=t*t
        den=3*(a1+3*a2*t2+7*a3*t2*t2+9*a4*t2*t2*t2)
        return (2*math.sqrt(3)*x*math.cos(t)/den,
                t*(a1+a2*t2+a3*t2*t2+a4*t2*t2*t2))
    raise ContractViolation("MAP_PROJECTION_INVALID",projection,
                            "Use the map contract's declared Mercator, Equirectangular or Equal Earth projection.")

def common_viewport(before:dict,after:dict) -> dict:
    if before["map_projection"]!=after["map_projection"]:
        raise ContractViolation("MAP_PROJECTION_MISMATCH",before["historical_map_id"],
                                "Compare dated maps in one shared projection.")
    a,b=before["geography_bbox"],after["geography_bbox"]
    bounds={"min_lon":min(a["min_lon"],b["min_lon"]),"min_lat":min(a["min_lat"],b["min_lat"]),
            "max_lon":max(a["max_lon"],b["max_lon"]),"max_lat":max(a["max_lat"],b["max_lat"])}
    if before["historical_map_id"]==after["historical_map_id"] or (
        before["valid_year_from"]==after["valid_year_from"] and before["valid_year_to"]==after["valid_year_to"]):
        raise ContractViolation("MAP_PAIR_NOT_DISTINCT",before["historical_map_id"],
                                "Compare two separately reviewed period/date identities.")
    return {"projection":before["map_projection"],"bbox":bounds,
            "map_ids":[before["historical_map_id"],after["historical_map_id"]]}
