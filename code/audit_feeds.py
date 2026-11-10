"""List, per feed of a region, every (route type, operator) with trips in the region's bounding box and how it is
classified (system key or DROPPED). Run: python3 code/audit_feeds.py <region>"""
import os, sys
os.environ["REGION"] = sys.argv[1]
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
import pandas as pd
import towns
import gtfs_io

real_auto, real_split = towns.AUTO_SYSTEM, towns.SPLIT_RAIL
feeds = dict(towns.FEEDS)
rows = []
for name, (label, system) in feeds.items():
    if system.startswith("auto"):
        gtfs_io.AUTO_SYSTEM = lambda r: f"{int(r['route_type'])}|{r.get('agency_name', '')}"
        gtfs_io.SPLIT_RAIL = None
        gtfs_io.FEEDS[name] = (label, "auto")
        fd = gtfs_io.load_feed(Path(towns.GTFS_ROOT), name, ("weekday",))["weekday"]
        t = fd["trips"]
        n_trips = t.groupby("mode").trip_id.nunique()
        n_in = fd["st"].merge(t[["trip_id", "mode"]], on="trip_id").groupby("mode").trip_id.nunique()
        for key, n in n_in.items():
            rt, ag = key.split("|", 1)
            r = pd.Series(dict(route_type=rt, agency_name=ag, route_short_name="", route_long_name=""))
            m = real_auto(r)
            if m == "rail" and real_split is not None:
                m = real_split(pd.Series(dict(route_type=rt, agency_name=ag, route_short_name="", route_long_name="")).to_frame().T.itertuples().__next__())
            if system == "auto:rail" and m not in towns.RAIL_SYSTEMS:
                m = f"(not used: {m} - taken from the bus feed)" if m else None
            if system == "auto:bus" and m in towns.RAIL_SYSTEMS:
                m = f"(not used: {m} - taken from the rail feed)"
            rows.append((label, rt, ag, int(n), m or "DROPPED"))
    else:
        gtfs_io.FEEDS[name] = (label, system)
        fd = gtfs_io.load_feed(Path(towns.GTFS_ROOT), name, ("weekday",)).get("weekday")
        if fd is not None:
            rows.append((label, "-", "(fixed system)", int(fd["st"].trip_id.nunique()), system))
df = pd.DataFrame(rows, columns=["feed", "route_type", "operator", "trips_in_area", "classified_as"])
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400); pd.set_option("display.max_colwidth", 48)
print(df.sort_values(["feed", "trips_in_area"], ascending=[True, False]).to_string(index=False))
