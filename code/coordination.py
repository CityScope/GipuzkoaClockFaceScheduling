"""Timetable coordination per node group and time band: symmetry minutes, transfers, departure minutes.

* symmetry: arrivals bunch up to W min BEFORE minute s and departures up to W min AFTER it. Patterns repeat every
  60 / 30 / 15 min (one radius / one diameter / two diameters on the map). Events that do not fit (extra
  departures that are not coordinated) are ignored for the detection and shown greyed in the popups.
* transfers: for every arrival, the earliest departure of each other line that can be reached (walk + 2 min if the
  mode or the station changes); arrival time -> departure time; a vehicle that reverses (same line, back where it
  came from) counts too up to 60 min.
"""
from collections import defaultdict
import numpy as np
import pandas as pd
from towns import (PERIODS, RAIL_SYSTEMS, SYS_NAME, SYM_WINDOW_MIN, SYM_MIN_SHARE, SYM_MIN_LINES, SYM_BUS_MIN_SHARE,
                   SYM_BUS_MIN_LINES, SYM_MIN_EVENTS_BAND, SNAP_MIN, SYM_WINDOW_BUS_ARR, FREQUENT_MIN, FREQ_CUT, COORD_WAIT_SHARE, COORD_BEST_HEADWAY_MIN, TRANSFER_MAX_WAIT, REVERSAL_MAX_WAIT, CHANGE_PENALTY_MIN)
from analysis import in_band

BANDS = list(PERIODS)
CONN_MIN_SHARE = 0.25         # a connection 'works' when at least 25 % of the services (of the less frequent edge) make it ...
CONN_REP_FULL, CONN_REP_HALF = 60, 120   # ... and it repeats every <= 60 min (counts full) or <= 120 min (counts half)


def _band_minutes(per):
    return sum(e - s for s, e in PERIODS[per])


def _members(groups):
    m = defaultdict(list)
    for k, g in groups.items():
        m[g].append(k)
    return m


def _basis(mem, ev, node):
    """Merged node: judge the first system (trains, small trains, buses) that has enough events."""
    if len(mem) == 1:
        return mem
    for sysk in SYS_NAME:
        part = [k for k in mem if node.loc[k, "system"] == sysk]
        if part and ev.node.isin(part).sum() >= 2 * SYM_MIN_EVENTS_BAND:
            return part
    return mem


def _detect(arr, al, dep, dl, MS, ML, aw=None, pmin=15):
    """Best symmetry pattern for arrival/departure minutes (mod 60) or None. Returns dict(hands, period, a, d, lines)."""
    W = SYM_WINDOW_MIN
    AW = W if aw is None else aw                      # arrival window per event (buses: wider, they arrive early)
    ma = lambda s: ((s - arr) % 60) <= AW
    md = lambda s: ((dep - s) % 60) <= W
    a_ = lambda s: float(ma(s).mean())
    d_ = lambda s: float(md(s).mean())
    nl = lambda s: min(len(set(al[ma(s)])), len(set(dl[md(s)])))
    A = np.array([a_(s) for s in range(60)])
    D = np.array([d_(s) for s in range(60)])
    L = np.array([nl(s) for s in range(60)])
    res = {}
    PS = [P for P in (60, 30, 15) if P >= pmin] or [60]
    for P in PS:
        K = 60 // P
        sc = np.zeros(P)
        for s in range(P):
            w = [(s + k * P) % 60 for k in range(K)]
            tot = min(A[w].sum(), D[w].sum())
            per_ok = all(min(A[x], D[x]) >= 0.4 * tot / K for x in w) and all(L[x] >= ML for x in w)
            sc[s] = tot if per_ok else 0.0
        res[P] = sc
    pick = None
    for P in PS:                                 # finer pattern only if it explains at least as much
        if res[P].max() >= MS and (pick is None or res[P].max() >= res[pick].max() * 0.999):
            pick = P
    if pick is None:
        return None
    P = pick; sc = res[P]
    best = sc.max()
    plateau = [s for s in range(P) if sc[s] >= best - 0.02]
    centre = plateau[len(plateau) // 2] if plateau else int(np.argmax(sc))
    dist = lambda x, y: min((x - y) % P, (y - x) % P)
    # round to a multiple of 5 within SNAP_MIN of the best minutes: pick the one that keeps arrivals BEFORE and departures AFTER
    cands = [r for r in range(0, P, 5) if min(dist(r, s) for s in plateau) <= SNAP_MIN]
    K = 60 // P

    def valid(s0):                                      # re-check the pattern at the rounded minutes
        w = [(s0 + k * P) % 60 for k in range(K)]
        return (min(A[w].sum(), D[w].sum()) >= MS and all(L[x] >= ML for x in w)
                and all(min(A[x], D[x]) >= 0.4 * min(A[w].sum(), D[w].sum()) / K for x in w))
    order = sorted(cands, key=lambda r: (-round(float(sc[r]), 3), dist(r, centre)))
    s = next((r for r in order if valid(r)), None)
    if s is None:
        s = centre if valid(centre) else None           # no round minute keeps the pattern: use the exact one, or none
    if s is None:
        return None
    hands = sorted((s + k * P) % 60 for k in range(K))
    return dict(hands=hands, period=P, a=float(sum(A[h] for h in hands)), d=float(sum(D[h] for h in hands)),
                lines=int(min(L[h] for h in hands)))


def symmetry_band(ev, groups, node, coord=None, estat=None):
    """DataFrame(gid, band, hands 'm1,m2', period, arr_share, dep_share, lines, basis) for groups with a clear pattern.
    With `coord` (from transfers()) only arrivals and departures that belong to COORDINATED connections count; without
    it all events of the node (first system with enough events) are used."""
    rows = []
    if estat is not None:                                # symmetry by mode level (see _node_conn)
        for gid, bb in estat.items():
            for per, d in bb.items():
                for k in d.get("sym", []):
                    rows.append(dict(gid=gid, band=per, hands=",".join(map(str, k["h"])), period=k["p"], arr_share=k["both"],
                                     dep_share=k["one"], lines=k["n"], basis=k["lv"], style=k["st"]))
        return pd.DataFrame(rows, columns=["gid", "band", "hands", "period", "arr_share", "dep_share", "lines", "basis", "style"])
    members = _members(groups)
    for gid, mem in members.items():
        busy = all(node.loc[k, "system"] not in RAIL_SYSTEMS for k in mem)
        MS, ML = (SYM_BUS_MIN_SHARE, SYM_BUS_MIN_LINES) if busy else (SYM_MIN_SHARE, SYM_MIN_LINES)
        for per, wins in PERIODS.items():
            if coord is not None:
                cc = coord.get(gid, {}).get(per)
                if not cc:
                    continue
                at, al, dt, dl = cc["at"] % 60, cc["al"], cc["dt"] % 60, cc["dl"]
                aw = np.where(np.isin(cc["asys"], list(RAIL_SYSTEMS)), SYM_WINDOW_MIN, SYM_WINDOW_BUS_ARR)
            else:
                e = ev[ev.node.isin(_basis(mem, ev, node))]
                eb = e[in_band(e.t.values, wins)]
                ea, ed = eb[eb.kind == "arr"], eb[eb.kind == "dep"]
                at, al, dt, dl = ea.t.values % 60, ea.route_key.values, ed.t.values % 60, ed.route_key.values
                aw = None
            if estat is not None:
                # symmetry: of the node's directions with headway >= 15 min, more than half have a connection more than half of the times
                el = [x for x in estat.get(gid, {}).get(per, []) if x[7]]
                if len(el) < 2 or sum(x[8] for x in el) / len(el) <= 0.5:
                    continue
                r = _detect(at, al, dt, dl, MS, ML, aw) or _detect(at, al, dt, dl, 0.0, 1, aw)
                if not r:
                    ang = np.concatenate([at, dt]) * 2 * np.pi / 60
                    mm = int(round(np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) / 6)) % 60
                    r = dict(hands=[mm], period=60, a=0.0, d=0.0, lines=len(set(al)))
                r["a"] = float(np.mean([x[4] for x in el])); r["d"] = float(np.mean([x[6] for x in el]))
            else:
                if len(at) < SYM_MIN_EVENTS_BAND or len(dt) < SYM_MIN_EVENTS_BAND:
                    continue
                r = _detect(at, al, dt, dl, MS, ML, aw)
            if r:
                rows.append(dict(gid=gid, band=per, hands=",".join(map(str, r["hands"])), period=r["period"], arr_share=r["a"],
                                 dep_share=r["d"], lines=r["lines"], basis="coordinated"))
    return pd.DataFrame(rows, columns=["gid", "band", "hands", "period", "arr_share", "dep_share", "lines", "basis"])


def node_minutes(ev, groups, node, sym):
    """{node key: {band: dict(m=[[minute, count, coordinated(1/0)], ...], n=departures, l=lines)}} departure minutes of the hour per node and band.
    Departures outside every symmetry window of the node's group are flagged 0 (shown grey) when the group has a pattern."""
    hands = {}
    for r in sym.itertuples():
        hands.setdefault((r.gid, r.band), []).extend(int(x) for x in str(r.hands).split(","))
    out = {}
    for k in node.index:
        g = groups[k]
        e = ev[(ev.node == k) & (ev.kind == "dep")]
        out[k] = {}
        for per, wins in PERIODS.items():
            eb = e[in_band(e.t.values, wins)]
            m = np.round(eb.t.values).astype(int) % 60
            cnt = pd.Series(m).value_counts().sort_index()
            h = hands.get((g, per))
            out[k][per] = dict(m=[[int(mm), int(c), 1 if (h is None or any((mm - x) % 60 <= SYM_WINDOW_MIN for x in h)) else 0]
                                  for mm, c in cnt.items()], n=int(len(eb)), l=int(eb.route_key.nunique()))
    return out


def _cd(x, y):
    return min((x - y) % 60, (y - x) % 60)


def _fit(hands, at, dt, aw):
    """How well arrivals (before) and departures (after) gather around the given symmetry minutes: min(arr share, dep share)."""
    if not len(at) or not len(dt):
        return 0.0
    a = np.mean([any(((h - x) % 60) <= w for h in hands) for x, w in zip(at % 60, aw)])
    d = np.mean([any(((x - h) % 60) <= SYM_WINDOW_MIN for h in hands) for x in dt % 60])
    return float(min(a, d))


def _hw(t, wins):
    """Headway of all services together (one pooled stream) with the pyGTFSHandler formula over the band windows."""
    from analysis import headway_window
    h, n = headway_window(np.sort(np.asarray(t, float)), wins)
    return float(h) if n else 999.0


COORD_WAIT_RAIL = 6           # a change is coordinated with a wait <= 6 min ...
WEIGHT_MODE = "freq"          # "freq" (60/worse headway), "headway" (worse headway) or "equal" (1; 0 if rarer than THIN_MAX)
THIN_MAX = 120
SYM_GROUP_HW = 60             # a group of timed connections running every <= 60 min always makes a symmetry
SYM_ONE_MIN = 0.5             # a (half) symmetry needs more than this share connected at least one way
WAIT_SHARE_H = 0.0            # test switch: wait limit up to this share of the worse headway (0 = fixed limits)
WAIT_MAX_HUB = 15
COORD_WAIT_BUS = 12           # ... or <= 12 min when arriving by bus (bus -> bus, bus -> train)
SYM_NO_NEED = 0.75            # >= 75 % (weighted) of the relations have a frequent edge: no symmetry needed
GROUP_TOL, GROUP_SEP = 5, 10
DEP_AFTER_MAX = 6             # a connection leaves at most 6 min after the symmetry minute (it arrives at most 6 / 12 min before it)
SYM_PULSE_MAX = 120           # a symmetry's pulses (with a timed connection) must run at least every 120 min
TIMED_MOST = 0.8              # timed services >= 80 % of the departures reached: coordinated without the timed-vs-any comparison
BACK_DEG = 45                 # two edges less than 45 degrees apart lead the same way (a change between them goes back)  # coordinated relations within 5 min (mod 30) form one symmetry; symmetries >= 10 min apart


def _circ(vals, period, w=None):
    a = np.asarray(vals, float) * 2 * np.pi / period
    w = np.ones(len(a)) if w is None else np.asarray(w, float)
    return float(np.degrees(np.arctan2((w * np.sin(a)).sum(), (w * np.cos(a)).sum())) % 360 * period / 360)


def _node_conn(gid, memset, groups, node, A, D, Dall, wk, VMAX, VMIN, wins, bm):
    """Connections between the edges of one node group in one band (see README, "Connections").
    Edge = (neighbour town, mode, station side, fast/slow class). For every direction X -> Y:
      direct options (same vehicle) and change options (wait <= 6 min, <= 12 min arriving by bus; plus the real walk).
      A change counts only if no other option arrives later and leaves earlier, and it gains >= min(30, 25 % Hd) over the
      next direct service. Hd = headway of direct options, Hc = direct + counted changes (pyGTFSHandler formula).
      Coordinated ('c') when >= 2 counted changes, Hc <= Hd / 2 (or no direct service) and 1.5 x mean wait <= headway(Y) / 2.
      'f' = one edge every <= 14 min (no coordination needed), 'n' = services but no coordination.
    Symmetries: hands (h, h + 30) lying inside the timed changes (arrival <= h <= departure), found greedily."""
    tw = node["town"]; sysof = node["system"]
    tlab = node.groupby("town").label.first()
    rank = {k: i for i, k in enumerate(SYS_NAME)}
    side = lambda n: "h" if n in memset else str(groups[n])
    short = lambda rk: str(rk).split(":", 1)[-1].split("@")[0]
    ek = lambda t, n, c: f"{t}¦{sysof[n]}¦{side(n)}¦{c or ''}"      # t = neighbouring NODE (station), not only its town
    A = A.assign(town=A.prev).dropna(subset=["town"])
    D = D.assign(town=D.next).dropna(subset=["town"])
    Dall = Dall.assign(town=Dall.next).dropna(subset=["town"])
    A = A[~A.town.isin(memset)]; D = D[~D.town.isin(memset)]; Dall = Dall[~Dall.town.isin(memset)]   # never a direction into the node itself
    if A.empty or Dall.empty:
        return dict(ep=[], rp=[], sym=[], ce=[])
    A["e"] = [ek(t, n, c) for t, n, c in zip(A.town, A.node, A.cls)]
    D["e"] = [ek(t, n, c) for t, n, c in zip(D.town, D.node, D.cls)]
    Dall["e"] = [ek(t, n, c) for t, n, c in zip(Dall.town, Dall.node, Dall.cls)]
    E = sorted(set(A.e) | set(D.e))
    hA = {e: _hw(A.t[A.e == e], wins) for e in E}
    hD = {e: _hw(D.t[D.e == e], wins) for e in E}
    enode = {}
    for e, n in zip(A.e, A.node): enode[e] = n
    for e, n in zip(Dall.e, Dall.node): enode[e] = n
    town = lambda e: e.split("¦")[0].split("|")[0]                   # municipality of the neighbouring station
    fr = lambda h: h < FREQ_CUT
    # ---- options per direction
    direct = defaultdict(list)                                       # (X, Y) -> [(ta, td)]
    dd = A.merge(Dall[["trip_key", "node", "e", "t"]], on=["trip_key", "node"], suffixes=("", "_d"))
    ownd = {}                                                        # (X, Y, arriving trip) -> its own departure towards Y
    for x, y, ta, td, tk in zip(dd.e, dd.e_d, dd.t, dd.t_d, dd.trip_key):
        if town(x) != town(y) and td >= ta:
            direct[(x, y)].append((ta, td)); ownd[(x, y, tk)] = td
    line_ = lambda rk: str(rk).split("@")[0]                       # feed + line number: S6 to S6 is the same line
    Dg = {y: g.sort_values("t") for y, g in Dall.groupby("e")}
    for x, ga in A.groupby("e"):
        nx_ = enode[x]; bus_in = sysof[nx_] not in RAIL_SYSTEMS
        lim = COORD_WAIT_BUS if bus_in else COORD_WAIT_RAIL
        ta = ga.t.values; tri = ga.trip_key.values; rki = ga.route_key.values
        for y, gd in Dg.items():
            if town(x) == town(y):
                continue
            ny_ = enode[y]
            if nx_ not in memset and ny_ not in memset:
                continue
            if nx_ == ny_:
                tr = 0.0
            elif (nx_, ny_) in wk:
                tr = wk[(nx_, ny_)] + CHANGE_PENALTY_MIN
            else:
                continue
            T = gd.t.values; Tr = gd.trip_key.values; Rk = gd.route_key.values; nT = len(T)
            k = np.searchsorted(T, ta + tr, side="left")
            for _ in range(2):                                       # own vehicle continuing: direct, not a change
                same = (k < nT) & (Tr[np.minimum(k, nT - 1)] == tri)
                k = k + same
            okk = k < nT
            kk = np.minimum(k, nT - 1)
            w = np.where(okk, T[kk] - ta - tr, np.inf)
            limxy = max(lim, min(WAIT_MAX_HUB, WAIT_SHARE_H * max(hA.get(x, 60.0), hD.get(y, 60.0)))) if WAIT_SHARE_H else lim
            sel = np.where(okk & (w <= limxy + 0.5))[0]          # waits compared rounded to the minute (6.4 counts as 6)
            ty, tx = town(y), town(x)
            for j in sel:
                kj = kk[j]
                if line_(rki[j]) == line_(Rk[kj]):
                    direct[(x, y)].append((float(ta[j]), float(T[kj])))   # same line continuing (trip split at the station): direct
                    continue
    nA = A.e.value_counts().to_dict(); hasD = set(Dall.e)
    # bearing of each edge (from its station towards the neighbouring station): two edges less than BACK_DEG apart point the
    # same way, so a "connection" between them means going back -- no coordination is needed for such pairs
    def bear(e):
        nb_ = e.split("¦")[0]; st0 = enode.get(e)
        if nb_ not in node.index or st0 is None:
            return None
        la0, lo0 = node.lat[st0], node.lon[st0]; la1, lo1 = node.lat[nb_], node.lon[nb_]
        return float(np.degrees(np.arctan2((lo1 - lo0) * np.cos(np.radians(la0)), la1 - la0)) % 360)
    BR = {e: bear(e) for e in E}
    sameway = lambda x, y: BR[x] is not None and BR[y] is not None and min((BR[x] - BR[y]) % 360, (BR[y] - BR[x]) % 360) < BACK_DEG
    # waits computed from the timetable: actual (every arrival, next departure on another vehicle, any wait) and
    # "without timing" (arrival times shifted by 1..59 min against the real departures)
    TA = {x: g.sort_values("t") for x, g in A.groupby("e")}
    def waits(x, y):
        """Real timetable, ALL services (no timing assumed): every arrival from x takes the first departure towards y
        (the same vehicle continuing included); when several arrivals catch the same departure only the latest counts
        (nobody comes earlier just to wait longer). Returns (mean wait of these trips, their headway, walk)."""
        nx_, ny_ = enode.get(x), enode.get(y)
        tr = 0.0 if nx_ == ny_ else (wk[(nx_, ny_)] + CHANGE_PENALTY_MIN if (nx_, ny_) in wk else None)
        if tr is None or x not in TA or y not in Dg:
            return None, None, None
        ta = TA[x].t.values; tri = TA[x].trip_key.values; rka = TA[x].route_key.values
        T = Dg[y].t.values; nT = len(T); rkd = Dg[y].route_key.values; trd = Dg[y].trip_key.values
        k = np.searchsorted(T, ta + tr)
        best = {}                                        # departure time -> (latest arrival catching it, wait)
        alts = defaultdict(list)                         # departure time -> every change arrival catching it
        for j in range(len(ta)):
            own = ownd.get((x, y, tri[j]))
            if own is not None:                          # the same vehicle continues towards y: wait 0
                d_, w_ = own, 0.0
            elif k[j] < nT:
                d_ = T[k[j]]; w_ = d_ - ta[j] - tr
                if line_(rka[j]) == line_(rkd[k[j]]):
                    own, w_ = d_, 0.0                    # the same line continuing under a new trip number: direct
            else:
                continue
            if w_ > 180:                                 # waits beyond 3 h run past the end of service
                continue
            if not in_band(np.array([d_]), wins)[0]:     # departures inside the time band only (as for the timed changes)
                continue
            if own is None:
                alts[d_].append((float(ta[j]), float(d_), float(w_), tr, rka[j], rkd[k[j]], tri[j], trd[k[j]]))
            if d_ not in best or ta[j] > best[d_][0]:
                best[d_] = (ta[j], w_, own is not None,
                            None if own is not None else (float(ta[j]), float(d_), float(w_), tr, rka[j], rkd[k[j]], tri[j], trd[k[j]]))
        if not best:
            return None, None, tr
        waits.alldirect = all(v[2] for v in best.values())        # every trip is the same vehicle continuing
        waits.nall = len(best)                                   # departures reached (one per departure)
        waits.ndir = sum(1 for v in best.values() if v[2])      # of which direct (same vehicle / same line, wait 0)
        waits.ddir = [float(k_) for k_, v in best.items() if v[2]]   # their departure times
        waits.opts = [v[3] for v in best.values() if v[3] is not None]   # the changes among them (for the change minutes)
        waits.optsets = [sorted(alts[k_]) for k_, v in best.items() if v[3] is not None]   # all arrivals catching each of them
        return float(np.mean([v[1] for v in best.values()])), _hw(np.array(sorted(best)), wins), tr
    nDb = {y: int(in_band(g.t.values, wins).sum()) for y, g in Dg.items()}   # departures towards y in the band
    st_ = {}
    for x in E:
        for y in E:
            if x == y or town(x) == town(y) or not nA.get(x) or y not in hasD or sameway(x, y):
                continue
            if (x.split("¦")[2] != "h") and (y.split("¦")[2] != "h"):
                continue
            _hw_ = max(hA[x], hD[y])
            wgt = (60.0 / _hw_ if WEIGHT_MODE == "freq" else min(240.0, _hw_) if WEIGHT_MODE == "headway"
                   else (1.0 if _hw_ <= THIN_MAX else 0.0))   # "equal": every pair counts 1, directions rarer than every 120 min not at all
            dr = sorted(direct.get((x, y), []))
            Hd = _hw([b for _, b in dr], wins) if dr else 999.0
            waits.alldirect = False
            _wall, _hall, _tr = waits(x, y)              # the relation itself, all services, real timetable
            if _hall is not None and _hall < FREQ_CUT:  # frequent = the RELATION runs more often than every 15 min
                st_[(x, y)] = dict(k="f", w=wgt, Hd=Hd, Hc=None, C=[], share=None, wait=None, walk=None)
                continue
            if _hall is not None and waits.alldirect:    # only direct services (same vehicle): nothing to time
                st_[(x, y)] = dict(k="d", w=wgt, Hd=_hall, Hc=None, C=[], share=None, wait=None, walk=None, alld=True)
                continue
            # ---- the relation, measured on the real timetable (all services): every arrival from x takes the first
            # departure towards y it can reach (same vehicle = wait 0). Candidate connections: per departure every arrival
            # that catches it within limit + 6 min; whether they are connections is decided at a symmetry minute (fit + use).
            limw = COORD_WAIT_RAIL if sysof[enode[x]] in RAIL_SYSTEMS else COORD_WAIT_BUS
            if _wall is None:
                st_[(x, y)] = dict(k="n", w=wgt, Hd=Hd, Hc=None, C=[], share=None, wait=None, walk=None)
                continue
            # a connection arrives at most limw (6, 12 by bus) + walk before the symmetry minute and leaves at most 6 min
            # after it: its wait (walk not included) is at most limw + 6
            C, CS = [], []                                              # per departure: latest candidate, all candidates
            for cs in waits.optsets:
                cs = [o for o in cs if o[2] <= limw + DEP_AFTER_MAX]
                if cs:
                    C.append(cs[-1]); CS.append(cs)
            rep_ = 2 if min(nA.get(x, 0), nDb.get(y, 0)) >= 2 else 1  # it repeats (a line with one service in the band: once)
            Hc = _hw([b for _, b in dr] + [c[1] for c in C], wins) if (dr or C) else 999.0
            if dr and not Hc < Hd:                                      # the changes add nothing to the direct trips
                st_[(x, y)] = dict(k="d", w=wgt, Hd=Hd, Hc=None, C=[], share=None, wait=None, walk=None)
                continue
            ok = len(C) >= rep_                                         # judged in the symmetry search (fit + use)
            st_[(x, y)] = dict(k="c" if ok else "n", w=wgt, Hd=Hd, Hc=Hc if C else _hall, C=C if ok else [], CS=CS if ok else [], rep=rep_,
                               hDy=hD[y], share=len(C) / nA[x], lim=limw, nall=waits.nall, ndir=waits.ndir, ddir=waits.ddir, hall=_hall,
                               dirdep=[float(b) for _, b in dr if in_band(np.array([b]), wins)[0]],
                               wait=_wall, walk=float(np.median([c[3] for c in C])) if C else _tr)
    # ---- symmetries: hands inside the timed changes of the coordinated directions
    need = {d: v for d, v in st_.items() if v["k"] not in ("f", "d")}     # directions that need coordination
    tot = sum(v["w"] for v in st_.values()) or 1.0
    sym, gof = [], {}
    if st_ and sum(v["w"] for v in st_.values() if v["k"] == "f") / tot < SYM_NO_NEED:
        # A symmetry minute (hand) h is a minute of the hour at which the timed changes take place: every timed change of
        # the symmetry ARRIVES AT OR BEFORE h and LEAVES AT OR AFTER h (minutes rounded). A coordinated relation belongs to
        # the symmetry when this holds for >= 2 of its changes and for at least half of them (it repeats). Symmetries are
        # searched greedily: the hand pair (h, h + 30) that fits the most relations (weighted), then the most changes, then
        # a multiple of 5, then the hand in the middle of the changes; its relations are taken out and the next
        # symmetry (hands >= GROUP_SEP min from the previous ones) is searched among the rest.
        cd_ = {d: v for d, v in need.items() if v["k"] == "c"}
        def fit1(d, o, h):
            """Change o (one arrival -> departure) is a connection at symmetry minute h: it arrives at or before h, at most
            the limit (6 min, 12 by bus) + walk before, and leaves at or after h, at most 6 min after (minutes rounded)."""
            a, b = int(round(o[0])), int(round(o[1]))
            off = (h - a) % 60
            return off <= b - a and off <= cd_[d]["lim"] + (o[3] or 0.0) + 0.5 and (b - a) - off <= DEP_AFTER_MAX

        def choose(d, hs):
            """Per departure of relation d: the latest arrival that connects to it at one of the hands (or None)."""
            out = []
            for cs in cd_[d]["CS"]:
                ok_ = [o for o in cs if any(fit1(d, o, h) for h in hs)]
                out.append(ok_[-1] + (cs[-1][2],) if ok_ else None)   # [8] = real wait: passengers take the latest arrival
            return out

        def pays(d, ch):
            """Are the timed changes ch of any use? Timed = direct trips (wait 0) + ch; normal = every departure reached
            (direct trips + all changes). The timed changes must wait less than half the departing headway, at least halve
            the headway of the direct trips (if any); then either they are >= 80 % of the departures, or the wait they
            save pays for the headway they lose: (H_timed - H_all) / 2 <= wait_all - wait_timed (formula headways)."""
            v = cd_[d]
            if not ch or float(np.mean([c[8] for c in ch])) >= v["hDy"] / 2:
                return False
            dep = sorted(set(v["ddir"]) | set(v["dirdep"]) | {c[1] for c in ch})
            ht = _hw(dep, wins)
            if v["dirdep"] and ht > _hw(sorted(v["dirdep"]), wins) / 2:
                return False
            if len(dep) >= TIMED_MOST * v["nall"]:
                return True
            wt = sum(c[8] for c in ch) / len(dep)
            return (ht - min(ht, v["hall"])) / 2 <= v["wait"] - wt + 1e-9

        def rel_fit(d, hs):
            """The connections of relation d at the hands (list per departure, None = not connected), or None when d is
            not coordinated there (fewer than it repeats, or of no use)."""
            ch = choose(d, hs)
            got_ = [c for c in ch if c is not None]
            return ch if (len(got_) >= cd_[d]["rep"] and pays(d, got_)) else None

        nfit = lambda ch: sum(1 for c in ch if c is not None)

        def slack(d, hs, ch):                                     # how central the hands lie in the connections
            s_ = 0
            for c in ch:
                if c is not None:
                    a, b = int(round(c[0])), int(round(c[1]))
                    s_ += max(min((h - a) % 60, (b - a) - (h - a) % 60) if fit1(d, c, h) else -99 for h in hs)
            return s_

        def best_for(hs, pool):
            got = {d: rel_fit(d, hs) for d in pool}
            got = {d: f for d, f in got.items() if f is not None}
            return got, (round(sum(cd_[d]["w"] for d in got), 6), sum(nfit(f) for f in got.values()))

        groups_ = []                                                  # [hands, weight, [directions], {direction: fit mask}]
        pool = set(cd_)
        while len(pool) >= 2:
            cands = []
            for h0 in range(30):
                if any(min((h0 - x) % 30, (x - h0) % 30) < GROUP_SEP for g in groups_ for x in g[0]):
                    continue
                got, sc = best_for((h0, h0 + 30), pool)
                if len(got) < 2:
                    continue
                cands.append((sc, h0, got))
            if not cands:
                break
            top = max(c[0] for c in cands)
            # period: both hands (every 30 min) when each of them carries >= 20 % of the fitting changes, else the busier one
            sc, h0, got = next(c for c in cands if c[0] == top)
            cands = [c for c in cands if c[0][0] == top[0]]          # the same relations (weight); changes may differ
            nh = [sum(nfit(choose(d, (h,))) for d in got) for h in (h0, h0 + 30)]
            two = min(nh) >= 0.2 * sum(nh)
            pick = []
            for sc, h0, got in cands:
                if two:
                    hs = (h0, h0 + 30)
                else:
                    nh_ = [sum(nfit(choose(d, (h,))) for d in got) for h in (h0, h0 + 30)]
                    hs = (h0,) if nh_[0] >= nh_[1] else (h0 + 30,)
                g2, sc2 = best_for(hs, pool)
                if len(g2) < 2:
                    continue
                rnd = 2 if hs[0] % 15 == 0 else 1 if hs[0] % 10 == 0 else 0   # same services: prefer :00/:15/:30/:45, then :10/:20/...
                pick.append(((sc2, rnd, sum(slack(d, hs, f) for d, f in g2.items())), hs, g2))
            if not pick:
                break
            best = max(pick, key=lambda z: z[0])
            # a rounder minute (:00/:15/:30/:45, then :10/:20/:40/:50) with the same relations is taken when no relation's
            # timed headway gets more than 10 % (at least 3 min) worse
            th = lambda d, f: _hw(sorted(set(cd_[d]["ddir"]) | set(cd_[d]["dirdep"]) | {c[1] for c in f if c is not None}), wins)
            hb = {d: th(d, f) for d, f in best[2].items()}
            alt = [z for z in pick if z[0][1] > best[0][1] and set(z[2]) == set(best[2])
                   and all(th(d, f) <= hb[d] + max(3.0, 0.1 * hb[d]) for d, f in z[2].items())]
            _, hs, got = max(alt, key=lambda z: (z[0][1], z[0][0], z[0][2])) if alt else best
            groups_.append([list(hs), sum(cd_[d]["w"] for d in got), list(got), got])
            pool -= set(got)
        for d in pool:                                                # left over (in no symmetry): coordinated only if some symmetry
            fbest = None                                              # minute would make it a connection that is of use
            for h in range(60):
                fb = rel_fit(d, (h,))
                if fb is not None and (fbest is None or nfit(fb) > nfit(fbest)):
                    fbest = fb
            if fbest is None:
                st_[d].update(k="n", C=[])
            else:
                st_[d]["C"] = [c for c in fbest if c is not None]
        for d in cd_:                                                 # the timed changes of a relation in a symmetry: those that fit it
            for g in groups_:
                if d in g[3]:
                    cd_[d]["C"] = [c for c in g[3][d] if c is not None]
            v = cd_[d]                                                # shown: headway (formula) and mean wait of direct + timed
            if v["k"] == "c" and v["C"]:
                dep = sorted(set(v["ddir"]) | set(v["dirdep"]) | {c[1] for c in v["C"]})
                v["Hc"] = _hw(dep, wins); v["wt"] = sum(c[8] if len(c) > 8 else c[2] for c in v["C"]) / len(dep)
        groups_.sort(key=lambda g: -g[1])
        for gi, (hands, wsum, dirs, _fm) in enumerate(groups_):
            if len(dirs) < 2:
                continue
            GE = {e for d in dirs for e in d}
            pairs = {tuple(sorted(d)) for d in need if d[0] in GE and d[1] in GE}
            wpair = lambda p: max(st_.get(p, {}).get("w", 0), st_.get(p[::-1], {}).get("w", 0))
            # a direction "works" if it is connected in this symmetry, needs no coordination (frequent / served directly)
            # or has no service at all (one-way relation); a pair is counted if at least one direction needs coordination
            works = lambda d: d in dirs or d not in st_ or st_[d]["k"] in ("c", "f", "d")   # timed here or in another pulse of the node
            timed = lambda d: d in dirs
            W = sum(wpair(p) for p in pairs) or 1.0
            both = sum(wpair(p) for p in pairs if works(p) and works(p[::-1])) / W
            one = sum(wpair(p) for p in pairs if timed(p) or timed(p[::-1])) / W
            ghw = float(np.median([st_[d]["Hc"] for d in dirs if st_[d]["Hc"] is not None] or [999]))
            regular = ghw <= SYM_GROUP_HW + 0.5               # the group's timed connections run every <= 60 min
            # a symmetry needs at least one timed change between two NON-frequent edges (a node whose only timed changes
            # involve a frequent line, < 15 min, is not symmetric); its >= 2 directions and >= 3 distinct neighbouring
            # places count all its timed changes
            nfe = lambda e: min(hA.get(e, 999.0), hD.get(e, 999.0)) >= FREQ_CUT
            dnf = [d for d in dirs if nfe(d[0]) and nfe(d[1])]
            nbs = {str(node.label.get(e.split("¦")[0], e.split("¦")[0])) for d in dirs for e in d}   # distinct neighbouring places (fast / slow, walk sides and modes of one place count once)
            if not dnf or len(dirs) < 2 or len(nbs) < 3 or (one <= SYM_ONE_MIN and not regular):
                continue                                       # >= 3 edges; more than half one way, or a regular (<= 60 min) group
            modes = sorted({e.split("¦")[1] for e in GE}, key=lambda s_: rank[s_])
            # how often the pulse really runs: headway of the pulses (hand times) with at least one timed connection
            P_ = 30 if len(set(hands)) > 1 else 60
            Ts = set()
            for d in dirs:
                for c in st_[d]["C"]:
                    hh = [h for h in hands if fit1(d, c, h)]
                    if hh:
                        a_ = int(round(c[0])); Ts.add(a_ + min((h - a_) % 60 for h in hh))
            ph = max(P_, round(_hw(sorted(Ts), wins))) if Ts else P_
            if ph > SYM_PULSE_MAX:                             # timed connections rarer than every 2 h: not a symmetry
                continue
            idx = len(sym)
            for d in dirs:
                gof[d] = idx
            sym.append(dict(h=sorted(set(hands)), p=P_, ph=ph if ph < 999 else None, st="solid" if both > 0.5 else "dotted",
                            lv=" + ".join(SYS_NAME[m] for m in modes), both=round(both, 2), one=round(one, 2), n=len(pairs),
                            w=round(wsum / tot, 2)))
    # ---- display rows
    rh = lambda h: None if h is None or h >= 999 else round(h)
    clsn = {"fast": " (fast)", "slow": " (slow)", "": ""}
    lab = lambda e: (lambda t, s_, w_, c_: [str(node.label.get(t, t)) + clsn.get(c_, ""), s_, 0 if w_ == "h" else 1, [rh(hA[e]), rh(hD[e])]])(*e.split("¦"))
    short_ = lambda rk: str(rk).split(":", 1)[-1].split("@")[0]
    lines_of = {}
    for e in E:                                        # lines on each edge with their own headway (in or out, the better)
        hh = {}
        for src in (A[A.e == e], D[D.e == e]):
            for rk_, g in src.groupby("route_key"):
                h_ = _hw(g.t.values, wins)
                if h_ < 999:
                    hh[rk_] = min(hh.get(rk_, 999.0), h_)
        lines_of[e] = sorted(([short_(k_), round(h_)] for k_, h_ in hh.items()), key=lambda z: z[1])
    def cell(d):
        if d not in st_:
            return None
        v = st_[d]
        waits.alldirect = False
        wall, hall, tr = waits(*d)
        used_in = sorted({short_(c[4]) for c in v["C"]}); used_out = sorted({short_(c[5]) for c in v["C"]})
        return [v["k"], None if v["share"] is None else round(min(1, v["share"]), 2), rh(v["Hd"]), rh(v["Hc"]),
                None if v["wait"] is None else round(v.get("wt", v["wait"]), 1), None if v["walk"] is None else round(v["walk"], 1),
                gof.get(d, -1), len(v["C"]),
                None if wall is None else round(wall, 1), None if wall is None else round(wall, 1),
                rh(hall) if hall is not None else None, used_in, used_out, None if tr is None else round(tr, 1),
                1 if v.get("alld") else 0]
    cat = lambda e1, e2: (max(rank[e1.split("¦")[1]], rank[e2.split("¦")[1]]), min(rank[e1.split("¦")[1]], rank[e2.split("¦")[1]]))
    seen, ep = set(), []
    for (x, y) in st_:
        p = tuple(sorted((x, y)))
        if p in seen:
            continue
        seen.add(p)
        ab, ba = cell((p[0], p[1])), cell((p[1], p[0]))
        kk = [d[0] for d in (ab, ba) if d]
        score = (0 if "c" in kk else 1 if "n" in kk else 2)                # connected first, then not timed, then direct / frequent
        wmin = min([d[4] for d in (ab, ba) if d and d[4] is not None] or [99])
        hwp = max(hA[p[0]], hD[p[0]], hA[p[1]], hD[p[1]]) if False else max(min(hA[p[0]], hD[p[0]]), min(hA[p[1]], hD[p[1]]))
        ep.append((cat(*p), score, hwp, lab(p[0]) + lab(p[1]) + [ab, ba, lines_of.get(p[0], []), lines_of.get(p[1], [])]))
    # pairs of edges leading the same way (< BACK_DEG apart): a change between them goes back; listed, not counted
    BK = ["b", None, None, None, None, None, -1, 0, None, None, None, [], [], None, 0]
    for x in E:
        for y in E:
            if not (x < y) or town(x) == town(y) or not sameway(x, y) or (x.split("¦")[2] != "h" and y.split("¦")[2] != "h"):
                continue
            p = (x, y)
            if p in seen:
                continue
            seen.add(p)
            ab = BK if (nA.get(x) and y in hasD) else None; ba = BK if (nA.get(y) and x in hasD) else None
            if ab is None and ba is None:
                continue
            hwp = max(min(hA[x], hD[x]), min(hA[y], hD[y]))
            ep.append((cat(x, y), 3, hwp, lab(x) + lab(y) + [ab, ba, lines_of.get(x, []), lines_of.get(y, [])]))
    ep = [r for *_, r in sorted(ep, key=lambda z: z[:3])][:80]
    rp_d = defaultdict(list)
    for d, v in st_.items():
        if v["k"] != "c":
            continue
        for c in v["C"]:
            rp_d[((short(c[4]), d[0]), (short(c[5]), d[1]))].append(c)
    rcell = lambda cs, d: None if not cs else ["c", None, None, None, round(float(np.mean([c[2] for c in cs])), 1),
                                              round(float(np.median([c[3] for c in cs])), 1), gof.get(d, -1), len(cs)]
    seen, rp = set(), []
    for (X, Y), cs in rp_d.items():
        k = tuple(sorted([X, Y]))
        if k in seen:
            continue
        seen.add(k)
        lo, hi = k
        f_ = rp_d.get((lo, hi)); b_ = rp_d.get((hi, lo))
        rl = lambda q: [q[0] + " · " + lab(q[1])[0], q[1].split("¦")[1]]
        rp.append((cat(lo[1], hi[1]), -(len(f_ or []) + len(b_ or [])), rl(lo) + rl(hi) + [rcell(f_, (lo[1], hi[1])), rcell(b_, (hi[1], lo[1]))]))
    rp = [r for *_, r in sorted(rp, key=lambda z: z[:2])][:40]
    # "coordinated only": edges (own station) and trips that belong to a symmetry group
    sdirs = [d for d, gi in gof.items() if gi < len(sym)]
    ce = sorted({e.rsplit("¦", 2)[0] for d in sdirs for e in d if e.split("¦")[2] == "h"})
    strips = sorted({t_ for d in sdirs for c in st_[d]["C"] for t_ in (c[6], c[7])})
    # ---- small network diagram of the node: its stations (+ walk times) and its directions, with per-symmetry timing
    mem_l = sorted(memset)
    stl = [[k_, str(node.label.get(k_, k_)), sysof[k_], round(float(node.lat[k_]), 5), round(float(node.lon[k_]), 5)] for k_ in mem_l]
    wkl = [[i, j, round(wk[(mem_l[i], mem_l[j])])] for i in range(len(mem_l)) for j in range(i + 1, len(mem_l)) if (mem_l[i], mem_l[j]) in wk]
    circ = lambda ts: _circ([t % 60 for t in ts], 60)
    def timing(ts, hands, before, floor=None):
        """Most common minutes past the hour (up to 2: e.g. 57 and 27 for a 30-min line) and the headway."""
        if not ts:
            return None
        mins = pd.Series([int(round(t)) % 60 for t in ts]).value_counts()
        top = []
        for m_ in mins.index:                       # merge minutes within 2 min of an already chosen one
            if all(min((m_ - t_) % 60, (t_ - m_) % 60) > 2 for t_ in top):
                top.append(int(m_))
            if len(top) == 2:
                break
        # headway of the symmetry services: services of one direction in the same pulse (e.g. an S-Bahn and an IR arriving
        # a few minutes apart before :00) are one service of that pulse -> never better than the pulse period
        # measured in pulses: each service belongs to the nearest pulse of the symmetry (hand + k x period); a pulse counts
        # once -> the headway of the symmetry services is never better than the symmetry period
        per_ = 30 if len(set(hands)) > 1 else 60
        h0 = min(hands) % per_
        first_ = {}
        for t_ in sorted(ts):                         # real time of the first service of each pulse (band edges stay right)
            first_.setdefault(round((t_ - h0) / per_), t_)
        return [sorted(top), None, rh(max(per_, floor or 0, _hw(sorted(first_.values()), wins)))]   # never better than the symmetry's pulses
    sym_dirs = defaultdict(list)
    for d, gi in gof.items():
        sym_dirs[gi].append(d)
    edl = {}
    for e in E:
        nbk, sy_, sd_, cl_ = e.split("¦")
        if e not in enode:
            continue
        wk_ = None
        if sd_ != "h":                              # direction served at a walk partner (other node): drawn only if used in a symmetry
            ws_ = [wk[(m_, enode[e])] for m_ in mem_l if (m_, enode[e]) in wk]
            if not ws_:
                continue
            wk_ = round(min(ws_))
        key = (enode[e], nbk, sy_)
        rec = edl.setdefault(key, dict(i=mem_l.index(enode[e]) if enode[e] in mem_l else -1, nb=str(node.label.get(nbk, nbk)), sy=sy_, wk=wk_,
                                       via=None if wk_ is None else str(node.label.get(enode[e], enode[e])),
                                       la=round(float(node.lat[nbk]), 5) if nbk in node.index else None,
                                       lo=round(float(node.lon[nbk]), 5) if nbk in node.index else None, ln={}, g={}, keys=[]))
        rec["keys"].append(e)
        rec["hi"] = min(rec.get("hi", 999.0), hA[e]); rec["ho"] = min(rec.get("ho", 999.0), hD[e])   # edge headways (all lines)
        for l_, h_ in lines_of.get(e, []):
            rec["ln"][l_] = min(rec["ln"].get(l_, 999), h_)
    for gi, dirs_ in sym_dirs.items():
        hands = sym[gi]["h"] if gi < len(sym) else []
        if not hands:
            continue
        for key, rec in edl.items():
            ks = set(rec["keys"])
            ins = {c[6]: (c[0], short_(c[4])) for d in dirs_ if d[0] in ks for c in st_[d]["C"]}
            outs = {c[7]: (c[1], short_(c[5])) for d in dirs_ if d[1] in ks for c in st_[d]["C"]}
            if not ins and not outs:
                continue
            fl_ = sym[gi].get("ph") if gi < len(sym) else None
            ti = timing([v[0] for v in ins.values()], hands, True, fl_); to = timing([v[0] for v in outs.values()], hands, False, fl_)
            wks = [c[3] or 0 for d in dirs_ if d[0] in ks or d[1] in ks for c in st_[d]["C"]]   # walk of its timed changes (median: most of them)
            rec["g"][gi] = [ti, to, sorted({v[1] for v in ins.values()} | {v[1] for v in outs.values()}),
                            round(float(np.median(wks))) if wks else 0]
    net = dict(st=stl, wk=wkl, ed=[[r_["i"], r_["nb"], r_["sy"], r_["la"], r_["lo"], sorted(([l_, h_] for l_, h_ in r_["ln"].items()), key=lambda z: z[1]),
                                    {str(k_): v_ for k_, v_ in r_["g"].items()}, rh(r_.get("hi", 999.0)), rh(r_.get("ho", 999.0)), r_["wk"], r_["via"]]
                                   for r_ in edl.values() if r_["la"] is not None and (r_["wk"] is None or r_["g"])])
    return dict(ep=ep, rp=rp, sym=sym, ce=ce, trips=strips, net=net)


def _cd30(x, y):
    return min((x - y) % 30, (y - x) % 30)


_W = {}                                                     # shared data for the worker processes (inherited by fork)


def _group_conn(gid):
    """Connection analysis of one node group for all bands (run in a worker process)."""
    ev, groups, node, wk, VMAX, VMIN, members, arr_all, dep_all = (_W[k] for k in
        ("ev", "groups", "node", "wk", "VMAX", "VMIN", "members", "arr_all", "dep_all"))
    memset = set(members[gid])
    nb_ = {b for a_, b in wk if a_ in memset} - memset
    arrs = arr_all[arr_all.node.isin(memset | nb_)]
    deps = dep_all[dep_all.node.isin(memset | nb_)]
    if arrs.empty or deps.empty:
        return gid, None, None
    out, est = {}, {}
    for per, wins in PERIODS.items():
        a = arrs[in_band(arrs.t.values, wins)]
        dB = deps[in_band(deps.t.values, wins)]
        if a.empty:
            out[per] = []
            continue
        r = _node_conn(gid, memset, groups, node, a, dB, deps, wk, VMAX, VMIN, wins, _band_minutes(per))
        est[per] = r
        out[per] = [[x[0], x[4], x[8][4] if x[8] else None, x[8][5] if x[8] else None,
                     f"direct {x[8][2]} / with changes {x[8][3]}" if x[8] else "", False, x[1], x[5]]
                    for x in r["ep"] if x[8] and x[8][0] == "c"]
    return gid, out, est


def transfers(ev, groups, node, walk):
    """Per node group and band: connection analysis (_node_conn), in parallel over the CPU cores.
    Returns (rows for the CSV, {}, used nodes, estat)."""
    import multiprocessing as mp, os
    wk = {}
    for r in walk.itertuples():
        wk[(r.a, r.b)] = wk[(r.b, r.a)] = float(r.walk_min)
    _v = ev[["trip_key", "node", "t"]].assign(town=ev.node.map(node["town"])).dropna(subset=["town"])
    _vg = _v.groupby(["trip_key", "town"]).t.agg(["min", "max"])
    _W.update(ev=ev, groups=groups, node=node, wk=wk, VMAX=_vg["max"].to_dict(), VMIN=_vg["min"].to_dict(),
              members=_members(groups), arr_all=ev[ev.kind == "arr"], dep_all=ev[ev.kind == "dep"])
    gids = list(_W["members"])
    nproc = min(os.cpu_count() or 1, 12)
    if nproc > 1 and len(gids) > 20:
        with mp.get_context("fork").Pool(nproc) as pool:
            res = pool.map(_group_conn, gids, chunksize=max(1, len(gids) // (nproc * 4)))
    else:
        res = [_group_conn(g) for g in gids]
    out, estat = {}, {}
    for gid, o, e in res:
        if o is None:
            continue
        out[gid] = o
        if e:
            estat[gid] = e
    _W.clear()
    return out, {}, set(), estat


def layovers(ev, groups, node):
    """Vehicles that wait at a terminus and go back: [(gid, system, t_arrival, t_departure)] when the return departure
    (same line, back to where it came from, another trip) is less than REVERSAL_MAX_WAIT minutes after the arrival."""
    out = []
    for gid, mem in _members(groups).items():
        e = ev[ev.node.isin(mem)]
        A = e[(e.kind == "arr") & e.next.isna() & e.prev.notna()]
        D = e[e.kind == "dep"]
        if A.empty or D.empty:
            continue
        for (rk, nd, pv), ga in A.groupby(["route_key", "node", "prev"]):
            gd = D[(D.route_key == rk) & (D.node == nd) & (D.next == pv)].sort_values("t")
            Td, Tr = gd.t.values, gd.trip_key.values
            used = np.zeros(len(Td), bool)
            for t, tr in sorted(zip(ga.t.values, ga.trip_key.values)):
                ix = int(np.searchsorted(Td, t))
                while ix < len(Td) and (used[ix] or Tr[ix] == tr):
                    ix += 1
                if ix < len(Td) and Td[ix] - t < REVERSAL_MAX_WAIT:
                    used[ix] = True
                    out.append((gid, node.loc[nd, "system"], float(t), float(Td[ix]), rk, nd, pv))
    return out


def route_intervals(ev):
    """{(route, node, next stop): median gap between its departures in that direction (<= 3 h), default 60 min}."""
    out = {}
    for (rk, nd, nx), g in ev[ev.kind == "dep"].groupby(["route_key", "node", "next"]):
        gp = np.diff(np.sort(g.t.values)); gp = gp[(gp > 0) & (gp <= 180)]
        out[(rk, nd, nx)] = float(np.median(gp)) if len(gp) else 60.0
    return out


STOP_SHOW_MAX = 10.0                                                  # minutes: longer stops are not drawn as standing vehicles


def stopped(ev, groups, node, dwell, max_share=0.5):
    """Vehicles shown standing at a stop for the video: waiting to reverse (< 60 min) and standing at intermediate stops.
    A vehicle is never left stopped for longer than max_share (50%) of its route's headway at that stop."""
    iv = route_intervals(ev)
    rows = list(layovers(ev, groups, node)) + [(groups[x.node], x.mode, float(x.t0), float(x.t1), x.rk, x.node, x.nx) for x in dwell.itertuples()]
    out = []
    best = {}                                                        # headway of the best (most frequent) line stopping at each station
    for (rk_, nd_, dn_), h_ in iv.items():
        g_ = groups.get(nd_)
        if g_ is not None:
            best[g_] = min(best.get(g_, 1e9), h_)
    for gid, sy, t0, t1, rk, nd, dn in rows:                         # dn = stop the vehicle leaves towards
        h = iv.get((rk, nd, dn), 60.0)
        t1c = min(t1, t0 + max_share * h, t0 + best.get(gid, h))   # never longer than the best line's headway at the station
        if t1c - t0 >= 0.9 and t1c >= t1 - 0.01 and t1 - t0 <= STOP_SHOW_MAX:      # long layovers: the vehicle just disappears on arrival / appears at departure
            out.append((gid, sy, t0, t1c, h < FREQ_CUT, t1c < t1 - 0.01, nd, dn))   # flag: disappears at t1c; nd -> dn = the link it leaves on
    return out
