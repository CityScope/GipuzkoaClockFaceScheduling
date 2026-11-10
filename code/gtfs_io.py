"""GTFS loading for the takt analysis (pandas only, chunked for big feeds)."""
from __future__ import annotations
from pathlib import Path
import datetime as dt
import pandas as pd

import numpy as np
from towns import FEEDS, BBOX, DATE_RANGE, AUTO_SYSTEM, SPLIT_RAIL, RAIL_SYSTEMS


def _read(path: Path, **kw) -> pd.DataFrame:
    """Read a GTFS text file with polars (multi-threaded), all columns as trimmed plain strings."""
    if not path.exists():
        return pd.DataFrame()
    import polars as pl
    df = pl.read_csv(path, infer_schema=False, encoding="utf8-lossy")
    df = df.rename({c: c.strip().lstrip("\ufeff") for c in df.columns})
    df = df.with_columns([pl.col(c).str.strip_chars().fill_null("") for c in df.columns])
    out = df.to_pandas(use_pyarrow_extension_array=False)
    return out.astype(object) if len(out.columns) else out


def parse_time(s: pd.Series) -> pd.Series:
    p = s.str.split(":", expand=True)
    return pd.to_numeric(p[0]) * 60 + pd.to_numeric(p[1]) + pd.to_numeric(p[2]) / 60


def active_services(cal, cd, date: dt.date) -> set[str]:
    ds, wd = date.strftime("%Y%m%d"), date.strftime("%A").lower()
    on = set()
    if len(cal):
        m = (cal.start_date <= ds) & (cal.end_date >= ds) & (cal[wd] == "1")
        on = set(cal.loc[m, "service_id"])
    if len(cd):
        x = cd[cd.date == ds]
        on |= set(x.loc[x.exception_type == "1", "service_id"])
        on -= set(x.loc[x.exception_type == "2", "service_id"])
    return on


DAYTYPES = {"weekday": (1, 2, 3), "saturday": (5,), "sunday": (6,)}   # Tue-Thu / Sat / Sun


def pick_date(cal, cd, trips, wdays, lo=None, hi=None) -> dt.date:
    lo, hi = (DATE_RANGE if DATE_RANGE else (None, None))
    """Typical date of a day type: the date (with weekday in `wdays`) with the most active trips in the feed."""
    cnt = trips.service_id.value_counts()
    ps = lambda x: dt.datetime.strptime(x, "%Y%m%d").date()
    fs = [ps(x) for x in cal.start_date] if len(cal) else [lo or dt.date(2026, 1, 1)]
    fe = [ps(x) for x in cal.end_date] if len(cal) else [hi or dt.date(2026, 12, 31)]
    a, b = (max(lo, min(fs)), min(hi, max(fe))) if lo else (min(fs), max(fe))
    if a > b:
        a, b = min(fs), max(fe)
    best, bn, day = a, -1, a
    while day <= b:
        if day.weekday() in wdays:
            n = sum(cnt.get(s, 0) for s in active_services(cal, cd, day))
            if n > bn:
                best, bn = day, n
        day += dt.timedelta(days=1)
    return best


def load_feed(root: Path, name: str, daytypes=("weekday",)) -> dict:
    """Cached wrapper of _load_feed: the parsed feed is stored in sources/cache/ (pickle) and reused while the GTFS files,
    this module and the region settings are unchanged (parsing the big national feeds takes most of the run time)."""
    import hashlib, pickle, sys as _sys
    d = Path(root) / name
    if not d.exists():
        return {}
    import towns as _t
    regf = Path(__file__).parent / "regions" / f"{_t.NAME}.py"
    ALL = tuple(DAYTYPES)                                    # the cache always holds every day type (superset)
    sig = [str(ALL), str(getattr(_t, "DATE_RANGE", "")), _t.NAME]
    for f in sorted(d.glob("*.txt")) + [Path(__file__), regf, Path(__file__).parent / "regions" / "_ch.py", Path(__file__).parent / "regions" / "_at.py"]:
        if f.exists():
            st_ = f.stat(); sig.append(f"{f.name}:{st_.st_size}:{int(st_.st_mtime)}")
    key = hashlib.md5("|".join(sig).encode()).hexdigest()[:16]
    cache = Path(__file__).parent.parent / "sources" / "cache" / f"{_t.NAME}_{name}_{key}.pkl"
    if cache.exists():
        with open(cache, "rb") as fh:
            res = pickle.load(fh)
        return {k: v for k, v in res.items() if k in daytypes}
    res = _load_feed(root, name, ALL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    for old in cache.parent.glob(f"{_t.NAME}_{name}_*.pkl"):
        old.unlink()
    with open(cache, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return {k: v for k, v in res.items() if k in daytypes}


def _load_feed(root: Path, name: str, daytypes=("weekday",)) -> dict:
    """Returns {daytype: feed dict} (stop_times are read once for all day types)."""
    d = root / name
    if not d.exists():
        return {}
    label, system = FEEDS[name]
    cal, cd = _read(d / "calendar.txt"), _read(d / "calendar_dates.txt")
    trips_all = _read(d / "trips.txt")
    routes = _read(d / "routes.txt")
    if system in ("auto", "auto:rail", "auto:bus"):       # one feed, several modes/operators: classify each route (see region AUTO_SYSTEM)
        ag = _read(d / "agency.txt")
        amap = dict(zip(ag.agency_id, ag.agency_name)) if len(ag) and "agency_id" in ag else {}
        dflt = ag.agency_name.iloc[0] if len(ag) else ""
        routes["agency_name"] = routes.agency_id.map(amap).fillna(dflt) if "agency_id" in routes else dflt
        routes["mode"] = routes.apply(AUTO_SYSTEM, axis=1)
        routes = routes.dropna(subset=["mode"])
        if SPLIT_RAIL is not None:                # trains: split into mainline vs small/narrow-gauge/mountain systems
            routes["mode"] = [SPLIT_RAIL(r) if r.mode == "rail" else r.mode for r in routes.itertuples()]
            routes = routes.dropna(subset=["mode"])
        if system == "auto:rail":                 # take only the trains of this feed (its buses are in the bus feed)
            routes = routes[routes["mode"].isin(RAIL_SYSTEMS)]
        if system == "auto:bus":                  # only the buses of this feed (its trains come from the rail feed)
            routes = routes[~routes["mode"].isin(RAIL_SYSTEMS)]
    else:
        routes["mode"] = system
    stops = _read(d / "stops.txt")
    stops["stop_lat"], stops["stop_lon"] = stops.stop_lat.astype(float), stops.stop_lon.astype(float)
    inb = stops[stops.stop_lat.between(BBOX["lat_min"], BBOX["lat_max"]) &
                stops.stop_lon.between(BBOX["lon_min"], BBOX["lon_max"])]
    sel = {}
    for dtp in daytypes:
        date = pick_date(cal, cd, trips_all, DAYTYPES[dtp])
        tr = trips_all[trips_all.service_id.isin(active_services(cal, cd, date))]
        sel[dtp] = (date, tr)
    tset = set().union(*[set(tr.trip_id) for _, tr in sel.values()])
    sset = set(inb.stop_id)
    # stop_times with polars (lazy, multi-threaded): read only 5 columns, keep the selected trips and the stops in the
    # area, parse HH:MM:SS to minutes and sort, then hand a small table to pandas
    import polars as pl
    cols = ["trip_id", "stop_id", "arrival_time", "departure_time", "stop_sequence"]
    lf = pl.scan_csv(d / "stop_times.txt", infer_schema=False, encoding="utf8-lossy")
    lf = lf.rename({c: c.strip() for c in lf.collect_schema().names()}).select(cols)
    lf = lf.with_columns([pl.col(c).str.strip_chars() for c in cols])
    lf = lf.filter(pl.col("trip_id").is_in(list(tset)) & pl.col("stop_id").is_in(list(sset))
                   & (pl.col("arrival_time") != "") & (pl.col("departure_time") != ""))
    tm = lambda c: (pl.col(c).str.split(":").list.get(0).cast(pl.Float64) * 60 + pl.col(c).str.split(":").list.get(1).cast(pl.Float64)
                    + pl.col(c).str.split(":").list.get(2).cast(pl.Float64) / 60)
    lf = lf.with_columns(pl.col("stop_sequence").cast(pl.Int64), tm("arrival_time").alias("arr"), tm("departure_time").alias("dep"))
    st_all = lf.sort(["trip_id", "stop_sequence"]).collect().to_pandas(use_pyarrow_extension_array=False)
    for c in ("trip_id", "stop_id", "arrival_time", "departure_time"):
        st_all[c] = st_all[c].astype(object)
    out = {}
    for dtp, (date, tr) in sel.items():
        if "agency_id" not in routes:
            routes["agency_id"] = ""
        tr = tr.merge(routes[["route_id", "route_short_name", "route_long_name", "mode", "agency_id"]], on="route_id")
        out[dtp] = dict(label=label, date=date, trips=tr, stops=inb,
                        st=st_all[st_all.trip_id.isin(set(tr.trip_id))], name=name)
    return out
