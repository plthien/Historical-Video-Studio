# Historical Map Engine — V1 Data and Projection Contract
## Selected representation
- Normalize vector geometry at ingest to GeoJSON EPSG:4326 with (lon,lat) ordering, retaining original source CRS and immutable bytes.
- HistoricalMap.v1 records source asset hash, period year span, reviewed geometry hash, approved feature IDs, bbox, projection and rights evidence.
- Renderer uses a pinned projection (Mercator default; Equirectangular/Equal Earth alternatives), same projection and viewport for T07 before/after comparisons. Use Python pyproj/Shapely for offline conversion/topology and pinned JavaScript d3-geo or equivalent at frame compilation, not live map tile requests.
- Raster map may use georeferenced tie points explicitly verified by reviewer; otherwise labels anchored in image UV and must not be treated as geographic coordinates. No automatic conversion from raster pixels to lon/lat.
- Routes are reviewed ordered GeoJSON LineStrings from period evidence or visibly labeled schematics approved at G3. Never use present-day roads as factual historic itineraries.
- Missing period boundary source blocks compilation; do not substitute modern national polygons even if map visually seems similar.
- Label disputed or approximate border status. Date coverage must contain the narration event year before feature layer drawn.

## Projection pipeline
Source geometry and metadata → validate period/source rights/relevance → convert validated source CRS to WGS84 → validate lon/lat order, topology and geo bbox → snapshot local bytes SHA → choose frozen projection and view window → convert each geo coordinate into pixels within approved map layer rect → apply camera transform to rendered layer only. Pan/zoom must keep requested marker within critical safe area; labels avoid collision.

## Exceptions
Antimeridian, polar regions, questionable period map, mixed projection and incomplete topology return typed MAP_GEOMETRY_INVALID or MAP_PERIOD_MISMATCH and operator review; no silent correction that changes evidence.
