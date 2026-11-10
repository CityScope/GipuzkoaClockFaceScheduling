"""Region polygon, outline and municipality polygons from OpenStreetMap (Overpass) for the data-driven regions.
Writes sources/<region>_polygon.geojson, sources/<region>_boundary.geojson and sources/<region>_municipalities.geojson
(name, inside = municipality centre lies inside the region polygon). Run: python3 code/make_region_geo.py <region>"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

SRC = Path(__file__).parent.parent / "sources"
# region -> how to find its polygon in OSM. 'rel': admin relation(s) of level `level` whose name matches `names` inside the area `within`.
REGIONS = {
    "gipuzkoa": dict(within=(42.5, -3.5, 43.8, -1.2), level=6, names=r"^(Gipuzkoa|Guipúzcoa)$", margin=0.55),
    "vorarlberg": dict(within=(46.3, 9.5, 49.1, 17.2), level=4, names=r"^Vorarlberg$"),
    "aargau": dict(within=(45.8, 5.9, 47.9, 10.6), level=4, names=r"^(Kanton )?Aargau$"),
    "luzern": dict(within=(45.8, 5.9, 47.9, 10.6), level=4, names=r"^(Kanton )?Luzern$"),
    "oberoesterreich": dict(within=(46.3, 9.5, 49.1, 17.2), level=6,
                            names=r"^(Linz|Linz-Land|Wels|Wels-Land|Steyr|Steyr-Land|Eferding|Grieskirchen)$|Statutarstadt (Linz|Wels|Steyr)|Bezirk (Linz|Wels|Steyr|Eferding|Grieskirchen)"),
}


def overpass(q, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "GipuzkoaTimetables-research/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=240))
        except Exception as e:                                    # rate limits / timeouts: wait and retry
            print("overpass retry", i, e); time.sleep(15 * (i + 1))
    raise SystemExit("overpass failed")


def rel_geom(rel):
    outer, inner = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        ln = LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        (inner if m.get("role") == "inner" else outer).append(ln)
    if not outer:
        return None
    polys = list(polygonize(linemerge(MultiLineString(outer))))
    if not polys:
        return None
    g = unary_union(polys)
    if inner:
        holes = list(polygonize(linemerge(MultiLineString(inner))))
        if holes:
            g = g.difference(unary_union(holes))
    return g


STATUTORY_AT = r"^(Linz|Wels|Steyr|St\\. Pölten|Wiener Neustadt|Krems an der Donau|Waidhofen an der Ybbs|Salzburg|Graz|Innsbruck|Klagenfurt am Wörthersee|Villach)$"


def add_statutory_cities(region):
    """Austrian statutory cities are district-level (admin_level 6) in OSM and missing from the level-8 municipality
    query: add them (and Vienna, a state) to <region>_municipalities.geojson if absent."""
    p = SRC / f"{region}_municipalities.geojson"
    d = gpd.read_file(p)
    poly = gpd.read_file(SRC / f"{region}_polygon.geojson").geometry.iloc[0]
    new = []
    q = f'[out:json][timeout:200];rel["boundary"="administrative"]["admin_level"="6"]["name"~"{STATUTORY_AT}"](46.3,9.5,49.1,17.2);out geom;'
    q2 = '[out:json][timeout:120];rel["boundary"="administrative"]["admin_level"="4"]["name"="Wien"](48.0,16.1,48.4,16.7);out geom;'
    for r in overpass(q)["elements"] + overpass(q2)["elements"]:
        name = r["tags"].get("name:de") or r["tags"]["name"]
        g = rel_geom(r)
        minx, miny, maxx, maxy = d.total_bounds
        if g is None or name in set(d.name) or not (minx - 0.3 < g.centroid.x < maxx + 0.3 and miny - 0.3 < g.centroid.y < maxy + 0.3):
            continue
        new.append(dict(name=name, inside=bool(poly.contains(g.representative_point())), geometry=g.buffer(0)))
    if new:
        import pandas as pd
        d = gpd.GeoDataFrame(pd.concat([d, gpd.GeoDataFrame(new, crs=4326)], ignore_index=True), crs=4326)
        d.to_file(p, driver="GeoJSON")
    print(region, "added:", [(n["name"], n["inside"]) for n in new])


def main(region):
    cfg = REGIONS[region]
    wb = ",".join(map(str, cfg["within"]))
    q = f'[out:json][timeout:200];rel["boundary"="administrative"]["admin_level"="{cfg["level"]}"]["name"~"{cfg["names"]}"]({wb});out geom;'
    rels = [r for r in overpass(q)["elements"] if re.search(cfg["names"], r.get("tags", {}).get("name", ""))]
    print("region relations:", [r["tags"]["name"] for r in rels])
    poly = unary_union([g for g in (rel_geom(r) for r in rels) if g is not None]).buffer(0.0004).buffer(-0.0004)
    minx, miny, maxx, maxy = poly.bounds
    mg = cfg.get("margin", 0.2)
    bb = f"{miny - mg},{minx - mg},{maxy + mg},{maxx + mg}"
    q = f'[out:json][timeout:240];rel["boundary"="administrative"]["admin_level"="8"]({bb});out geom;'
    munis = []
    for r in overpass(q)["elements"]:
        g = rel_geom(r)
        if g is None:
            continue
        name = r["tags"].get("name:de") or r["tags"].get("name")
        munis.append((name, g))
    print("municipalities:", len(munis))
    rows = [dict(name=n, inside=bool(poly.contains(g.representative_point())), geometry=g.buffer(0)) for n, g in munis]
    gdf = gpd.GeoDataFrame(rows, crs=4326)
    gdf.to_file(SRC / f"{region}_municipalities.geojson", driver="GeoJSON")
    b = poly.boundary.simplify(0.0006)
    parts = [l for l in getattr(b, "geoms", [b]) if l.length > 0.05]
    gpd.GeoDataFrame({"name": [region]}, geometry=[MultiLineString(parts)], crs=4326).to_file(SRC / f"{region}_boundary.geojson", driver="GeoJSON")
    gpd.GeoDataFrame({"name": [region]}, geometry=[poly], crs=4326).to_file(SRC / f"{region}_polygon.geojson", driver="GeoJSON")
    print(region, "inside municipalities:", int(gdf.inside.sum()), "bbox", [round(x, 3) for x in poly.bounds])
    if cfg["within"][0] == 46.3:
        add_statutory_cities(region)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "cities":
        add_statutory_cities(sys.argv[1])
    else:
        main(sys.argv[1])
