"""Which services (routes with trips inside the area) appear on the map and which do not.
Needs output/<region>/results.pkl. Run: python3 code/audit_services.py <region>"""
import os, pickle, sys
os.environ["REGION"] = sys.argv[1]
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
import numpy as np
import pandas as pd
import towns
from gtfs_io import FEEDS, load_feed

R = Path(__file__).parent.parent
res = pickle.load(open(R / "output" / sys.argv[1] / "results.pkl", "rb"))["weekday"]
import json
from shapely.geometry import shape
import shapely
poly = shape(json.load(open(R / towns.POLYGON_FILE))["features"][0]["geometry"])
shown = set(res["legs"].route_key)
alias = res.get("alias", {})                       # routes merged by stop pattern
rows = []
for name in FEEDS:
    fd = load_feed(R / towns.GTFS_ROOT, name, ("weekday",)).get("weekday")
    if fd is None or fd["st"].empty:
        continue
    sp = fd["stops"][["stop_id", "stop_lat", "stop_lon"]].copy()
    sp["inside"] = shapely.contains_xy(poly, sp.stop_lon.values, sp.stop_lat.values)
    import geopandas as gpd
    pts = gpd.GeoDataFrame({"stop_id": sp.stop_id.values}, geometry=gpd.points_from_xy(sp.stop_lon, sp.stop_lat), crs=4326)
    sp["muni"] = sp.stop_id.map(gpd.sjoin(pts, towns.MUNI_POLYS, how="left", predicate="within").drop_duplicates("stop_id").set_index("stop_id")["name"])
    t = fd["st"].merge(sp[["stop_id", "inside", "muni", "stop_lat", "stop_lon"]], on="stop_id").merge(fd["trips"][["trip_id", "route_short_name", "mode", "agency_id"]], on="trip_id")
    t = t.merge(fd["trips"][["trip_id", "route_id"]], on="trip_id")
    t["route_short_name"] = t.route_short_name.astype(str) + "@" + t.route_id.astype(str)   # = analysis route key
    # regional-bus rule (same as the analysis): bus routes need >= 3 municipalities and a trip of >= 8 km
    from analysis import _m
    a = t.sort_values(["trip_id", "stop_sequence"])
    same = a.trip_id.values[1:] == a.trip_id.values[:-1]
    a["d"] = np.concatenate([[0.0], np.where(same, _m(a.stop_lat.values[1:], a.stop_lon.values[1:], a.stop_lat.values[:-1], a.stop_lon.values[:-1]), 0.0)])
    km = a.groupby(["route_short_name", "trip_id"]).d.sum().groupby("route_short_name").max() / 1000
    nm = a.groupby("route_short_name").muni.nunique()
    isbus = a.groupby("route_short_name")["mode"].first() == "bus"
    rule_ok = ~isbus | ((nm >= towns.REGIONAL_BUS_MIN_TOWNS) & (km >= towns.REGIONAL_BUS_MIN_KM))   # must be on the map
    other_ok = isbus & ~rule_ok & (nm >= getattr(towns, "MINOR_BUS_MIN_TOWNS", 2))                   # only between existing nodes
    t = t[t.inside]                                   # only stops inside the region
    t["route_key"] = fd["label"] + ":" + t.route_short_name
    g = t.groupby("route_key").agg(trips=("trip_id", "nunique"), stops=("stop_id", "nunique"), munis=("muni", "nunique"))
    g = g[g.munis >= 2]                              # a service must touch at least two municipalities to give a link
    g["feed"] = fd["label"]
    g["regional"] = g.index.map(lambda k: bool(rule_ok.get(k.split(":", 1)[1], True)))
    g["other"] = g.index.map(lambda k: bool(other_ok.get(k.split(":", 1)[1], False)))
    rows.append(g.reset_index())
df = pd.concat(rows)
df["on_map"] = df.route_key.map(lambda k: alias.get(k, k)).isin(shown)
df["regional"] = df.regional.fillna(True).astype(bool)
df["other"] = df.get("other", False)
_o = df[df.other.fillna(False).astype(bool)]
print(f"other bus lines (only between existing nodes): {len(_o)}, used on the map: {int(_o.route_key.map(lambda k: alias.get(k, k)).isin(shown).sum())}")
print(f"local bus routes excluded by the regional-bus rule: {int((~df.regional).sum())}")
df = df[df.regional]
print(f"routes with trips in the area: {len(df)}, on the map: {int(df.on_map.sum())}, missing: {int((~df.on_map).sum())}")
print("trips/day of missing routes:", int(df[~df.on_map].trips.sum()), "of", int(df.trips.sum()))
print(df[~df.on_map].groupby("feed").agg(routes=("route_key", "size"), trips=("trips", "sum")).to_string())
pd.set_option("display.width", 200)
print(df[~df.on_map].sort_values("trips", ascending=False).head(12).to_string(index=False))
df.to_csv(R / "output" / sys.argv[1] / "services_audit.csv", index=False)
