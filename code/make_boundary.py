"""Province polygon + outline for a region (used by the map and by the veh-km / population calculations).
Writes sources/<region>_boundary.geojson (outline lines) and sources/<region>_polygon.geojson (polygon).
Gipuzkoa: dissolved municipalities of sources/gipuzkoa_aoi.gpkg. Vorarlberg: OSM (Nominatim) polygon.
Run: python3 code/make_boundary.py gipuzkoa|vorarlberg"""
import json
import sys
import urllib.request
from pathlib import Path
import geopandas as gpd
from shapely.geometry import MultiLineString, shape

SRC = Path(__file__).parent.parent / "sources"
region = sys.argv[1] if len(sys.argv) > 1 else "gipuzkoa"
if region == "gipuzkoa":
    g = gpd.read_file(SRC / "gipuzkoa_aoi.gpkg").to_crs(4326)
    poly = g.geometry.buffer(0.0003).union_all().buffer(-0.0003)      # close slivers between municipalities
else:
    req = urllib.request.Request("https://nominatim.openstreetmap.org/search?q=Vorarlberg,+Austria&format=geojson&polygon_geojson=1&limit=1&featuretype=state",
                                 headers={"User-Agent": "GipuzkoaTimetables-research/1.0"})
    poly = shape(json.load(urllib.request.urlopen(req))["features"][0]["geometry"])
b = poly.boundary.simplify(0.0004)
parts = [l for l in getattr(b, "geoms", [b]) if l.length > 0.05]      # drop tiny slivers
gpd.GeoDataFrame({"name": [region]}, geometry=[MultiLineString(parts)], crs=4326).to_file(SRC / f"{region}_boundary.geojson", driver="GeoJSON")
gpd.GeoDataFrame({"name": [region]}, geometry=[poly], crs=4326).to_file(SRC / f"{region}_polygon.geojson", driver="GeoJSON")
print(region, "boundary parts:", len(parts), "polygon area (deg2):", round(poly.area, 4))
