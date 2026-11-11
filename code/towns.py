"""Generic parameters + region loader. The region is chosen with the REGION environment variable
(set by run_analysis.py from its first argument, default gipuzkoa); region modules live in code/regions/."""
import pandas as _pd
try:                                    # pandas 3: plain Python strings (Arrow strings are much slower element by element)
    _pd.set_option("future.infer_string", False)
except Exception:
    pass

import importlib
import os
import pathlib as _pl

_R = importlib.import_module("regions." + os.environ.get("REGION", "gipuzkoa"))
for _k, _v in vars(_R).items():
    if _k.isupper():
        globals()[_k] = _v

SPLIT_RAIL = globals().get("SPLIT_RAIL")   # optional: region function (route speed, route row) -> system key

import json as _json
import pathlib as _pl
_pf = _pl.Path(__file__).parent.parent / "sources" / "population" / f"{NAME}_population.json"
POPULATION = _json.load(open(_pf))["population"] if _pf.exists() else None     # see code/make_population.py
POLYGON_FILE = f"sources/{NAME}_polygon.geojson"                                # province polygon (veh-km are counted inside it)

# optional region settings (defaults for regions that do not define them)
for _k, _v in dict(PREFIX_FEED=None, MUNI_ALIAS={}, PREFIX_MAX_M=5000, EXEMPT_SHORT=set(), GEOM_FIRST=set(), DISPLAY={},
                   ANCHOR_HINT={}, KEEP_ALWAYS=set(), EXTERNAL=set(), PASSTHROUGH=True, TOWNS={}, BUS_STATION_RE=r"bahnhof|bus station|geltokia").items():
    globals().setdefault(_k, _v)

# data-driven regions: every stop belongs to the municipality polygon it lies in (see make_region_geo.py)
MUNI_FILE = globals().get("MUNI_FILE")
EXTERNAL_MIN_DEPS = globals().get("EXTERNAL_MIN_DEPS", 150)   # outside municipalities become nodes only with at least this many departures/day
PRIORITY = globals().get("PRIORITY", [])
if MUNI_FILE:
    import geopandas as _gpd
    _m = _gpd.read_file(_pl.Path(__file__).parent.parent / MUNI_FILE)
    _m = _m.dropna(subset=["name"]).drop_duplicates("name")
    TOWNS = {r.name: (r.geometry.representative_point().y, r.geometry.representative_point().x, 0) for r in _m.itertuples()}
    EXTERNAL = set(_m.loc[~_m.inside, "name"])
    KEEP_ALWAYS = set(EXTERNAL)
    MUNI_POLYS = _m[["name", "geometry"]]

# derived per-system tables
SYS_NAME = {k: v["name"] for k, v in SYSTEMS.items()}
VMAX_KMH = {k: v["vmax"] for k, v in SYSTEMS.items()}          # straight-line speed cap; faster legs are discarded
MAX_ANCHOR_M = {k: v["anchor_m"] for k, v in SYSTEMS.items()}  # a stop counts as a visit within this distance of the station
RAIL_SYSTEMS = {k for k, v in SYSTEMS.items() if v["rail"]}

MIN_EDGE_MIN = globals().get("MIN_EDGE_MIN", 9)   # no transit edge shorter than this (user requirement; a region may override)
MIN_TRIPS_DAY = globals().get("MIN_TRIPS_DAY", 3)   # ignore ghost links with fewer trips/day
WALK_M_PER_MIN = 75   # walking links between nodes of the same town
WALK_MAX_MIN = 5      # walking transfer only up to 5 min (about 375 m); more is too much for a connection
ONEWAY_DETOUR = (1.4, 4.0)   # a one-way link is routed along the return corridor if that path takes <= 1.4 x its time + 4 min
ONEWAY_DROP_MAX = 3          # one-way legs with at most this many trips/day and no return corridor are exceptional: dropped

# Time bands (minutes after midnight of the service day). Limits are WHOLE HOURS on purpose: the headway formula
# (g0^2 + sum gaps^2)/window is distorted by the window edges unless the window length is a multiple of the
# service interval, so a band of 3.5 h turns an hourly service into ~70 min. Whole-hour bands keep 60/30/20/15-min
# services exact whatever their phase. Times before DAY_START_MIN belong to the night tail (+24 h).
PERIODS = {
    "peak":  [(7 * 60, 9 * 60), (17 * 60, 19 * 60)],     # 07:00-09:00 and 17:00-19:00
    "day":   [(9 * 60, 17 * 60)],                        # 09:00-17:00   (06-07 and 19-22 belong to no band)
    "night": [(22 * 60, 30 * 60)],                       # 22:00-06:00
}
DAY_START_MIN = 6 * 60

# --- how connections are established -------------------------------------------------------------------
# 1. a trip VISITS a node if it stops within MAX_ANCHOR_M[system] of the node's station (time = that stop's time)
# 2. a connection joins two consecutive visited nodes of the same system on a trip
# 3. legs much slower than the same route's usual time on that pair are loops/detours and are discarded
LEG_OUTLIER = (2.0, 10.0)      # discard leg if tt > 2.0*route-pair median + 10 min
# 4. a direct link A-C past a node B exists whenever at least MIN_TRIPS_DAY services skip B (express);
#    if every service stops at B there is no A-C link, only A-B and B-C

# 5. pass-through nodes are removed: a node with <= 2 neighbours (same system), no other-system node of the same
#    town to change to, and (almost) no service starting/ending there adds nothing -> its neighbours link directly
TERMINUS_SHARE = 0.10          # share of the node's trips that start/end there above which it counts as a terminus


# --- merged nodes and symmetry minutes -----------------------------------------------------------------
MERGE_WALK_MIN = 2             # nodes of the same town with different systems are ONE node only if the walk between them is <= 2 min
SYM_WINDOW_MIN = 6             # symmetry node: arrivals up to 6 min before minute s, departures up to 6 min after it
SYM_MIN_SHARE = 0.33           # ... for at least 33% of the arrivals AND of the departures (06:00-22:00; rail events when the node has a station)
SYM_BUS_MIN_SHARE, SYM_BUS_MIN_LINES = 0.5, 3   # bus-only nodes need a stronger pattern (few lines line up by chance)
SYM_MIN_LINES = 2              # ... and at least 2 distinct lines meet in the arrival window and in the departure window
SYM_MIN_EVENTS = 10            # and at least 10 arrivals and 10 departures that day
SYM_PERIOD30_RATIO = 0.6       # pattern also holds at s+30 (>= 60% as strong) -> 30-minute symmetry (diameter line)

STATION_RADIUS_M = 500        # a town's bus node is anchored at its best-served bus stop within this distance of the train station (if no bus station)

# --- coordination (code/coordination.py)
SYM_MIN_EVENTS_BAND = 6        # arrivals and departures needed inside a band to look for a symmetry pattern
SNAP_MIN = 1                   # symmetry minute snaps to a multiple of 5 only if one lies within 1 min of the exact minute and the pattern stays valid; otherwise the exact minute is kept
TRANSFER_MAX_WAIT = 30         # transfers shown with a wait under 30 min ...
REVERSAL_MAX_WAIT = 60         # ... and vehicles that reverse (same line back) up to 60 min
CHANGE_PENALTY_MIN = 2         # +2 min whenever the mode or the station changes
COORD_WAIT_SHARE = 0.25        # a connection is coordinated only if its wait <= 25% of how often it repeats
COORD_BEST_HEADWAY_MIN = 15    # a connection is only shown if even the BETTER of the two lines runs every 15 min or less often (otherwise no coordination is needed)
SHORT_LINK_MIN = 10              # links shorter than this are kept only if both stations take part in timed connections
DROP_REDUNDANT = True           # remove branching stations whose every line pair also meets at another node
FS_MIN_STOPS = 2                # fast / slow split of a link: the slow group makes >= 2 more stops ...
FS_MIN_MIN = 6.0                # ... and takes >= 6 min more; headways within a factor 2; each group >= FS_MIN_TRIPS trips a day
FS_MIN_TRIPS = 6
FAR_VISIT_M = 8000              # a trip through a municipality counts as serving it if a stop is within this of the node (drawn only)
REGIONAL_BUS_MIN_TOWNS = 3      # a bus line is regional (may create nodes) if it serves >= 3 municipalities ...
REGIONAL_BUS_MIN_KM = 10.0      # ... and one of its trips is >= 10 km long (straight-line sum between stops)
SAME_ROUTE_JACCARD = 0.8        # routes sharing >= 80 % of their stops (by position) are one line, whatever their names
MINOR_BUS_MIN_TOWNS = 2         # other bus lines (>= 2 municipalities) only add links / trips between existing nodes; town buses are out
FREQUENT_MIN = 15               # frequent = headway below 15 min; exactly every 15 min is NOT frequent
FREQ_CUT = FREQUENT_MIN         # frequent = headway just under 15 min (< 15); exactly 15 min is not
SYM_WINDOW_BUS_ARR = 12         # buses typically arrive earlier (delay buffer): a bus arrival may be up to 12 min before the symmetry minute (rail: SYM_WINDOW_MIN)


# population of every municipality (code/make_muni_population.py): importance of a town
try:
    import json as _json2
    MUNI_POP = _json2.load(open(_pl.Path(__file__).parent.parent / "sources" / "population" / f"{NAME}_municipalities_pop.json"))
except Exception:
    MUNI_POP = {}
