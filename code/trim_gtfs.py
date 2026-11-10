"""Stream a big GTFS zip and keep only what touches a bounding box (stop_times of stops inside it and the trips,
routes, agencies, calendars they need). Usage: python3 code/trim_gtfs.py <zip> <out_dir> lat_min lat_max lon_min lon_max"""
import sys
import zipfile
from pathlib import Path
import pandas as pd

zpath, out = sys.argv[1], Path(sys.argv[2])
la0, la1, lo0, lo1 = map(float, sys.argv[3:7])
out.mkdir(parents=True, exist_ok=True)
zf = zipfile.ZipFile(zpath)
rd = lambda name, **kw: pd.read_csv(zf.open(name), dtype=str, keep_default_na=False, **kw)

stops = rd("stops.txt")
lat, lon = stops.stop_lat.replace("", "nan").astype(float), stops.stop_lon.replace("", "nan").astype(float)
keep_stops = set(stops.loc[lat.between(la0, la1) & lon.between(lo0, lo1), "stop_id"])
print("stops in bbox:", len(keep_stops), flush=True)

parts, trip_ids, header = [], set(), True
with open(out / "stop_times.txt", "w", encoding="utf-8") as fh:
    for i, ch in enumerate(pd.read_csv(zf.open("stop_times.txt"), dtype=str, keep_default_na=False, chunksize=3_000_000,
                                       usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"])):
        ch = ch[ch.stop_id.isin(keep_stops)]
        trip_ids |= set(ch.trip_id)
        ch.to_csv(fh, index=False, header=header); header = False
        print("chunk", i, "kept trips", len(trip_ids), flush=True)

trips = pd.concat(rd("trips.txt", usecols=["route_id", "service_id", "trip_id"], chunksize=2_000_000) if False else
                  [c[c.trip_id.isin(trip_ids)] for c in pd.read_csv(zf.open("trips.txt"), dtype=str, keep_default_na=False,
                                                                    chunksize=2_000_000, usecols=["route_id", "service_id", "trip_id"])])
trips.to_csv(out / "trips.txt", index=False)
svc = set(trips.service_id)
rd("routes.txt").to_csv(out / "routes.txt", index=False)
rd("agency.txt").to_csv(out / "agency.txt", index=False)
stops.to_csv(out / "stops.txt", index=False)
cal = rd("calendar.txt"); cal[cal.service_id.isin(svc)].to_csv(out / "calendar.txt", index=False)
cd = pd.concat([c[c.service_id.isin(svc)] for c in pd.read_csv(zf.open("calendar_dates.txt"), dtype=str, keep_default_na=False, chunksize=2_000_000)])
cd.to_csv(out / "calendar_dates.txt", index=False)
print("done: trips", len(trips), "services", len(svc), flush=True)
