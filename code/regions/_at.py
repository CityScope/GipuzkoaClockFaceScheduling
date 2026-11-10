"""Shared settings for the Austrian data-driven regions (rail feed + one Verkehrsverbund bus feed)."""
import datetime as dt
import re

DATE_RANGE = (dt.date(2026, 9, 14), dt.date(2026, 11, 27))
GTFS_ROOT = "sources/austria_gtfs"
MIN_EDGE_MIN = 2
MIN_TRIPS_DAY = 1           # any served town stays on the map
PASSTHROUGH = True          # intermediate towns without branch or interchange are not nodes (line ends and junctions stay)
SYSTEMS = {
    "bigrail":   dict(icon="train", name="National railways", color="#d62728", dash=False, vmax=140, anchor_m=1000, rail=True),
    "localrail": dict(icon="tram",  name="Local railways", color="#2ca02c", dash=False, vmax=80,  anchor_m=1000, rail=True),
    "bus":       dict(icon="bus",   name="Regional bus", color="#1f77b4", dash=True,  vmax=80,  anchor_m=1500, rail=False),
}
_URBAN = re.compile(r"wiener linien", re.I)      # Vienna's internal network only; every other local/town bus is kept (links between municipalities)
_SMALL = re.compile(r"stern\s*&?\s*hafferl|traunsee|attergau|lokalbahn|p\u00f6stlingberg|schmalspur|zahnrad|mariazell|schneeberg|wachau|"
                    r"citybahn|taurach|montafon|zillertal|achensee|pinzgau|stubaital|badner|n\u00f6vog|schafberg", re.I)
BUS_STATION_RE = r"bahnhof|busbahnhof|hbf|bf\b"


def AUTO_SYSTEM(row):
    t = int(row["route_type"])
    if _URBAN.search(str(row.get("agency_name", ""))):
        return None
    if t in (0, 1, 2, 12) or 100 <= t < 200 or 400 <= t < 500:
        return "rail"
    if t == 3 or 200 <= t < 300 or 700 <= t < 800:
        return "bus"
    return None


def SPLIT_RAIL(row):
    """Mainline trains incl. S-Bahn -> 'bigrail' (red); trams, rack and narrow-gauge/small railways -> 'localrail' (green)."""
    t = int(row.route_type)
    if t in (0, 1, 12, 116, 117, 400, 401, 402, 403, 404, 405):
        return "localrail"
    who = f"{getattr(row, 'agency_name', '')} {row.route_short_name} {row.route_long_name}"
    return "localrail" if _SMALL.search(who) else "bigrail"
