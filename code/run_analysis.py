"""Run: python3 code/run_analysis.py [gipuzkoa|vorarlberg] [GTFS_ROOT]
Writes output/<region>/*.csv and the map page maps/<region>/index.html (one URL per region on the GitHub Pages site).
Weekday defines the node set (9-minute rule, pass-through removal); Saturday and Sunday reuse the same nodes."""
import os
import sys
from pathlib import Path

REGION = sys.argv[1] if len(sys.argv) > 1 else "gipuzkoa"
os.environ["REGION"] = REGION                      # must be set before importing the modules below
sys.path.insert(0, str(Path(__file__).parent))
import pandas as pd_
import towns
from gtfs_io import FEEDS, DAYTYPES, load_feed
from analysis import build, merge_groups
from coordination import symmetry_band, node_minutes, transfers, stopped
from make_map import make_map

ROOT = Path(__file__).parent.parent

if __name__ == "__main__":
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / towns.GTFS_ROOT
    OUT = ROOT / "output" / REGION
    OUT.mkdir(parents=True, exist_ok=True)
    per_day = {d: [] for d in DAYTYPES}
    for n in FEEDS:
        res = load_feed(root, n, tuple(DAYTYPES))
        for d, fd in res.items():
            if len(fd["st"]):
                per_day[d].append(fd)
        if res:
            print(f"{FEEDS[n][0]:16s} {n[:8]} " + "  ".join(f"{d}={fd['date']}({len(fd['trips'])} trips)" for d, fd in res.items()))
    if not per_day["weekday"]:
        sys.exit(f"No GTFS feeds found in {root}. Expected sub-folders: {', '.join(FEEDS)} (see README).")
    results, ref, groups = {}, None, None
    for d in DAYTYPES:                       # weekday first -> reference node set
        first = ref is None
        excl = set(); mrg = {} if first else mrg
        for it in range(6 if first else 1):    # weekday: drop stations on short links that are not needed for connections, repeat
            node, und, walk, takt, removed, keep, legs, ev, vehkm, dwell, ends = build(per_day[d], ref, excl, mrg if first else None)
            if not first:
                break
            groups = merge_groups(node)
            tr, coord, used, estat = transfers(ev, groups, node, walk)
            # links shorter than SHORT_LINK_MIN are kept only if both stations are needed for connections (a timed
            # connection or a symmetry in some band); otherwise the less important station goes (also an end station)
            needed = set()
            for g_, bb in estat.items():
                if any(d_.get("sym") or any(c and c[0] == "c" for x in d_.get("ep", []) for c in (x[8], x[9])) for d_ in bb.values()):
                    needed |= {k for k, v in groups.items() if v == g_}
            imp = lambda k: (towns.MUNI_POP.get(k.split("|")[0], 0), float(node.departures.get(k, 0)))
            drop = set(); newm = set()
            rn = {}                                        # nodes of each route on the map (a route must keep >= 2)
            for rk_, g_ in legs.groupby("route_key"):
                rn[rk_] = set(g_.a) | set(g_.b)
            rof = {}
            for rk_, ns_ in rn.items():
                for k_ in ns_:
                    rof.setdefault(k_, set()).add(rk_)
            # the network must stay ONE connected graph (links + walking links): never drop a station that would split it
            adj_ = {}
            for a_, b_ in list(zip(und.a, und.b)) + list(zip(walk.a, walk.b)):
                adj_.setdefault(a_, set()).add(b_); adj_.setdefault(b_, set()).add(a_)
            def pieces(gone):
                left = set(adj_) - gone; seen_, n_ = set(), 0
                for s_ in left:
                    if s_ in seen_:
                        continue
                    n_ += 1; todo = [s_]; seen_.add(s_)
                    while todo:
                        x_ = todo.pop()
                        for y_ in adj_.get(x_, ()):
                            if y_ in left and y_ not in seen_:
                                seen_.add(y_); todo.append(y_)
                return n_
            base_pieces = pieces(set())
            safe = lambda k_: all(len(rn[r_] - drop - {k_}) >= 2 for r_ in rof.get(k_, ())) and pieces(drop | {k_}) <= base_pieces
            for a_, b_, tt_ in zip(und.a, und.b, und.tt_med):
                if tt_ >= towns.SHORT_LINK_MIN or a_ in drop or b_ in drop:
                    continue
                same_place = a_.split("|")[:2] == b_.split("|")[:2]          # two stations of one mode in one municipality
                if same_place:                             # < 10 min apart: one place -> merge into the main / busier station
                    lo_ = min((a_, b_), key=lambda k: (k.count("|") == 1, float(node.departures.get(k, 0))))
                    hi_ = b_ if lo_ == a_ else a_
                    if lo_ not in mrg and hi_ not in drop:
                        mrg[lo_] = hi_; newm.add(lo_)
                    continue
                cand_ = [k for k in (a_, b_) if k not in needed and safe(k)]
                if cand_:
                    drop.add(min(cand_, key=imp))
            drop -= excl                                  # already removed (or given back to keep a line drawable)
            for k_ in list(mrg):                          # resolve chains a -> b -> c
                seen_ = {k_}
                while mrg[k_] in mrg and mrg[k_] not in seen_:
                    seen_.add(mrg[k_]); mrg[k_] = mrg[mrg[k_]]
            print(f"   pass {it + 1}: {len(node)} nodes, {len(drop)} stations removed on short links (< {towns.SHORT_LINK_MIN} min) without connections, {len(newm)} merged into another station of the same place")
            if (not drop and not newm) or it == 5:
                break
            excl |= drop
        if first:
            ref = (node, keep)
            groups = merge_groups(node)
            print(f"\n{len(node)} nodes ({len(set(groups.values()))} after merging stations), {len(und)} edges, {len(walk)} walk links")
            print("nodes removed (9-minute rule / pass-through):")
            for r in removed: print("  ", r)
            print("merged:", {g: [k for k in groups if groups[k] == g] for g in set(groups.values()) if list(groups.values()).count(g) > 1})
        if not first:
            tr, coord, _, estat = transfers(ev, groups, node, walk)
        sym = symmetry_band(ev, groups, node, coord, estat)
        nmin = node_minutes(ev, groups, node, sym)
        lay = stopped(ev, groups, node, dwell)          # vehicles standing at stops, never longer than 50% of the route headway
        night_on = bool(((ev.kind == "dep") & (ev.t >= 1440) & (ev.t < 1740)).any())     # any departure between 00:00 and 05:00?
        print(f"   {d}: services between 00:00 and 05:00: {night_on}")
        import analysis as _an
        results[d] = dict(alias=dict(_an.ROUTE_ALIAS), night=night_on, node=node, und=und, walk=walk, takt=takt, legs=legs, sym=sym, nmin=nmin, tr=tr, estat=estat, lay=lay, groups=groups, vehkm=vehkm)
        sfx = "" if d == "weekday" else f"_{d}"
        node.assign(group=node.index.map(groups)).to_csv(OUT / f"nodes{sfx}.csv")
        und.to_csv(OUT / f"edges{sfx}.csv", index=False); walk.to_csv(OUT / f"walk_links{sfx}.csv", index=False)
        takt.to_csv(OUT / f"takt_by_node{sfx}.csv", index=False)
        sym.to_csv(OUT / f"symmetry{sfx}.csv", index=False)
        pd_.DataFrame([dict(node=g, band=b, from_line=x[0], to_line=x[1], wait_min=x[2], transfer_min=x[3], frequency=x[4], reversing=x[5])
                       for g, bb in tr.items() for b, rows in bb.items() for x in rows]).to_csv(OUT / f"transfers{sfx}.csv", index=False)
        if _an.DBG_CONN:
            print(f"{d}: pieces that could not be reconnected: " + "; ".join(", ".join(c) for c, _ in _an.DBG_CONN))
        pd_.DataFrame(list(_an.ONEWAY_LOG), columns=["a", "b", "mode", "trips_day", "action"]).to_csv(OUT / f"oneway_links{sfx}.csv", index=False)
        print(f"{d}: one-way links: " + ", ".join(f"{k} {v}" for k, v in pd_.Series([x[4].split(' ')[0] for x in _an.ONEWAY_LOG]).value_counts().items()))
        print(f"{d}: {len(und)} edges, {sym.gid.nunique()} symmetry nodes; veh-km " +
              ", ".join(f"{k} {v:,.0f}" for k, v in vehkm.items()) + (f" (pop {towns.POPULATION:,})" if towns.POPULATION else ""))
        pd_.DataFrame([dict(system=k, veh_km=v, veh_km_per_1000_pop=(v / towns.POPULATION * 1000 if towns.POPULATION else None))
                       for k, v in vehkm.items()]).to_csv(OUT / f"vehicle_km{sfx}.csv", index=False)
    import pickle
    pickle.dump(results, open(OUT / "results.pkl", "wb"))        # cache: code/rebuild_map.py regenerates the page from it in seconds
    (OUT.parent.parent / "maps" / REGION).mkdir(parents=True, exist_ok=True)
    make_map(results, OUT.parent.parent / "maps" / REGION / "index.html")
