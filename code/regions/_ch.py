"""Shared settings for the Swiss regions (national SKI+ GTFS feed, extended route types)."""
import datetime as dt
import re

DATE_RANGE = (dt.date(2026, 9, 14), dt.date(2026, 11, 27))        # autumn term, inside the 2026 timetable year
GTFS_ROOT = "sources/switzerland_gtfs"
FEEDS = {"sbb": ("SKI+ Switzerland", "auto")}
MIN_EDGE_MIN = 2            # data-driven regions keep small towns: only links under 3 min are collapsed
MIN_TRIPS_DAY = 1           # any served town stays on the map
PASSTHROUGH = True          # intermediate towns without branch or interchange are not nodes (line ends and junctions stay)
SYSTEMS = {
    "bigrail":   dict(icon="train", name="National railways", color="#d62728", dash=False, vmax=140, anchor_m=1000, rail=True),
    "localrail": dict(icon="tram",  name="Local railways", color="#2ca02c", dash=False, vmax=90,  anchor_m=1000, rail=True),
    "bus":       dict(icon="bus",   name="Regional bus", color="#1f77b4", dash=True,  vmax=80,  anchor_m=1500, rail=False),
}
_SMALL = re.compile(r"zentralbahn|aargau verkehr|\bwsb\b|wynental|suhrental|bdwm|bremgarten|triengen|rigi|pilatus|zahnrad|"
                    r"bergbahn|schmalspur|\bbls\b.*tram|\btram\b|strassenbahn", re.I)
BUS_STATION_RE = r"bahnhof|busbahnhof|bhf"


def AUTO_SYSTEM(row):
    t = int(row["route_type"])
    if t in (0, 1, 2, 12) or 100 <= t < 200 or 400 <= t < 500 or 900 <= t < 1000:
        return "rail"
    if t == 3 or 200 <= t < 300 or 700 <= t < 800:
        return "bus"
    return None                                  # ferries, cable cars, funiculars, ...


def SPLIT_RAIL(row):
    """Trams, narrow-gauge and rack/mountain railways -> 'localrail' (green); everything else (SBB, S-Bahn, RE, IC) -> 'bigrail'."""
    t = int(row.route_type)
    if t in (0, 1, 12, 116, 117) or 900 <= t < 1000:
        return "localrail"
    who = f"{getattr(row, 'agency_name', '')} {row.route_short_name} {row.route_long_name}"
    return "localrail" if _SMALL.search(who) else "bigrail"
