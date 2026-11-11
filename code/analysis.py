"""Station-level nodes (town x system), edges >= 9 min, takt statistics, network travel times."""
from __future__ import annotations
import heapq
import re
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from towns import WALK_MAX_MIN, PASSTHROUGH, MUNI_FILE, EXTERNAL_MIN_DEPS, STATION_RADIUS_M, POLYGON_FILE, TOWNS, BUS_STATION_RE, RAIL_SYSTEMS, PREFIX_FEED, MERGE_WALK_MIN, WALK_M_PER_MIN, SYM_WINDOW_MIN, SYM_MIN_SHARE, SYM_MIN_LINES, SYM_BUS_MIN_SHARE, SYM_BUS_MIN_LINES, SYM_MIN_EVENTS, SYM_PERIOD30_RATIO, SYS_NAME, MIN_EDGE_MIN, MIN_TRIPS_DAY, WALK_M_PER_MIN, PRIORITY, ANCHOR_HINT, EXTERNAL, MUNI_ALIAS, PREFIX_MAX_M, EXEMPT_SHORT, GEOM_FIRST, DISPLAY, PERIODS, DAY_START_MIN, MAX_ANCHOR_M, VMAX_KMH, LEG_OUTLIER, TERMINUS_SHARE, KEEP_ALWAYS, REGIONAL_BUS_MIN_TOWNS, REGIONAL_BUS_MIN_KM, MINOR_BUS_MIN_TOWNS, SAME_ROUTE_JACCARD, FAR_VISIT_M, FS_MIN_STOPS, FS_MIN_MIN, FS_MIN_TRIPS, DROP_REDUNDANT, MUNI_POP, ONEWAY_DETOUR, ONEWAY_DROP_MAX

LAT0 = np.radians(43.2)


def _m(lat1, lon1, lat2, lon2):
    return np.hypot((lon1 - lon2) * 111320 * np.cos(LAT0), (lat1 - lat2) * 110540)


def _edges(st, keep, block_towns=None, pos=None, clean=False):
    """Consecutive visits of nodes in `keep`; returns per directed pair stats (vectorised).
    With `block_towns`, a visit to ANY node of those towns (whatever its system) also counts as a
    stop in between, so no direct link is made past it."""
    if block_towns is None:
        s = st[st.node.isin(keep)]
    else:
        s = st[st.node.str.split("|").str[0].isin(block_towns)]
    nxt = s.groupby("trip_key")
    e = s.assign(b=nxt.node.shift(-1), b_arr=nxt.arr.shift(-1), **({"b_k": nxt.k.shift(-1)} if "k" in s else {}),
                 **({"b_far": nxt.far.shift(-1)} if "far" in s else {})).dropna(subset=["b"])
    if block_towns is not None:
        e = e[e.node.isin(keep) & e.b.isin(keep)]
    e = e[e.node != e.b].copy()
    e["tt"] = e.b_arr - e.dep
    e = e[e.tt > 0].rename(columns={"node": "a"})
    if pos is not None and len(e):      # physical plausibility: straight-line speed must not exceed VMAX
        km = _m(pos.lat.reindex(e.a).values, pos.lon.reindex(e.a).values,
                pos.lat.reindex(e.b).values, pos.lon.reindex(e.b).values) / 1000
        vmax = e["mode"].map(VMAX_KMH).fillna(100).values
        # a far visit (stop far from the station, e.g. at the other end of the municipality) has no station position:
        # its speed cannot be checked against the station positions
        farv = (e["far"].fillna(False).astype(bool).values | e["b_far"].fillna(False).astype(bool).values) if "far" in e and "b_far" in e else np.zeros(len(e), bool)
        e = e[((km / (e.tt.values / 60)) <= vmax) | farv]
    if clean and len(e):                # loops / detours: much slower than the usual time of that route on that pair
        med = e.groupby(["route_key", "a", "b"]).tt.transform("median")
        e = e[e.tt <= LEG_OUTLIER[0] * med + LEG_OUTLIER[1]]
    return e


def headway_window(d, windows):
    """Headway (min) of departures `d` (minutes) in a band made of several windows.
    Copy of pyGTFSHandler `get_headway_at_stops`: per window (g0^2 + sum gaps^2) with g0 = (first-start)+(end-last)
    (the wrap-around gap), summed over windows and divided by the total length. A window without departures
    counts as one gap as long as the window. Returns NaN when there is no departure at all."""
    num = tot = 0.0; n = 0
    for s, e in windows:
        x = d[(d >= s) & (d < e)]
        tot += e - s
        if len(x) == 0:
            num += (e - s) ** 2; continue
        n += len(x)
        num += ((x[0] - s) + (e - x[-1])) ** 2 + float(np.sum(np.diff(x) ** 2))
    return (num / tot if n else np.nan), n


def in_band(t, wins):
    """Boolean mask: departure times t (minutes, may exceed 1440; times before DAY_START_MIN belong to the night tail)."""
    t = np.where(t < DAY_START_MIN, t + 1440, t)
    return np.any([(t >= s) & (t < e) for s, e in wins], axis=0)


def main_minutes(m, min_count=2, nmax=6):
    """Main departure minutes of the hour for a set of departures (minute-of-hour values): peaks of the circular
    histogram (+-1 min smoothing), each at least half of the strongest and >= min_count departures, >= 4 min apart.
    Returns (list of minutes, interval, share): interval = spacing in minutes when evenly spaced (60 = hourly, 0 = irregular),
    share = share of departures within +-2 min of a main minute."""
    m = np.asarray(m).round().astype(int) % 60
    if len(m) == 0:
        return [], 0, 0.0
    if len(m) < 6:
        min_count = 1                                      # very few departures: list each recurring/any minute
    c = np.bincount(m, minlength=60).astype(float)
    c3 = np.convolve(np.r_[c[-1:], c, c[:1]], np.ones(3), "valid")
    thr = max(0.5 * c3.max(), min_count)
    picked = []
    for sm in np.argsort(-c3):
        if c3[sm] < thr or len(picked) >= nmax:
            break
        if all(min((sm - q) % 60, (q - sm) % 60) >= 4 for q in picked):
            picked.append(int(sm))
    picked.sort()
    if not picked:
        return [], 0, 0.0
    cover = np.zeros(60, bool)
    for q in picked:
        for dlt in range(-2, 3):
            cover[(q + dlt) % 60] = True
    interval = 60 if (len(picked) == 1 and len(m) >= 3) else 0
    if len(picked) > 1:
        gaps = np.diff(picked + [picked[0] + 60])
        if gaps.max() - gaps.min() <= 3:
            interval = int(round(gaps.mean()))
    return picked, interval, float(c[cover].sum() / len(m))


def edge_minutes(e, und):
    """All distinct departure minutes of the hour per connection, band and direction (columns mn_<band>_ab / _ba,
    'm1,m2,...'; ab = from und.a to und.b)."""
    grp = {k: g.dep.values for k, g in e.groupby(["a", "b", "mode"])}
    out = {}
    for per, wins in PERIODS.items():
        for suf, flip in (("ab", False), ("ba", True)):
            col = []
            for r in und.itertuples():
                a_, b_ = (r.b, r.a) if flip else (r.a, r.b)
                d = grp.get((a_, b_, r.mode), np.array([]))
                d = d[in_band(d, wins)] if len(d) else d
                col.append(",".join(map(str, sorted({int(round(x)) % 60 for x in d}))))
            out[f"mn_{per}_{suf}"] = col
    return pd.DataFrame(out, index=und.index)


def longest_wait(d, windows):
    """Longest wait (min) for one direction in a band: the biggest gap between consecutive departures. As in the
    headway formula the band is treated as repeating, so the wait across the band edge (last departure -> end,
    start -> first departure) counts as ONE gap; a window without any departure counts as its whole length.
    NaN if there is no departure at all. (Consequently longest wait >= headway.)"""
    mx, any_ = 0.0, False
    for s, e in windows:
        x = np.sort(d[(d >= s) & (d < e)])
        if len(x) == 0:
            mx = max(mx, e - s); continue
        any_ = True
        mx = max(mx, (x[0] - s) + (e - x[-1]), float(np.max(np.diff(x))) if len(x) > 1 else 0.0)
    return mx if any_ else np.nan


def period_headways(e):
    """Directed trips `e` (cols a,b,u,mode,route_key,dep) -> DataFrame indexed by key 'a||b' (undirected)
    with hw_<period> (best direction; routes combined as 1/sum(1/h), like the library's how='add') and
    n_<period> (trips, both directions)."""
    d_all = e.dep.where(e.dep >= DAY_START_MIN, e.dep + 1440)
    rec = {}
    for (u, mode, a, b, rk), g in e.assign(d=d_all).groupby(["u", "mode", "a", "b", "route_key"]):
        d = np.sort(g.d.values)
        for per, wins in PERIODS.items():
            h, n = headway_window(d, wins)
            r = rec.setdefault((u, mode, per), {"dirs": {}, "n": 0, "lines": set(), "pool": {}})
            r["n"] += n
            r["pool"].setdefault((a, b), []).extend(d.tolist())          # all lines together, for the longest wait
            if n:
                r["dirs"].setdefault((a, b), []).append(h); r["lines"].add(rk)
    rows = {}
    for (u, mode, per), r in rec.items():
        # all lines of a direction pooled into ONE departure stream, then the pyGTFSHandler formula (bunched lines are not "frequent")
        per_dir = {k: headway_window(np.sort(np.array(r["pool"][k])), PERIODS[per])[0] for k in r["dirs"]}
        bestk = min(per_dir, key=per_dir.get) if per_dir else None
        best = per_dir[bestk] if bestk else np.nan
        lw = longest_wait(np.array(r["pool"][bestk]), PERIODS[per]) if bestk else np.nan    # same (better) direction as the headway
        row = rows.setdefault((u[0] + "||" + u[1], mode), {})
        row["hw_" + per], row["n_" + per], row["l_" + per], row["lw_" + per] = best, r["n"], len(r["lines"]), lw
        row["hab_" + per] = per_dir.get((u[0], u[1]), np.nan); row["hba_" + per] = per_dir.get((u[1], u[0]), np.nan)   # each direction
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index = pd.MultiIndex.from_tuples(out.index, names=["key", "mode"])
    return out


def _directions(node, k, neighbours, tol_deg=50):
    """Group the neighbours of node k by compass direction (greedy, tolerance tol_deg); returns mean bearings."""
    ang = sorted(float(np.degrees(np.arctan2((node.lon[n] - node.lon[k]) * np.cos(LAT0), node.lat[n] - node.lat[k])) % 360)
                 for n in neighbours)
    groups = []
    for a in ang:
        if groups and min(abs((a - g[-1] + 180) % 360 - 180) for g in groups[-1:]) <= tol_deg:
            groups[-1].append(a)
        else:
            groups.append([a])
    if len(groups) > 1 and abs((groups[0][0] - groups[-1][-1] + 180) % 360 - 180) <= tol_deg:   # wrap-around
        groups[0] = groups.pop() + groups[0]
    return [float(np.degrees(np.arctan2(np.mean(np.sin(np.radians(g))), np.mean(np.cos(np.radians(g))))) % 360) for g in groups]


def _drop_passthrough(st, keep, node, protect=frozenset()):
    """Branching is ALWAYS required: remove every node that does not reach >= 3 directions (stations of any mode within
    walking distance count only if together they reach a third direction). Exceptions: route termini (`protect`) and
    stations where all trips start or end. Done in passes (all non-branch nodes of a pass at once, links rebuilt between
    passes); the neighbours are then linked directly."""
    keep = set(keep); removed = []
    fl = (st["first"] | st["last"]) if "first" in st else pd.Series(False, index=st.index)
    endall = set(st.assign(fl=fl).groupby("node").fl.all().pipe(lambda s: s[s].index))   # every trip starts or ends here
    R_W = WALK_MAX_MIN * WALK_M_PER_MIN / 1.3
    ids = [k for k in node.index if k in keep]
    la_, lo_ = node.lat.reindex(ids).values, node.lon.reindex(ids).values
    near = {}                                                # stations within walking distance (positions never change)
    for i_, k in enumerate(ids):
        d = np.hypot((la_ - la_[i_]) * 111200, (lo_ - lo_[i_]) * 111200 * np.cos(np.radians(la_[i_])))
        near[k] = [ids[j_] for j_ in np.where(d <= R_W)[0] if ids[j_] != k]
    s0 = st[st.node.isin(keep)]
    while True:
        e = _edges(s0[s0.node.isin(keep)], keep, None, node, clean=True)
        if e.empty:
            break
        e["u"] = [tuple(sorted(x)) for x in zip(e.a, e.b)]
        pairs = e.groupby("u").size()
        pairs = pairs[pairs >= MIN_TRIPS_DAY]
        nb = defaultdict(set)
        for a, b in pairs.index:
            nb[a].add(b); nb[b].add(a)
        cand = []
        for k in keep:
            town = k.split("|")[0]
            if town in KEEP_ALWAYS or k in endall or k in protect or len(nb[k]) >= 3:
                continue
            part = [o for o in near.get(k, []) if o in keep]
            place = lambda n: n if n.split("|")[0] == town else n.split("|")[0]     # stations of the own town count as own directions
            here = {place(o) for o in [k] + part}
            dirs = {place(n) for c in [k] + part for n in nb[c]} - here
            if len(dirs) >= 3:
                continue                                    # a branch thanks to a station within walking distance
            cand.append(k)
        if not cand:
            break
        for k in cand:
            keep.discard(k); removed.append((k, "no branch", sorted(nb[k])))
    return keep, removed


def _drop_redundant(st, keep, node, protect=frozenset()):
    """A branching station is only needed if it offers a change between two lines that cannot be made at any other node.
    Lines of a station include those of stations within walking distance. If every pair of lines meeting at a station also
    meets at another kept node (e.g. Buttisholz: lines 60/61/62 all also stop at Ruswil), the station is redundant: it is
    removed (least departures first, re-checked after each removal) and its neighbours are linked directly."""
    from itertools import combinations
    keep = set(keep); removed = []
    vis = st[~st["far"]] if "far" in st else st
    lines = vis.groupby("node").route_key.agg(lambda x: frozenset(x)).to_dict()
    R_W = WALK_MAX_MIN * WALK_M_PER_MIN / 1.3
    ids = [k for k in node.index if k in keep]
    la_, lo_ = node.lat.reindex(ids).values, node.lon.reindex(ids).values
    near = {}
    for i_, k in enumerate(ids):
        d = np.hypot((la_ - la_[i_]) * 111200, (lo_ - lo_[i_]) * 111200 * np.cos(np.radians(la_[i_])))
        near[k] = [ids[j_] for j_ in np.where(d <= R_W)[0] if ids[j_] != k]
    # a route terminus stays only if its last stretch is not also run by another route that continues beyond it
    seq = vis.sort_values(["trip_key", "arr"]) if "arr" in vis else vis
    prv = seq.groupby("trip_key").node.shift(1); nxt_ = seq.groupby("trip_key").node.shift(-1)
    inner = defaultdict(set)                          # route -> (prev, node) stretches where the route continues
    endst = defaultdict(set)                          # node -> {(route, prev)} where a route ends coming from prev
    for r_, n_, p_, q_ in zip(seq.route_key, seq.node, prv, nxt_):
        if isinstance(p_, str) and isinstance(q_, str):
            inner[(p_, n_)].add(r_); inner[(q_, n_)].add(r_)
        elif isinstance(p_, str) or isinstance(q_, str):
            endst[n_].add((r_, p_ if isinstance(p_, str) else q_))
    hard = {k for k in protect if any(not inner.get((p_, k)) for r_, p_ in endst.get(k, ()))}   # (other trips of the same line count too)
    while True:
        grp = {k: frozenset([k] + [o for o in near.get(k, []) if o in keep]) for k in keep}
        L = {k: frozenset().union(*[lines.get(o, frozenset()) for o in grp[k]]) for k in keep}
        P = {k: {tuple(sorted(p)) for p in combinations(sorted(L[k]), 2)} for k in keep}
        where = defaultdict(set)                       # line pair -> stations (groups) where it meets
        for k in keep:
            for p in P[k]:
                where[p].add(k)
        rnodes = defaultdict(set)                      # kept stations of each route
        for k in keep:
            for r_ in lines.get(k, ()):
                rnodes[r_].add(k)
        cand = []
        for k in keep:
            if k.split("|")[0] in KEEP_ALWAYS or k in hard:
                continue
            if any(len(rnodes[r_]) <= 2 for r_ in lines.get(k, ())):
                continue                               # a route would keep fewer than 2 nodes and could not be drawn
            if all(any(j not in grp[k] for j in where[p]) for p in P[k]):
                # least important first: smaller municipality, secondary station of a town, fewer departures
                cand.append((MUNI_POP.get(k.split("|")[0], 0), k.count("|") == 1, float(node.departures.get(k, 0)), k))
        if not cand:
            break
        k = min(cand)[-1]
        keep.discard(k); removed.append((k, "redundant", "all its changes are possible at other nodes"))
    return keep, removed


def vehicle_km(st, stops):
    """Vehicle-km of one day per system, inside the province polygon: straight-line length of every stop-to-stop
    segment of every trip (stops of the feeds' bounding box), counted when the segment's midpoint is inside."""
    poly = shape(json.load(open(Path(__file__).parent.parent / POLYGON_FILE))["features"][0]["geometry"])
    x = st.merge(stops[["stop_key", "stop_lat", "stop_lon"]], on="stop_key").sort_values(["trip_key", "stop_sequence"])
    g = x.groupby("trip_key")
    la0, lo0 = g.stop_lat.shift(), g.stop_lon.shift()
    dy = (x.stop_lat - la0) * 111.2
    dx = (x.stop_lon - lo0) * 111.2 * np.cos(np.radians(x.stop_lat))
    km = np.hypot(dx, dy)
    mlat, mlon = (x.stop_lat + la0) / 2, (x.stop_lon + lo0) / 2
    ok = km.notna() & shapely.contains_xy(poly, mlon.fillna(0).values, mlat.fillna(0).values)
    return km.where(ok, 0).groupby(x["mode"]).sum().to_dict()


def fast_slow(e):
    """Per leg: 'fast' / 'slow' when a directed link has two clear service patterns, else ''.
    Two groups only if the slow one makes >= FS_MIN_STOPS more intermediate stops AND takes >= FS_MIN_MIN more minutes,
    and their headways are similar (the less frequent group runs at least every 2x the better group's headway).
    A few exceptional fast services do not form a group (each group needs >= FS_MIN_TRIPS trips a day)."""
    out = pd.Series("", index=e.index)
    if not len(e):
        return out
    for (a_, b_), g in e.groupby(["a", "b"]):
        if len(g) < 2 * FS_MIN_TRIPS:
            continue
        x = g.sort_values("tt")
        tt = x.tt.values; ns = x.ns.values
        best = None
        for i in range(FS_MIN_TRIPS, len(x) - FS_MIN_TRIPS + 1):          # split between fast (first i) and slow (rest)
            if tt[i] - tt[i - 1] <= 0:
                continue
            f, s = x.iloc[:i], x.iloc[i:]
            if np.median(s.tt) - np.median(f.tt) < FS_MIN_MIN or np.median(s.ns) - np.median(f.ns) < FS_MIN_STOPS:
                continue
            gap = tt[i] - tt[i - 1]
            if best is None or gap > best[0]:
                best = (gap, f.index, s.index)
        if best is None:
            continue
        hf = headway_window(np.sort(e.loc[best[1], "dep"].values), [(DAY_START_MIN, 22 * 60)])[0]
        hs = headway_window(np.sort(e.loc[best[2], "dep"].values), [(DAY_START_MIN, 22 * 60)])[0]
        if not (np.isfinite(hf) and np.isfinite(hs)) or max(hf, hs) > 2 * min(hf, hs):
            continue                                                      # headways too different: one group
        out.loc[best[1]] = "fast"; out.loc[best[2]] = "slow"
    return out


def _prune(st, node, protect=frozenset()):
    """Collapse links shorter than MIN_EDGE_MIN: the less important endpoint is dropped (route termini never).
    Done in passes: in each pass every short link (shortest first) whose two ends are untouched in this pass drops one end;
    links are rebuilt only between passes (same result as one-by-one, much faster)."""
    pos = node
    keep = set(node.index)
    removed = []
    s0 = st[st.node.isin(keep)]
    rk = lambda k: (PRIORITY.index(k.split('|')[0]) if k.split('|')[0] in PRIORITY else 10 ** 6, -float(node.score[k]))
    while True:
        e = _edges(s0[s0.node.isin(keep)], keep, None, pos)
        if e.empty:
            break
        e["u"] = [tuple(sorted(x)) for x in zip(e.a, e.b)]
        g = e.groupby("u").agg(tt=("tt", "median"), n=("tt", "size"))
        g = g[(g.n >= MIN_TRIPS_DAY) & (g.tt < MIN_EDGE_MIN)]
        g = g.loc[np.array([not any(k.split('|')[0] in EXEMPT_SHORT for k in u) for u in g.index], dtype=bool)].sort_values("tt")
        if g.empty:
            break
        touched, n0 = set(), len(removed)
        for (a, b), tt_ in zip(g.index, g.tt):
            if a in touched or b in touched:
                continue
            loser = a if rk(a) > rk(b) else b
            if loser in protect:                       # never drop a route terminus; try the other end
                loser = b if loser == a else a
            if loser in protect:
                continue
            keep.discard(loser); touched.update((a, b))
            removed.append((loser, a if loser == b else b, round(float(tt_), 1)))
        if len(removed) == n0:
            break
    return keep, removed


ROUTE_ALIAS = {}                                     # route key -> line key it was merged into (same stop pattern)


def _merge_same_routes(st, stops, jac=SAME_ROUTE_JACCARD):
    """Routes with (almost) the same stops are one line even if their names, ids or feeds differ (e.g. Lurraldebus
    variants, one route id per direction). Stops are compared by position (~100 m grid), per mode; two routes are the
    same line when the Jaccard overlap of their stop sets is >= `jac`. The line keeps the key of its busiest route."""
    pos = stops.set_index("stop_key")[["stop_lat", "stop_lon"]]
    x = st[["route_key", "stop_key", "mode", "trip_key"]].drop_duplicates(["route_key", "stop_key"])
    x = x.join(pos, on="stop_key").dropna(subset=["stop_lat"])
    x["cell"] = list(zip((x.stop_lat * 1000).round().astype(int), (x.stop_lon * 1000 / 1.5).round().astype(int)))
    sets = x.groupby("route_key").cell.agg(frozenset)
    mode = st.groupby("route_key")["mode"].first()
    ntrip = st.groupby("route_key").trip_key.nunique()
    keys = list(sets.index)
    parent = {k: k for k in keys}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]; k = parent[k]
        return k
    by_cell = defaultdict(set)                     # candidate pairs: routes sharing at least one stop cell
    for k in keys:
        for c in sets[k]:
            by_cell[(mode[k], c)].add(k)
    seen = set()
    for grp in by_cell.values():
        if len(grp) > 60:
            continue                               # a big hub cell: pairs are found through their other stops
        g = sorted(grp)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                p = (g[i], g[j])
                if p in seen:
                    continue
                seen.add(p)
                s1, s2 = sets[g[i]], sets[g[j]]
                if len(s1 & s2) >= jac * len(s1 | s2):
                    parent[find(g[i])] = find(g[j])
    groups_ = defaultdict(list)
    for k in keys:
        groups_[find(k)].append(k)
    ren = {}
    for members in groups_.values():
        if len(members) > 1:
            main = max(members, key=lambda k: ntrip.get(k, 0))
            for k in members:
                ren[k] = main
    ROUTE_ALIAS.update(ren)
    if ren:
        st = st.assign(route_key=st.route_key.map(lambda k: ren.get(k, k)))
        print(f"   same stop pattern: {len(ren) - sum(1 for v in set(ren.values()))} routes merged into {len(set(ren.values()))} lines")
    return st



def _two_way(e, pos=None):
    """Make links two-way where possible. For every directed pair a -> b (one mode) without any service b -> a:
    if the return trips run b -> x (-> y) -> a and that path is not much longer, the a -> b legs are routed along it
    (they pass x, y without stopping; travel time split in proportion); otherwise, if there are at most
    ONEWAY_DROP_MAX such legs a day, they are exceptional trips and dropped. Returns the new legs and a log."""
    if not len(e):
        return e, []
    cnt = e.groupby(["a", "b", "mode"]).size()
    med = e.groupby(["a", "b", "mode"]).tt.median()
    out_ = defaultdict(list)
    for (a, b, mo), t in med.items():
        out_[(a, mo)].append((b, float(t)))
    log, new, drop = [], [], np.zeros(len(e), bool)
    idx = {k: v for k, v in e.groupby(["a", "b", "mode"]).indices.items()}
    for (a, b, mo), n in cnt.items():
        if (b, a, mo) in cnt:
            continue
        tt0 = float(med[(a, b, mo)])
        best = None                                   # shortest return path b -> ... -> a with 1 or 2 stations in between
        for x, t1 in out_.get((b, mo), []):
            if x in (a, b):
                continue
            for y, t2 in out_.get((x, mo), []):
                if y == a:
                    c = (t1 + t2, [b, x, a], [t1, t2])
                    best = c if best is None or c[0] < best[0] else best
                elif y not in (a, b, x):
                    for z, t3 in out_.get((y, mo), []):
                        if z == a:
                            c = (t1 + t2 + t3, [b, x, y, a], [t1, t2, t3])
                            best = c if best is None or c[0] < best[0] else best
        rows = idx[(a, b, mo)]
        if best is not None and pos is not None:      # the corridor must also be geographically on the way
            P_ = [(float(pos.lat[k_]), float(pos.lon[k_])) for k_ in best[1]]
            dpath = sum(float(_m(*P_[k_], *P_[k_ + 1])) for k_ in range(len(P_) - 1))
            if dpath > 1.8 * float(_m(*P_[0], *P_[-1])) + 1000:
                best = None
        sis = None                                    # same town, same mode: the return trips use a sister station
        if best is None:
            ta, tb = a.split("|")[:2], b.split("|")[:2]
            for (x, y, mo2) in cnt.index:
                if mo2 == mo and (x, y) != (b, a) and x.split("|")[:2] == tb and y.split("|")[:2] == ta and (y, x, mo) not in cnt:
                    sis = (y, x); break
        if sis is not None:                           # draw the one-way trips between the stations the return trips use
            sub = e.iloc[rows]
            new.append(sub.assign(a=sis[0], b=sis[1]))
            drop[rows] = True
            log.append((a, b, mo, int(n), f"moved to {sis[0]} - {sis[1]}"))
        elif best is not None and best[0] <= ONEWAY_DETOUR[0] * tt0 + ONEWAY_DETOUR[1]:
            path, segs = best[1][::-1], best[2][::-1]          # forward: a -> ... -> b
            tot = sum(segs)
            sub = e.iloc[rows]
            for k in range(len(segs)):
                f0, f1 = sum(segs[:k]) / tot, sum(segs[:k + 1]) / tot
                new.append(sub.assign(a=path[k], b=path[k + 1], dep=sub.dep + sub.tt * f0, tt=sub.tt * (f1 - f0), ns=0))
            drop[rows] = True
            log.append((a, b, mo, int(n), "via " + " - ".join(path[1:-1])))
        elif n <= ONEWAY_DROP_MAX:
            drop[rows] = True
            log.append((a, b, mo, int(n), "dropped"))
        else:
            log.append((a, b, mo, int(n), "kept one-way"))
    # never drop the last legs of a route: a line must stay on the map (then it stays one-way)
    if drop.any():
        rk_ = e.route_key.values
        kept_r = set(rk_[~drop]) | {r_ for df_ in new for r_ in df_.route_key.unique()}
        lost = set(rk_[drop]) - kept_r
        if lost:
            back = drop & np.isin(rk_, list(lost))
            for k_, (a_, b_, mo_, n_, act_) in enumerate(log):
                if act_ == "dropped" and e.iloc[idx[(a_, b_, mo_)]].route_key.isin(lost).any():
                    log[k_] = (a_, b_, mo_, n_, "kept one-way (only service of its line)")
            drop &= ~back
    e2 = pd.concat([e[~drop]] + new, ignore_index=True) if new or drop.any() else e
    return e2, log


def _components(nodes, e, node, walk_min=WALK_MAX_MIN):
    """Connected pieces of the network: links of the legs plus walking links (<= walk_min) between the nodes."""
    par = {}
    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    if len(e):                                        # only links that will be on the map (>= MIN_TRIPS_DAY trips, touching the region)
        u_ = pd.Series([tuple(sorted(x)) for x in zip(e.a, e.b)])
        cnt_ = u_.groupby([u_, e["mode"].values]).size()
        ins_ = lambda k: k.split('|')[0] not in EXTERNAL
        for (uu, _m_), c_ in cnt_.items():
            a, b = uu
            if c_ >= MIN_TRIPS_DAY and (ins_(a) or ins_(b)) and a in nodes and b in nodes:   # stations without links are not on the map
                par.setdefault(a, a); par.setdefault(b, b)
                par[f(a)] = f(b)
    ids = list(par)
    la, lo = node.lat.reindex(ids).values, node.lon.reindex(ids).values
    for i in range(len(ids)):
        d = _m(la[i], lo[i], la, lo) * 1.3 / WALK_M_PER_MIN
        for j in np.where(d <= walk_min)[0]:
            if j > i:
                par[f(ids[i])] = f(ids[j])
    comp = defaultdict(set)
    for k in ids:
        comp[f(k)].add(k)
    return sorted(comp.values(), key=len, reverse=True)

DBG_CONN = []
ONEWAY_LOG = []                                     # (a, b, mode, trips, what was done) of the last build


def build(feeds: list[dict], ref=None, exclude=None, merge=None):
    """`ref` = (node, keep) of a previous build: reuse the same node set/positions (no pruning)."""
    stops, sts = [], []
    for fd in feeds:
        s = fd["stops"].copy(); s["stop_key"] = fd["name"] + "|" + s.stop_id
        s["label"] = fd["label"]
        stops.append(s[["stop_key", "stop_name", "stop_lat", "stop_lon", "label"]])
        t = fd["st"].merge(fd["trips"][["trip_id", "route_short_name", "mode", "agency_id"]], on="trip_id")
        t["stop_key"] = fd["name"] + "|" + t.stop_id
        t["trip_key"] = fd["name"] + "|" + t.trip_id
        t = t.merge(fd["trips"][["trip_id", "route_id"]], on="trip_id")
        t["route_key"] = fd["label"] + ":" + t.route_short_name.astype(str) + "@" + t.route_id.astype(str)   # one line = one GTFS route (shown by its short name)
        sts.append(t[["trip_key", "stop_key", "arr", "dep", "stop_sequence", "route_key", "mode"]])
    stops = pd.concat(stops, ignore_index=True).drop_duplicates("stop_key")
    st = pd.concat(sts, ignore_index=True)
    st = _merge_same_routes(st, stops)               # same stop pattern, different name / id / feed = one line

    vehkm = vehicle_km(st, stops)

    if MUNI_FILE:                                   # data-driven region: municipality polygon containing the stop
        import geopandas as gpd
        from towns import MUNI_POLYS
        pts = gpd.GeoDataFrame({"stop_key": stops.stop_key.values}, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat), crs=4326)
        j = gpd.sjoin(pts, MUNI_POLYS, how="left", predicate="within").drop_duplicates("stop_key").set_index("stop_key")
        stops["town"] = stops.stop_key.map(j["name"]).values
    else:
        # stop -> town (nearest centre within catchment)
        best, bd = np.array([None] * len(stops), dtype=object), np.full(len(stops), 1e12)
        for nme, (la, lo, rad) in TOWNS.items():
            d = _m(stops.stop_lat.values, stops.stop_lon.values, la, lo)
            ok = (d <= rad) & (d < bd); best[ok], bd[ok] = nme, d[ok]
        # Lurraldebus: assign by municipality prefix of the stop name instead (unknown municipality -> none)
        lower = {k.lower(): k for k in TOWNS}
        lower.update({k.lower().split("/")[0]: k for k in TOWNS})
        lower.update(MUNI_ALIAS)
        pre = stops.stop_name.str.extract(r"^(.+?) - ")[0].str.strip().str.lower()
        isl = ((stops.label == PREFIX_FEED) if PREFIX_FEED else pd.Series(False, index=stops.index)) & pre.notna()
        geo = best.copy()
        for i in np.where(isl.values)[0]:
            if geo[i] in GEOM_FIRST:
                continue
            t = lower.get(pre.iloc[i])
            if t is not None:
                la, lo, _ = TOWNS[t]
                ok = _m(stops.stop_lat.values[i], stops.stop_lon.values[i], la, lo) <= PREFIX_MAX_M
                best[i] = t if ok else None
            else:
                best[i] = None
        stops["town"] = best
    stops = stops.dropna(subset=["town"]).copy()
    # regional buses only: a bus route must serve >= 3 municipalities and have a trip of >= 8 km (drops town / local buses)
    if REGIONAL_BUS_MIN_TOWNS:
        x = st[st["mode"] == "bus"].merge(stops[["stop_key", "town", "stop_lat", "stop_lon"]], on="stop_key").sort_values(["trip_key", "stop_sequence"])
        same = x.trip_key.values[1:] == x.trip_key.values[:-1]
        dm = np.where(same, _m(x.stop_lat.values[1:], x.stop_lon.values[1:], x.stop_lat.values[:-1], x.stop_lon.values[:-1]), 0.0)
        x["d"] = np.concatenate([[0.0], dm])
        rl = x.groupby(["route_key", "trip_key"]).d.sum().groupby("route_key").max() / 1000
        nt = x.groupby("route_key").town.nunique()
        major = set(nt.index[(nt >= REGIONAL_BUS_MIN_TOWNS) & (rl.reindex(nt.index).fillna(0) >= REGIONAL_BUS_MIN_KM)])
        bad = set(nt.index[nt < MINOR_BUS_MIN_TOWNS])                 # town buses (one municipality): out
        minor = set(nt.index) - major - bad                          # other lines: only between nodes that exist anyway
        if bad:
            st = st[~st.route_key.isin(bad)].copy()
            vehkm = vehicle_km(st, stops)
        st["minor"] = st.route_key.isin(minor)
        print(f"   bus lines: {len(major)} regional (>= {REGIONAL_BUS_MIN_TOWNS} municipalities, >= {REGIONAL_BUS_MIN_KM:g} km), "
              f"{len(minor)} other (only between existing nodes), {len(bad)} town buses dropped")
    if "minor" not in st:
        st["minor"] = False
    # a stop belongs to a node per SYSTEM of the trips that call there (one feed can mix trains and buses)
    st = st.merge(stops[["stop_key", "town", "stop_lat", "stop_lon"]], on="stop_key")
    st["node"] = st.town + "|" + st["mode"]
    sn = st[~st["minor"]].groupby(["node", "stop_key"]).agg(deps=("trip_key", "size"), nr=("route_key", "nunique")).reset_index().merge(
        stops[["stop_key", "stop_name", "stop_lat", "stop_lon"]], on="stop_key")
    # ---- node anchors (position = chosen station stop + stops within 250 m)
    rows, rail_pos = {}, defaultdict(list)
    # rail nodes first: bus nodes are then anchored next to their town's station when possible
    for key, g in sorted(sn.groupby("node"), key=lambda kv: kv[0].split("|")[1] not in RAIL_SYSTEMS):
        if ref is not None and key not in ref[0].index:
            continue
        pick = g
        sysk = key.split("|")[1]
        if sysk not in RAIL_SYSTEMS:
            hs = g[g.stop_name.str.contains(BUS_STATION_RE, flags=re.I, regex=True) & (g.deps >= 5)]
            pick = hs if len(hs) else g
            if not len(hs) and rail_pos.get(key.split("|")[0]):        # no bus station: best-served stop near the train station
                near_st = g[[min(float(_m(la, lo, a, b)) for a, b in rail_pos[key.split("|")[0]]) <= STATION_RADIUS_M
                             for la, lo in zip(g.stop_lat, g.stop_lon)]]
                near_st = near_st[near_st.deps >= max(8, 0.25 * g.deps.max())]
                pick = near_st if len(near_st) else g
        else:                                                      # main station: name == town, then startswith
            tok = re.split(r"[/-]", key.split("|")[0])[0].strip().lower()
            nm = g.stop_name.str.lower().str.replace("estaci\u00f3n de tren ", "", regex=False).str.strip()
            main = g[nm.isin([tok, tok + " bahnhof", tok + " hbf", tok + " bf"])]            # "<Town> Bahnhof" before other stops
            ex = main if len(main) else g[nm.str.replace(r"[-/ ].*", "", regex=True).eq(tok) & ~nm.str.contains("-")]
            ex = ex if len(ex) else g[nm.str.startswith(tok)]
            pick = ex if len(ex) else g
            hb = pick[pick.stop_name.str.contains(r"hauptbahnhof|\bhbf\b|bahnhof|estaci", case=False, regex=True)]
            pick = hb if len(hb) else pick
            pick = pick[pick.nr == pick.nr.max()]                 # the stop served by the most lines (not a terminus of one urban line)
        if key in ANCHOR_HINT:
            h = g[g.stop_name.str.contains(ANCHOR_HINT[key], flags=re.I, regex=True)]
            pick = h if len(h) else pick
        c = pick.sort_values("deps", ascending=False).iloc[0]
        near = g[_m(g.stop_lat, g.stop_lon, c.stop_lat, c.stop_lon) <= 250]
        rows[key] = dict(lat=near.stop_lat.mean(), lon=near.stop_lon.mean(), anchor=c.stop_name)
        if sysk in RAIL_SYSTEMS:
            rail_pos[key.split("|")[0]].append((rows[key]["lat"], rows[key]["lon"]))
    node = pd.DataFrame.from_dict(rows, orient="index")
    if ref is None:                                          # further candidate stations of the same municipality and mode
        R_ST = WALK_MAX_MIN * WALK_M_PER_MIN                   # stops within a 5-min walk form one station
        sn2 = sn.assign(town=sn.node.str.split("|").str[0], sys=sn.node.str.split("|").str[1])
        rtk = st.groupby("stop_key").route_key.agg(lambda x: set(x))
        extra = {}
        for (tn, sy), g in sn2.groupby(["town", "sys"]):
            mk = f"{tn}|{sy}"
            if mk not in node.index:
                continue
            cents = [(node.loc[mk, "lat"], node.loc[mk, "lon"])]
            g = g.sort_values("deps", ascending=False)
            for r_ in g.itertuples():
                if min(float(_m(r_.stop_lat, r_.stop_lon, la, lo)) for la, lo in cents) <= R_ST:
                    continue
                cl = g[_m(g.stop_lat, g.stop_lon, r_.stop_lat, r_.stop_lon) <= R_ST]
                lines = set().union(*[rtk.get(k, set()) for k in cl.stop_key])
                if sy not in RAIL_SYSTEMS:                     # bus: only a bus station or the stop next to a train station
                    isbs = cl.stop_name.str.contains(BUS_STATION_RE, flags=re.I, regex=True).any()
                    nrail = any(float(_m(r_.stop_lat, r_.stop_lon, la, lo)) <= STATION_RADIUS_M for la, lo in rail_pos.get(tn, []))
                    if not (isbs or nrail):
                        continue
                cents.append((r_.stop_lat, r_.stop_lon))
                k = f"{mk}|{len(cents) - 1}"
                extra[k] = dict(lat=cl.stop_lat.mean(), lon=cl.stop_lon.mean(), anchor=r_.stop_name)
        if extra:
            node = pd.concat([node, pd.DataFrame.from_dict(extra, orient="index")])
    if ref is not None:
        node = ref[0][["lat", "lon", "anchor"]].copy()
    # each stop belongs to the NEAREST candidate station of its municipality and mode
    nk = pd.Series(node.index, index=node.index)
    base = nk.str.split("|").str[:2].str.join("|")
    cand = {b: list(g) for b, g in nk.groupby(base)}
    us = st[["stop_key", "node", "stop_lat", "stop_lon"]].drop_duplicates(["stop_key", "node"])
    best_k = {}
    for b, g in us.groupby("node"):
        cs = cand.get(b)
        if not cs:
            continue
        if len(cs) == 1:
            for sk_ in g.stop_key: best_k[(sk_, b)] = cs[0]
            continue
        dm = np.array([_m(g.stop_lat.values, g.stop_lon.values, node.loc[c, "lat"], node.loc[c, "lon"]) for c in cs])
        for sk_, j in zip(g.stop_key, dm.argmin(axis=0)): best_k[(sk_, b)] = cs[j]
    st["node"] = [best_k.get((s_, n_), n_) for s_, n_ in zip(st.stop_key, st.node)]
    if merge:                                        # stations merged into another one of the same place (run_analysis)
        st["node"] = st.node.map(lambda k_: merge.get(k_, k_))
        node = node[~node.index.isin(set(merge))]
    # attach stops to nodes; for each run of consecutive stops in the same node use the times of the
    # stop CLOSEST TO THE NODE ANCHOR (so travel times are station-to-station, not catchment edge)
    st = st.sort_values(["trip_key", "stop_sequence"]).reset_index(drop=True)
    st["k"] = st.groupby("trip_key").cumcount()             # position of the stop in its trip (stops between node visits)
    st["adist"] = _m(st.stop_lat.values, st.stop_lon.values,
                     node.lat.reindex(st.node).values, node.lon.reindex(st.node).values)
    # a trip that passes through a municipality but never near its station still serves it (drawn), up to FAR_VISIT_M;
    # such far visits are no station visits: they are left out of transfers / symmetry / dwell events
    st = st[st.node.isin(node.index) & (st.adist <= FAR_VISIT_M)].reset_index(drop=True)
    st["run"] = ((st.node != st.node.shift()) | (st.trip_key != st.trip_key.shift())).cumsum()
    best = st.loc[st.groupby("run").adist.idxmin()].set_index("run")
    best["far"] = best.adist > best["mode"].map(MAX_ANCHOR_M).fillna(1200)
    st = best[["trip_key", "node", "arr", "dep", "route_key", "mode", "far", "k", "minor"]].reset_index(drop=True)
    st["last"] = st.trip_key != st.trip_key.shift(-1)
    st["first"] = st.trip_key != st.trip_key.shift(1)
    deps = st[~st["last"] & ~st["minor"]]               # node importance and existence from trains and regional buses only
    smj = st[~st["minor"]]                               # the other bus lines never create or keep nodes
    node["town"] = [k.split("|")[0] for k in node.index]
    node["system"] = [k.split("|")[1] for k in node.index]
    node["label"] = node.town.map(lambda t: DISPLAY.get(t, t))
    node["name"] = node.label + " · " + node.system.map(SYS_NAME)
    node["departures"] = deps.groupby("node").size().reindex(node.index).fillna(0)
    node["routes"] = st.groupby("node").route_key.nunique().reindex(node.index).fillna(0)
    node["score"] = node.departures + 5 * node.routes
    # route termini: a station where >= 30 % of a route's trips start or end is always a node (also outside the region)
    # (share among the route's trips that reach the station: a pattern ending there counts even if the route has other patterns)
    fl_ = smj[smj["first"] | smj["last"]].groupby(["route_key", "node"]).size()
    nvis = smj.groupby(["route_key", "node"]).trip_key.nunique()
    TERM = set(n_ for (rk_, n_), c_ in fl_.items() if c_ >= 0.3 * nvis.get((rk_, n_), 1)) & set(node.index)
    if ref is None:
        node = node[node.departures > 0]
        if MUNI_FILE:                                # outside municipalities only as sizeable hubs or route termini
            node = node[~(node.town.isin(EXTERNAL) & (node.departures < EXTERNAL_MIN_DEPS) & ~node.index.isin(TERM))]
        keep, removed = _prune(smj, node, TERM)
        if PASSTHROUGH:                              # (off for the data-driven regions: every served town keeps its node)
            keep, passed = _drop_passthrough(smj, keep, node, TERM)
            removed = removed + passed
            if DROP_REDUNDANT:
                for _ in range(4):                      # redundant stations, then non-branches again, until stable
                    keep, red = _drop_redundant(smj, keep, node, TERM)
                    keep, passed = _drop_passthrough(smj, keep, node, TERM)
                    removed = removed + red + passed
                    if not red and not passed:
                        break
    else:
        keep, removed = set(ref[1]), []
    _t = smj.assign(e_=(smj["first"] | smj["last"]).astype(int)).groupby("node").e_.agg(["sum", "size"])
    ends = (set(_t.index[(_t["sum"] >= 1) & (_t["sum"] >= _t["size"])]) | TERM) & set(node.index)   # termini (all trips, or a route's end)
    if ref is None:
        redundant_ = {r_[0] for r_ in removed if len(r_) > 1 and r_[1] == "redundant"}
        keep = keep | (ends - redundant_)           # a service that starts or ends at a place keeps its node (unless redundant)
        if exclude:                                  # stations removed by run_analysis (short links without connections)
            keep = keep - set(exclude)
        # safeguard: every route must keep >= 2 nodes so it can be drawn -> give it back its end stations
        vis_ = smj                                     # (also stops passing through: they draw the route)
        isin_ = lambda k_: k_.split("|")[0] not in EXTERNAL
        for rk_, g_ in vis_[vis_.node.isin(node.index)].groupby("route_key"):
            kept_ = set(g_.node) & keep
            # most trips of the route must reach >= 2 kept nodes (one exceptional trip does not make the route drawable)
            ntk = g_[g_.node.isin(keep)].groupby("trip_key").node.nunique().reindex(g_.trip_key.unique()).fillna(0)   # distinct kept stations per trip (a loop visits its start twice)
            if (ntk >= 2).mean() < 0.5:
                bad = g_[g_.trip_key.isin(ntk.index[ntk < 2])]
                ends_ = bad.loc[bad["first"] | bad["last"], "node"].value_counts()
                add_ = set(ends_.index[:2]) & set(node.index)
                have = (set(bad.node) & (keep | add_))
                if len(have) < 2:                          # a loop (Sins - Auw - Abtwil - Sins): add its farthest stop too
                    cand_ = [k_ for k_ in set(bad.node) & set(node.index) if k_ not in have]
                    if cand_ and have:
                        h0 = next(iter(have))
                        add_.add(max(cand_, key=lambda k_: float(_m(node.lat[k_], node.lon[k_], node.lat[h0], node.lon[h0]))))
                    elif len(cand_) >= 2:
                        add_ |= set(sorted(cand_, key=lambda k_: -float(node.departures.get(k_, 0)))[:2])
                keep |= add_
            inside_ = {k_ for k_ in g_.node if isin_(k_)}
            if inside_ and not (inside_ & keep):       # the route serves the region but no node inside it is left
                ends_in = set(g_.loc[g_["first"] | g_["last"], "node"]) & inside_
                keep |= (ends_in or inside_)
    node_all = node.copy()                           # (all candidate stations: used to reconnect cut-off pieces)
    if exclude:                                      # (the drawable safeguard above may have given some back)
        if ref is not None:
            keep = keep - set(exclude)
        node = node[~node.index.isin(set(exclude) - keep)]
    keep_towns = {k.split('|')[0] for k in keep}
    # links: a far visit in the middle of a trip that is off the way (passing it is > 1.3 x the direct distance between the
    # stations before and after) is no link stop (e.g. a town bus loop touching the border of the next municipality)
    def _st_links(keep):
        s_ = st[st.node.isin(keep)].copy()
        g_ = s_.groupby("trip_key").node
        s_["p_"], s_["n_"] = g_.shift(1), g_.shift(-1)
        c_ = s_[s_["far"] & s_.p_.notna() & s_.n_.notna() & (s_.p_ != s_.node) & (s_.n_ != s_.node)]
        if not len(c_):
            return st
        P_ = node_all[["lat", "lon"]]
        la = lambda k_: P_.lat.reindex(k_).values; lo = lambda k_: P_.lon.reindex(k_).values
        dpn = _m(la(c_.p_), lo(c_.p_), la(c_.n_), lo(c_.n_))
        dvia = _m(la(c_.p_), lo(c_.p_), la(c_.node), lo(c_.node)) + _m(la(c_.node), lo(c_.node), la(c_.n_), lo(c_.n_))
        off = c_.index[dvia > 1.3 * dpn + 500]
        return st.drop(index=off)
    def _legs(keep):
        e = _edges(_st_links(keep), keep, None, node_all, clean=True)   # same-system consecutive nodes only (a bus stop is not a train stop)
        e["ns"] = (e.b_k - e.k - 1).clip(lower=0) if "b_k" in e else 0          # intermediate stops on the link
        e["cls"] = fast_slow(e)
        e = e[e.a.isin(keep) & e.b.isin(keep)].copy()
        log = []
        for _ in range(3):                                  # links as two-way as possible (a reroute can leave a new one-way pair)
            e, lg = _two_way(e, node_all)
            log += [x for x in lg if x[4] != "kept one-way"] if _ < 2 else lg
            if not any(x[4] != "kept one-way" for x in lg):
                log += [x for x in lg if x[4] == "kept one-way" and x not in log]
                break
        return e, log
    e, ow_log = _legs(keep)
    DBG_CONN[:] = []
    # the network must be ONE connected graph: a piece cut off gets back the station that links it to the rest
    # (a station of one of its towns, or within walking distance of it, served by trips that also reach the main network)
    for _ in range(6):
        comps = _components(keep & set(node_all.index), e, node_all)
        if len(comps) <= 1:
            break
        main_ = comps[0]
        added = False
        for cp in comps[1:]:
            towns_ = {k_.split("|")[0] for k_ in cp}
            near_ = set()
            for k_ in node_all.index:
                if k_ in keep:
                    continue
                if k_.split("|")[0] in towns_ or min(float(_m(node_all.lat[k_], node_all.lon[k_], node_all.lat[c_], node_all.lon[c_])) for c_ in cp) * 1.3 / WALK_M_PER_MIN <= WALK_MAX_MIN:
                    near_.add(k_)
            mtrips = set(st.trip_key[st.node.isin(main_)])
            cand_ = [(int(((st.node == k_) & st.trip_key.isin(mtrips)).sum()), k_) for k_ in near_]
            cand_ = [c_ for c_ in cand_ if c_[0] > 0]
            if cand_:
                keep.add(max(cand_)[1]); added = True
        if not added:
            DBG_CONN[:] = [(sorted(cp), sorted(near_)) for cp in comps[1:]]   # (reported by run_analysis)
            break
        e, ow_log = _legs(keep)
    ONEWAY_LOG[:] = ow_log
    if len(_components(keep & set(node_all.index), e, node_all)) <= 1:
        DBG_CONN[:] = []
    back_ = [k_ for k_ in keep if k_ in node_all.index and k_ not in node.index]
    if back_:
        node = pd.concat([node, node_all.loc[back_]])
    e["hour"] = (e.dep // 60).astype(int)
    e["dep_min"] = (e.dep % 60).round().astype(int) % 60
    e["u"] = [tuple(sorted(x)) for x in zip(e.a, e.b)]
    und = e.groupby(["u", "mode"]).agg(
        trips_day=("tt", "size"), tt_med=("tt", "median"), tt_min=("tt", "min"), tt_max=("tt", "max"),
        peak=("hour", lambda h: int(h.between(7, 8).sum())),
        routes=("route_key", lambda x: ", ".join(sorted(set(x))[:8])),
        minutes=("dep_min", lambda m: sorted(m.value_counts().head(6).index.tolist()))).reset_index()
    ex = np.array([any(k.split('|')[0] in EXEMPT_SHORT for k in u) for u in und.u])
    und["key"] = [a + "||" + b for a, b in und.u]
    und = und.merge(period_headways(e).reset_index(), on=["key", "mode"], how="left").drop(columns="key")
    und = und[und.trips_day >= MIN_TRIPS_DAY].copy()       # (short links were already collapsed by _prune; never cut a line here)
    und["a"], und["b"] = zip(*und.u)
    inside = lambda k: k.split('|')[0] not in EXTERNAL
    und = und[[inside(a) or inside(b) for a, b in zip(und.a, und.b)]]   # drop links not touching the region
    und = und.join(edge_minutes(e, und))
    keys = set(zip(und.u, und["mode"]))
    legs = e[[(u, m) in keys for u, m in zip(e.u, e["mode"])]][["a", "b", "dep", "tt", "mode", "route_key", "trip_key", "ns", "cls"]].copy()   # every service leg (for the video)
    used = set(und.a) | set(und.b)
    if ref is None:
        node = node[node.index.isin(used)].copy()
    node["important"] = True
    tm = node.index.str.split("|").str[:2].str.join("|")
    multi = set(tm[tm.duplicated(keep=False)])
    def _stn(k):
        """Short station name: without the municipality name, only the part before the first comma, max ~22 characters."""
        an = str(node.loc[k, "anchor"]); t = node.loc[k, "town"]
        t0 = re.sub(r"\s*\(.*?\)", "", t)                    # "Hergiswil (NW)" -> "Hergiswil"
        for tok in sorted({t, t0} | set(re.split(r"\s*[/,-]\s*", t0)), key=len, reverse=True):
            if tok and len(tok) > 2:                    # the town name anywhere in the station name
                an = re.sub(r"(?i)(^|[\s,/\-·]+)" + re.escape(tok) + r"\b", " ", an)
        an = an.strip(" -·,/")
        an = an.split(",")[0].strip(" -·")
        if not an or an.lower() in {x.lower() for x in re.split(r"\s*[/,-]\s*", t) + [t]}:
            an = "main station"                                   # the station simply named after the town
        for pat, rep in ((r"(?i)autobus\s*geltokia|estaci[oó]n de autobuses|busbahnhof|bus\s*station", "bus station"),
                         (r"(?i)hauptbahnhof", "Hbf"), (r"(?i)\bbahnhof\b", "Bf"), (r"(?i)\bkalea\b|\bstrasse\b|\bstraße\b", "")):
            an = re.sub(pat, rep, an).strip(" -·,")
        an = re.sub(r"\s+", " ", an).strip(" -·,/") or "main station"
        if "bus station" in an.lower():
            an = "bus station"
        return an if len(an) <= 16 else an[:15].rstrip() + "…"
    short_town = lambda t: DISPLAY.get(t, re.split(r"\s+/\s+|\s*/\s*", t)[0].strip())   # "Donostia / San Sebastián" -> "Donostia"
    node["label"] = [(short_town(node.loc[k, "town"]) + (" · " + _stn(k) if m_ in multi else "")) for k, m_ in zip(node.index, tm)]
    node["name"] = node.label + " · " + node.system.map(SYS_NAME)

    # ---- walking links between different systems in the same town
    walk = []
    for _one in [0]:                                   # any two nodes (any town, any mode) within walking distance
        ids = list(node.index)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = node.loc[ids[i]], node.loc[ids[j]]
                if abs(a.lat - b.lat) > 0.01 or abs(a.lon - b.lon) > 0.015:
                    continue
                d = float(_m(a.lat, a.lon, b.lat, b.lon)) * 1.3
                if d / WALK_M_PER_MIN <= WALK_MAX_MIN:
                    walk.append(dict(a=ids[i], b=ids[j], meters=round(d), walk_min=round(d / WALK_M_PER_MIN, 1)))
    walk = pd.DataFrame(walk, columns=["a", "b", "meters", "walk_min"])

    # ---- takt phase stats per node: departure minute (+-2 min window)
    d2 = deps[deps.node.isin(node.index)].copy()
    d2["m"] = (d2.dep % 60).round().astype(int) % 60
    rows_t = []
    for nd, g in d2.groupby("node"):
        for per, wins in PERIODS.items():
            gg = g[in_band(g.dep.values, wins)]
            mm, iv, sh = main_minutes(gg.m.values, min_count=2)
            rows_t.append(dict(node=nd, band=per, n=len(gg), minutes=",".join(map(str, mm)), interval=iv, share_in_window=sh))
    takt = pd.DataFrame(rows_t)
    # arrival / departure events at the kept nodes, with trip and previous/next kept node (transfers, symmetry, minutes)
    sk = st[st.node.isin(node.index) & ~st["far"]].copy()   # only real station visits of nodes on the map (previous/next must exist)
    gk = sk.groupby("trip_key").node
    sk["prev"], sk["next"] = gk.shift(1), gk.shift(-1)
    adj = lambda t: np.where(t < DAY_START_MIN, t + 1440, t)
    lcls = dict(zip(zip(e.trip_key, e.a, e.b), e.cls))                    # fast / slow class of each trip on each link
    sk["cin"] = [lcls.get((t, p, n), "") for t, p, n in zip(sk.trip_key, sk.prev, sk.node)]
    sk["cout"] = [lcls.get((t, n, x), "") for t, n, x in zip(sk.trip_key, sk.node, sk.next)]
    cols = ["node", "route_key", "trip_key", "prev", "next"]
    ev = pd.concat([sk[sk.prev.notna()][cols + ["cin"]].rename(columns={"cin": "cls"}).assign(t=adj(sk[sk.prev.notna()].arr.values), kind="arr"),
                    sk[sk.next.notna()][cols + ["cout"]].rename(columns={"cout": "cls"}).assign(t=adj(sk[sk.next.notna()].dep.values), kind="dep")], ignore_index=True)
    ev = ev[ev.node.isin(node.index)]
    vis = sk[sk.prev.notna() & sk.next.notna()]                       # intermediate stops: the vehicle stands there from arrival to departure
    dwell = pd.DataFrame(dict(node=vis.node.values, mode=vis["mode"].values, rk=vis.route_key.values, nx=vis.next.values, t0=adj(vis.arr.values), t1=adj(vis.dep.values)))
    dwell = dwell[(dwell.t1 - dwell.t0 >= 0.9) & (dwell.t1 - dwell.t0 <= 30)]
    return node, und.drop(columns=["u", "peak"]), walk, takt, removed, keep, legs, ev, vehkm, dwell, ends


def shortest_times(node, und, walk, transfer_penalty=5.0):
    """Dijkstra over nodes. Boarding costs half the peak headway (max 30) + penalty unless the rider
    stays on the same system; walking links cost walk_min. Returns minutes matrix."""
    adj = defaultdict(list)
    for r in und.itertuples():
        hw = r.hw_peak if np.isfinite(r.hw_peak) else 60
        w = min(hw / 2, 30) + transfer_penalty
        adj[r.a].append((r.b, r.tt_med, r.mode, w)); adj[r.b].append((r.a, r.tt_med, r.mode, w))
    for r in walk.itertuples():
        adj[r.a].append((r.b, r.walk_min, "walk", 0)); adj[r.b].append((r.a, r.walk_min, "walk", 0))
    ids = list(node.index)
    out = pd.DataFrame(np.inf, index=ids, columns=ids)
    for s in ids:
        dist = {(s, "start"): 0.0}; pq = [(0.0, s, "start")]
        while pq:
            d, u, m = heapq.heappop(pq)
            if d > dist.get((u, m), 1e9):
                continue
            for v, t, mode, w in adj[u]:
                board = 0 if (mode == "walk" or m == mode or m == "start") else w
                nd = d + t + board
                if nd < dist.get((v, mode), 1e9):
                    dist[(v, mode)] = nd; heapq.heappush(pq, (nd, v, mode))
        for (v, _), d in dist.items():
            out.at[s, v] = min(out.at[s, v], d)
    return out


def merge_groups(node):
    """Group nodes of the same town with DIFFERENT systems into one multi-coloured node when they are the same
    station: walk between them <= MERGE_WALK_MIN minutes (same building / next door), OR both stops carry the
    same station name (e.g. 'Bludenz Bahnhof' for train and bus) and lie within 400 m. Returns {node: group id}."""
    par = {k: k for k in node.index}
    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    nm = lambda k: str(node.loc[k, "anchor"]).casefold().replace(".", "").replace(" ", "")
    for town, g in node.groupby("town"):
        ids = list(g.index)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = node.loc[ids[i]], node.loc[ids[j]]
                if a.system == b.system:
                    continue
                d = float(_m(a.lat, a.lon, b.lat, b.lon))
                if d * 1.3 / WALK_M_PER_MIN <= MERGE_WALK_MIN or (nm(ids[i]) == nm(ids[j]) and d <= 400):
                    par[f(ids[i])] = f(ids[j])
    roots = defaultdict(list)
    for k in node.index:
        roots[f(k)].append(k)
    return {k: sorted(v)[0] for v in roots.values() for k in v}
