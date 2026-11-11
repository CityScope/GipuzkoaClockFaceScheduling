"""Interactive MapLibre GL map (OpenFreeMap vector tiles, no CARTO). Self-contained HTML.
Features: day-type / time-band / travel-time buttons, merged multi-coloured nodes (stations of different
systems close together), symmetry-minute hand on node circles, and a video mode (vehicles + clock)."""
import json
from pathlib import Path
import numpy as np

import towns
from towns import SYSTEMS, TITLE, MAP_CENTER, MAP_ZOOM, BOUNDARY_FILE, POPULATION

ROOT = Path(__file__).parent.parent
VENDOR = Path(__file__).parent / "vendor"
STYLE = "https://tiles.openfreemap.org/styles/positron"
SYS_KEYS = list(SYSTEMS)


def _chips(txt, cls="chip"):
    return "".join(f'<span class="{cls}">{c.strip().split(":", 1)[-1].split("@")[0]}</span>' for c in str(txt).split(",") if c.strip())


def _band(k):
    f = lambda t: f"{(t // 60) % 24:02d}:{t % 60:02d}"
    return ", ".join(f"{f(a)}–{f(b)}" for a, b in towns.PERIODS[k])


def _num(x, nd=1):
    x = float(x)
    return None if not np.isfinite(x) else round(x, nd)


def _features(r):
    node, und, walk, legs, sym, nmin, trs, groups = (r[k] for k in ("node", "und", "walk", "legs", "sym", "nmin", "tr", "groups"))
    BANDS = ("peak", "day", "night")
    members = {}
    for k, g in groups.items():
        members.setdefault(g, []).append(k)
    gpos = {g: (float(node.loc[m, "lon"].mean()), float(node.loc[m, "lat"].mean())) for g, m in members.items()}
    gids = list(members)
    def _nm(g):
        labs = list(dict.fromkeys(node.loc[members[g], "label"]))
        towns_ = list(dict.fromkeys(node.loc[members[g], "town"]))
        return (DISPLAY_T(towns_[0]) if len(towns_) == 1 else " + ".join(labs)) if len(labs) > 1 else labs[0]
    DISPLAY_T = lambda t: towns.DISPLAY.get(t, t) if hasattr(towns, "DISPLAY") else t
    names = {g: _nm(g) for g in gids}

    feats_n, nd = [], {}
    for g in gids:
        mem = sorted(members[g], key=lambda k: SYS_KEYS.index(node.loc[k, "system"]))
        syss = [node.loc[k, "system"] for k in mem]
        blocks = [dict(k=node.loc[k, "system"], anchor=str(node.loc[k, "anchor"]),
                       m={b: nmin[k][b]["m"] for b in BANDS}, n={b: nmin[k][b]["n"] for b in BANDS},
                       l={b: nmin[k][b]["l"] for b in BANDS}) for k in mem]
        es = r.get("estat", {}).get(g, {})
        symb = {b: es.get(b, {}).get("sym", []) for b in BANDS}          # list of symbols per band (solid / dotted)
        nd[g] = dict(name=names[g], sy=blocks, sym=symb,
                     ep={b: es.get(b, {}).get("ep", []) for b in BANDS}, rp={b: es.get(b, {}).get("rp", []) for b in BANDS},
                     net={b: es.get(b, {}).get("net") for b in BANDS})
        hands = lambda b, st: ",".join(str(h) for k in symb[b][:1] if k["st"] == st for h in k["h"])   # map symbol: the largest symmetry
        score = float(node.loc[mem, "score"].sum())
        props = dict(id=g, name=names[g], sys=",".join(syss), r=float(7 + score ** .5 / 4), dep=float(node.loc[mem, "departures"].sum()),
                     hp=hands("peak", "solid"), hd=hands("day", "solid"), hn=hands("night", "solid"),
                     xp=hands("peak", "dotted"), xd=hands("day", "dotted"), xn=hands("night", "dotted"))
        for sk in SYS_KEYS:
            props["s_" + sk] = 1 if sk in syss else 0
        feats_n.append(dict(type="Feature", geometry=dict(type="Point", coordinates=list(gpos[g])), properties=props))

    nightset = set()                                       # links with a departure between 00:00 and 05:00
    if len(legs):
        tt_ = legs.dep.values; adj_ = np.where(tt_ < 360, tt_ + 1440, tt_); sel_ = (adj_ >= 1440) & (adj_ < 1740)
        for a_, b_, m_ in zip(legs.a.values[sel_], legs.b.values[sel_], legs["mode"].values[sel_]):
            nightset.add((min(a_, b_), max(a_, b_), m_))
    feats_e, eidx, ed = [], {}, {}
    CE = {g: {b: set(d.get("ce", [])) for b, d in bb.items()} for g, bb in r.get("estat", {}).items()}   # connected edges per node / band
    for i, r_ in enumerate(und.itertuples()):
        ga, gb = groups[r_.a], groups[r_.b]
        eidx[(r_.a, r_.b, r_.mode)] = i
        cn = {b: int(f"{r_.b}¦{r_.mode}" in CE.get(ga, {}).get(b, set()) or
                     f"{r_.a}¦{r_.mode}" in CE.get(gb, {}).get(b, set()) or
                     (np.isfinite(float(getattr(r_, "hw_" + b))) and float(getattr(r_, "hw_" + b)) < towns.FREQ_CUT)) for b in BANDS}
        ed[i] = dict(a=node.loc[r_.a, "label"], b=node.loc[r_.b, "label"], k=r_.mode, cn=cn,
                     hd={b: [_num(getattr(r_, "hab_" + b, np.nan)), _num(getattr(r_, "hba_" + b, np.nan))] for b in BANDS},
                     tt=[_num(r_.tt_min, 0), _num(r_.tt_med, 0), _num(r_.tt_max, 0)],
                     hw={b: [_num(getattr(r_, "hw_" + b)), _num(getattr(r_, "lw_" + b)), int(getattr(r_, "n_" + b)), int(getattr(r_, "l_" + b))] for b in BANDS},
                     mn={b: [[int(x) for x in str(getattr(r_, f"mn_{b}_ab")).split(",") if x != ""],
                             [int(x) for x in str(getattr(r_, f"mn_{b}_ba")).split(",") if x != ""]] for b in BANDS},
                     rt=[c.strip().split(":", 1)[-1].split("@")[0] for c in str(r_.routes).split(",") if c.strip()])
        props = dict(system=r_.mode, a=ga, b=gb, ei=i, nn=1 if (r_.a, r_.b, r_.mode) in nightset else 0, t_min=f"{r_.tt_min:.0f}′", t_med=f"{r_.tt_med:.0f}′", t_max=f"{r_.tt_max:.0f}′",
                     off=float((SYS_KEYS.index(r_.mode) - (len(SYS_KEYS) - 1) / 2) * 4.0))
        for k in BANDS:
            props["c_" + k] = cn[k]
            h = getattr(r_, "hw_" + k)
            props["n_" + k] = int(getattr(r_, "n_" + k))
            props["w_" + k] = float(1.5 + min(60 / h, 8) * 0.9) if np.isfinite(h) else 0.0
        feats_e.append(dict(type="Feature", geometry=dict(type="LineString", coordinates=[list(gpos[ga]), list(gpos[gb])]), properties=props))

    feats_w, seen = [], {}
    for r_ in walk.itertuples():
        ga, gb = groups[r_.a], groups[r_.b]
        if ga == gb:
            continue
        key = tuple(sorted((ga, gb)))
        if key not in seen or seen[key] > r_.meters:
            seen[key] = r_.meters
    for r_ in walk.itertuples():
        ga, gb = groups[r_.a], groups[r_.b]
        key = tuple(sorted((ga, gb)))
        if ga == gb or seen.get(key) != r_.meters:
            continue
        seen[key] = -1
        feats_w.append(dict(type="Feature", geometry=dict(type="LineString", coordinates=[list(gpos[ga]), list(gpos[gb])]),
                            properties=dict(lbl=f"walk {r_.walk_min:.0f}′", na=ga, nb=gb,
                                            html=f"<div class='pp'><div class='hd' style='--c:#6b7280'><div class='pills'><span class='pill'>Walk</span></div>"
                                                 f"<h3>{names[ga]} <span class='arr'>↔</span> {names[gb]}</h3></div><div class='bd'>"
                                                 f"<div class='tiles two'><div><b>{r_.meters} m</b><span>distance</span></div><div><b>~{r_.walk_min:.0f}′</b><span>walking time</span></div></div></div></div>")))

    # service legs for the video: [edge feature index, direction (0 = a->b), departure min, travel min, system index]
    L = []
    if len(legs):
        gaps = {}                                                    # headway of each line on each directed link
        for k, g in legs.groupby(["route_key", "a", "b"]):
            gp = np.diff(np.sort(g.dep.values)); gp = gp[(gp > 0) & (gp <= 180)]
            gaps[k] = float(np.median(gp)) if len(gp) else 999.0
        comb = {}                                                    # all lines together on each directed link (different routes count too)
        for k, g in legs.groupby(["a", "b"]):
            gp = np.diff(np.unique(np.round(g.dep.values))); gp = gp[(gp > 0) & (gp <= 180)]
            comb[k] = float(np.median(gp)) if len(gp) else 999.0
        if "trip_key" in legs:
            fst = legs.groupby("trip_key").dep.transform("min").eq(legs.dep).values
            lst = legs.groupby("trip_key").dep.transform("max").eq(legs.dep).values
        else:
            fst = lst = np.ones(len(legs), bool)
        STR = {b: set() for b in BANDS}                         # trips that take part in a symmetry group, per band
        for g_, bb in r.get("estat", {}).items():
            for b_, d_ in bb.items():
                STR.setdefault(b_, set()).update(d_.get("trips", []))
        tbits = [sum(1 << i for i, b_ in enumerate(BANDS) if tk in STR.get(b_, ())) for tk in legs.trip_key] if "trip_key" in legs else [0] * len(legs)
        for li, lg in enumerate(legs.itertuples()):
            u = tuple(sorted((lg.a, lg.b)))
            i = eidx.get((u[0], u[1], lg.mode))
            if i is not None:
                L.append([i, 0 if lg.a == u[0] else 1, round(float(lg.dep), 1), round(float(lg.tt), 1), SYS_KEYS.index(lg.mode),
                          1 if gaps[(lg.route_key, lg.a, lg.b)] < towns.FREQ_CUT else 0,      # the line itself; the link (all lines) is checked per band in the page
                          1 if fst[li] else 0, 1 if lst[li] else 0, tbits[li]])     # first / last leg of its trip; bit per band: trip in a symmetry group
        L.sort(key=lambda x: x[2])
    combf = {}
    if len(legs):
        for k, g in legs.groupby(["a", "b"]):
            gp = np.diff(np.unique(np.round(g.dep.values))); gp = gp[(gp > 0) & (gp <= 180)]
            combf[k] = float(np.median(gp)) if len(gp) else 999.0
    LAY = []
    for row in r.get("lay", []):                     # vehicles standing at a stop: only if they then leave on a drawn link
        g, sy, t0, t1, fq, tr_ = row[:6]
        lk, dn = (row[6], row[7]) if len(row) > 7 else (None, None)
        if g not in gpos or not isinstance(dn, str):
            continue
        u = tuple(sorted((lk, dn)))
        ei = eidx.get((u[0], u[1], sy))
        if ei is None:
            continue
        LAY.append([round(gpos[g][0], 5), round(gpos[g][1], 5), round(t0, 1), round(t1, 1), SYS_KEYS.index(sy), 1 if fq else 0, 1 if tr_ else 0, ei])
    LAY.sort(key=lambda x: x[2])
    # timetables per node group: departures towards / arrivals from the next node, line, trip origin / destination
    TTL, TTN, TT = [], [], {}
    li_ = {}; ni_ = {}
    def _ix(tbl, idx, v):
        if v not in idx:
            idx[v] = len(tbl); tbl.append(v)
        return idx[v]
    if len(legs) and "trip_key" in legs:
        lg = legs.copy()
        lg["t0"] = np.where(lg.dep < towns.DAY_START_MIN, lg.dep + 1440, lg.dep)
        lg = lg.sort_values(["trip_key", "t0"])
        first = lg.groupby("trip_key").a.transform("first"); last = lg.groupby("trip_key").b.transform("last")
        lab_ = node["label"]
        tix = {t_: i for i, t_ in enumerate(lg.trip_key.unique())}
        for a_, b_, t0, tt, rk, mo, o_, d_, tk in zip(lg.a.values, lg.b.values, lg.t0.values, lg.tt.values, lg.route_key.values,
                                                 lg["mode"].values, first.values, last.values, lg.trip_key.values):
            ln = _ix(TTL, li_, str(rk).split(":", 1)[-1].split("@")[0]); si = SYS_KEYS.index(mo)
            ga_, gb_ = groups.get(a_), groups.get(b_)
            if ga_ is not None:   # departure from a towards b, trip to d
                TT.setdefault(ga_, []).append([round(float(t0), 1), ln, _ix(TTN, ni_, str(lab_.get(b_, b_))), _ix(TTN, ni_, str(lab_.get(d_, d_))), si, 0, tix[tk]])
            if gb_ is not None:   # arrival at b from a, trip from o
                TT.setdefault(gb_, []).append([round(float(t0 + tt), 1), ln, _ix(TTN, ni_, str(lab_.get(a_, a_))), _ix(TTN, ni_, str(lab_.get(o_, o_))), si, 1, tix[tk]])
        for g_ in TT:
            TT[g_].sort(key=lambda z: z[0])
    fc = lambda f: dict(type="FeatureCollection", features=f)
    return dict(n=fc(feats_n), e=fc(feats_e), w=fc(feats_w), legs=L, lay=LAY, nd=nd, ed=ed, night=bool(r.get("night", True)),
                tt=TT, ttl=TTL, ttn=TTN,
                vehkm={k: round(float(v), 1) for k, v in r.get("vehkm", {}).items()})


def _legend():
    rows = "".join(
        f'<label><input type="checkbox" data-l="{k}" checked><span class="sw{" dash" if v["dash"] else ""}" '
        f'style="border-color:{v["color"]}"></span><span id="nl-{k}" class="nd"><i class="dotn" style="background:{v["color"]}"></i></span>{v["name"]}</label>'
        for k, v in SYSTEMS.items())
    cols = [v["color"] for v in SYSTEMS.values()]
    return rows, "", cols[0], cols[-1]


def make_map(results, path, region_title=None):
    data = {d: _features(r) for d, r in results.items()}
    boundary = (ROOT / BOUNDARY_FILE).read_text()
    rows, dots, c1, c2 = _legend()
    cfg = dict(systems=[dict(key=k, color=v["color"], dash=v["dash"], icon=v.get("icon", "bus")) for k, v in SYSTEMS.items()],
               center=MAP_CENTER, zoom=MAP_ZOOM, periods=towns.PERIODS, freq=towns.FREQ_CUT, bands={k: _band(k) for k in towns.PERIODS}, pop=POPULATION,
               names={k: v['name'] for k, v in SYSTEMS.items()})
    page = (TEMPLATE.replace("__TITLE__", region_title or TITLE).replace("__FQ__", str(towns.FREQUENT_MIN)).replace("__PEAK__", _band("peak")).replace("__DAYB__", _band("day")).replace("__NIGHT__", _band("night"))
            .replace("__ROWS__", rows).replace("__DOTS__", dots).replace("__C1__", c1).replace("__C2__", c2)
            .replace("/*CSS*/", (VENDOR / "maplibre-gl.css").read_text())
            .replace("/*JS*/", (VENDOR / "maplibre-gl.js").read_text())
            .replace("__BOUNDARY__", boundary).replace("__DATA__", json.dumps(data))
            .replace("__CFG__", json.dumps(cfg)).replace("__STYLE__", STYLE))
    Path(path).write_text(page, encoding="utf-8")


TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>/*CSS*/</style>
<style>
:root{--ink:#1d2433;--mute:#6b7487;--line:#e4e7ee;--card:#fffffff2;--bg:#fff;--soft:#f3f5f9;--med:#e8eefc;--medl:#c5d3f5;--btn:#1d2433;--btnt:#fff;--hw1:#4a515c;--hw2:#737a85}
body.dark{--ink:#e8ebf2;--mute:#9aa3b5;--line:#2e3646;--card:#1c2230f2;--bg:#252c3b;--soft:#2a3242;--med:#31405f;--medl:#46598a;--btn:#e8ebf2;--btnt:#1c2230;--hw1:#c9cfda;--hw2:#a3abba}
body.dark .maplibregl-ctrl-group{background:#252c3b}body.dark .maplibregl-ctrl button .maplibregl-ctrl-icon{filter:invert(1)}body.dark .maplibregl-ctrl-scale{background:#1c2230cc;color:#e8ebf2;border-color:#e8ebf2}
html,body,#map{margin:0;height:100%;font:13px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink)}
#stack{position:absolute;left:12px;top:12px;bottom:28px;width:238px;display:flex;flex-direction:column;gap:8px;z-index:2;pointer-events:none}
#stack>*{pointer-events:auto;background:var(--card);backdrop-filter:blur(6px);border-radius:12px;box-shadow:0 4px 18px #1d243326;padding:9px 11px;box-sizing:border-box}
#ui{flex:0 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin}
#ui .top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
#ui h1{font-size:14px;margin:0;line-height:1.2}
#ui .t{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:8px 0 3px}
#ui .row{display:grid;grid-template-columns:34px 1fr;align-items:center;gap:6px;margin:3px 0}#ui .row>span{font-size:10.5px;color:var(--mute);text-transform:uppercase}
#ui label{display:flex;align-items:center;gap:6px;padding:2px 0;cursor:pointer;font-size:12px}
#ui input[type=checkbox]{accent-color:var(--btn);margin:0}
.sw{width:22px;height:0;border-top:3px solid;border-radius:2px;flex:none}.dash{border-top-style:dashed}.dot{border-top:3px dotted #777}
.dotn{display:inline-block;width:11px;height:11px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #0003;flex:none;vertical-align:middle}
.nd{transition:opacity .15s}.nd.off{opacity:.3}
#ui .seg{display:flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
#ui .seg button{flex:1;border:0;background:var(--bg);padding:3px 0;font:inherit;font-size:11.5px;cursor:pointer;color:var(--ink);white-space:nowrap}
#ui .seg button+button{border-left:1px solid var(--line)}#ui .seg button.on{background:var(--btn);color:var(--btnt)}
#ui select{flex:1;min-width:0;padding:3px 4px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--ink);font:inherit;font-size:11.5px}
#themebtn{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:7px;width:28px;height:24px;cursor:pointer;font-size:14px;line-height:1;padding:0}
#ui label.off{opacity:.35}#ui .foot{display:flex;gap:10px;align-items:center;font-size:11px;color:var(--mute);margin-top:6px}
#ui .foot span{display:flex;align-items:center;gap:4px}
.mix{background:radial-gradient(circle,__C2__ 0 45%,#fff 45% 55%,__C1__ 55% 100%)}
#supplybox .t{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 3px}
#supply{width:100%;border-collapse:collapse;font-size:11.5px}#supply td,#supply th{padding:1px 0;text-align:right;font-weight:400}#supply th{font-size:9.5px;color:var(--mute);text-transform:uppercase}#supply td:first-child,#supply th:first-child{text-align:left}#supply tr.tot td{border-top:1px solid var(--line);font-weight:700}
#vbtn{width:100%;margin-top:6px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--ink);padding:3px 0;font:inherit;font-size:11.5px;cursor:pointer}#vbtn.on{background:var(--btn);color:var(--btnt)}
#clock{display:none;flex:none}
#clock .row{display:flex;align-items:center;gap:10px}#clock .time{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1}
#clock .day{color:var(--mute);font-size:11px;text-transform:capitalize}
#clock input[type=range]{width:100%;margin:5px 0 3px}#clock .ctl{display:flex;gap:4px}#hidefl{display:flex;align-items:center;gap:6px;font-size:11.5px;margin:2px 0 6px;cursor:pointer}
#clock button{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:7px;padding:2px 6px;font:inherit;font-size:11.5px;cursor:pointer}#clock button#cplay{flex:1}
#clock button.on{background:var(--btn);color:var(--btnt)}
.maplibregl-popup-content{overflow-x:hidden;background:var(--bg);color:var(--ink);padding:0;border-radius:12px;box-shadow:0 6px 24px #1d243340;overflow:hidden}
.maplibregl-popup-tip{display:none}.maplibregl-popup-close-button{font-size:20px;color:#fff;padding:4px 10px;border-radius:0 12px 0 8px}
.pp{box-sizing:border-box;width:min(440px,calc(100vw - 60px));font-size:12.5px;max-height:calc(100vh - 140px);overflow-y:auto;overflow-x:hidden;scrollbar-width:thin}
.pp .hd{background:linear-gradient(135deg,var(--c),color-mix(in srgb,var(--c) 62%,#000));color:#fff;padding:12px 38px 12px 16px}
.pp .pills{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:5px}
.pp .pill{background:#ffffff2e;border:1px solid #ffffff55;border-radius:999px;padding:1px 9px;font-size:10.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
.pp h3{margin:0;font-size:17px;line-height:1.25;font-weight:650}.pp h3 .arr{opacity:.7;font-weight:400;margin:0 2px}
.pp .bd{padding:2px 16px 14px}
.pp .sec{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--mute);margin:14px 0 6px;display:flex;align-items:baseline;gap:6px}
.pp .sec small{text-transform:none;letter-spacing:0;font-size:10.5px;opacity:.8}
.tiles{display:grid;gap:8px}.tiles.two{grid-template-columns:1fr 1fr}.tiles.three{grid-template-columns:1fr 1.25fr 1fr}
.tiles>div{background:var(--soft);border-radius:10px;padding:7px 6px;text-align:center}
.tiles b{display:block;font-size:19px;line-height:1.15;font-weight:650}.tiles span{font-size:10.5px;color:var(--mute)}
.tiles .med{background:var(--med);outline:1px solid var(--medl)}
.pp table{width:100%;border-collapse:collapse}
.pp td{padding:5px 0;border-bottom:1px solid var(--line);vertical-align:middle}.pp tr:last-child td{border-bottom:0}
.pp tr.th td{font-size:9.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em;padding-bottom:3px}
.pp td.r{text-align:right;white-space:nowrap;padding-left:10px}.pp td.bl{font-weight:600;white-space:nowrap;padding-right:10px}
.pp td small{display:block;color:var(--mute);font-weight:400;font-size:10px}
.pp .ft tr:nth-child(even) td{background:color-mix(in srgb,var(--soft) 55%,transparent)}
.pp .blk{margin-top:12px;padding:10px 11px;border:1px solid var(--line);border-radius:12px}
.pp .blk .bh{display:flex;align-items:center;gap:7px;margin-bottom:8px}.pp .blk .stop{margin-left:auto;color:var(--mute);font-size:11px;text-align:right;max-width:55%}
.pp .blk .tiles{margin-bottom:6px}
.mc{display:inline-block;background:var(--soft);border-radius:6px;padding:0 6px;margin:1px 3px 1px 0;font-variant-numeric:tabular-nums;font-weight:600;font-size:11.5px}
.iv{color:var(--mute);font-size:10.5px;margin-left:3px}.none{color:var(--mute)}
.pp .dir{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin:1px 0}.pp .dir em{font-style:normal;color:var(--mute);font-size:10.5px;min-width:86px}
.symcard{display:flex;align-items:center;gap:12px;margin-top:12px;padding:9px 12px;border-radius:12px;background:var(--med);outline:1px solid var(--medl)}
.symcard .symclock{color:var(--ink);flex:none}.symcard b{display:block;font-size:13px}.symcard span{display:block}.symcard small{display:block;color:var(--mute);font-size:10.5px;margin-top:1px}
.rt td{padding:3px 0}.rt .sysn{display:inline;color:var(--mute);font-size:10.5px;margin-left:3px}.rt td.bar{width:34%}.rt td.bar i{display:block;height:6px;border-radius:3px;background:color-mix(in srgb,var(--ink) 25%,transparent)}
.tiles.four{grid-template-columns:repeat(4,1fr)}.tiles.four b{font-size:16px}
.dirs td{vertical-align:middle}.dirs .cb{display:inline-block;width:52px;height:6px;border-radius:3px;background:var(--soft);vertical-align:middle;margin-right:5px;overflow:hidden}.dirs .cb i{display:block;height:100%}.dirs small{font-size:10.5px;color:var(--mute)}.dirs tr.frq{opacity:.45}.half{display:inline-block;font-size:10px;font-weight:700;padding:0 4px;border-radius:5px;background:var(--soft);color:var(--mute)}.cn td{vertical-align:middle;padding:4px 3px}.cn .th td.ar{font-size:17px;font-weight:700;color:var(--ink);letter-spacing:0}details.fq{margin-top:6px}details.fq summary{cursor:pointer;font-size:11px;color:#2563eb;padding:3px 0}.cn td.c{text-align:center;width:22%}.cn td.ed{width:28%;font-weight:600;font-size:11.5px}.cn td.ed small{display:block;font-weight:400;color:var(--mute);font-size:10px}.cn td.rt{text-align:right}.cn .wk{font-size:9.5px;font-weight:600;color:var(--mute);border:1px solid var(--line);border-radius:4px;padding:0 3px}.cx{text-align:center;border-radius:7px}.cx b{display:block;font-size:12px}.cx small{display:block;font-size:9.5px;color:var(--mute);line-height:1.15}.cx.c{background:color-mix(in srgb,#16a34a 16%,transparent)}.cx.p{background:color-mix(in srgb,#f59e0b 16%,transparent)}.cx.f{background:color-mix(in srgb,#2563eb 13%,transparent)}.cx.f b{color:#2563eb}.cx.no,.cx.na{color:var(--mute);opacity:.6}.symcard.dot{outline-style:dashed}.symcard+.symcard{margin-top:6px}#ui .conn{margin-top:2px}#infobtn{margin-left:auto;width:20px;height:20px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:italic 700 12px Georgia,serif;cursor:pointer;padding:0;pointer-events:auto}
#connfl{display:flex;align-items:center;gap:6px;font-size:11.5px;margin:0 0 6px;cursor:pointer}#connfl.dis{opacity:.5}
#info{position:fixed;inset:0;z-index:20;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;padding:16px}#info[hidden]{display:none}
#info .ibox{position:relative;background:var(--bg);color:var(--ink);border-radius:14px;max-width:760px;width:100%;max-height:92vh;overflow:auto;padding:16px 18px;box-shadow:0 10px 40px #0006}
#info h2{margin:0 0 8px;font-size:16px}#info ul{margin:10px 0 0;padding-left:18px;font-size:12.5px;line-height:1.45}#info li{margin:3px 0}
#info canvas{width:100%;height:auto;border-radius:10px;background:var(--soft)}#infox{position:absolute;right:10px;top:6px;border:0;background:none;color:var(--ink);font-size:22px;cursor:pointer}
.dirb{border:1px solid var(--line);border-radius:10px;padding:6px 9px;margin-top:7px}.dirb .dh{display:flex;justify-content:space-between;gap:8px;font-weight:600;font-size:12px;margin-bottom:4px}.dirb .hwt{font-weight:400;color:var(--mute);white-space:nowrap}.dirb .hwt b{color:var(--ink)}
.cn small.hio{display:flex;gap:4px;flex-wrap:wrap}.cn td.rt small.hio{justify-content:flex-end}.cn small.hio span{background:var(--soft);border-radius:5px;padding:0 4px}
.symcard{cursor:pointer}.symcard.sel{outline:2px solid var(--ink)}.gt{display:inline-block;font-style:normal;font-size:9.5px;font-weight:700;background:var(--ink);color:var(--bg);border-radius:4px;padding:0 4px;margin-right:4px;vertical-align:1px}.selnote{font-size:11px;color:var(--mute);margin:6px 0 0}.sec .hint{font-size:9.5px;text-transform:none;letter-spacing:0;color:var(--mute);margin-left:6px}
.cn{table-layout:fixed;width:100%}.cn td{vertical-align:middle;padding:5px 3px;border-top:1px solid var(--line)}.cn tr.th td{border-top:0;font-size:9.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--mute);font-weight:600;padding-bottom:3px}
.cn td.ed{width:26%;font-size:11px;font-weight:600;line-height:1.25;overflow-wrap:anywhere;hyphens:auto}.cn td.rt{text-align:right}.cn .enm{display:block}.cn td.ed .dotk,.cn td.ed .dotn{width:8px;height:8px;border-width:1.5px;vertical-align:1px}
.cn td.c{text-align:center}.cx{width:24%;text-align:center;border-radius:8px;padding:4px 2px!important}.cx b{display:block;font-size:12px;line-height:1.2;white-space:nowrap}.cx small{display:block;font-size:9.5px;color:var(--mute);line-height:1.25}.cx small.dim{opacity:.8}
.cx.c{background:color-mix(in srgb,#16a34a 15%,transparent)}.cx.c b{color:color-mix(in srgb,#15803d 85%,var(--ink))}.cx.f{background:color-mix(in srgb,#2563eb 10%,transparent)}.cx.f b{color:#2563eb}.cx.no b{color:var(--mute);font-weight:600}.cx.na{color:var(--mute);opacity:.5}
.cx .gt{margin:0 3px 0 0;vertical-align:1px}.cn .nw{white-space:nowrap}details.fq{margin-top:8px}details.fq summary{cursor:pointer;font-size:11px;color:var(--mute);padding:3px 0}details.fq[open] summary{color:var(--ink)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 8px}.tabs button{display:flex;align-items:center;gap:5px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:999px;padding:2px 10px 2px 4px;font:inherit;font-size:12px;font-weight:600;cursor:pointer}.tabs button.on{background:var(--ink);color:var(--bg)}
.nosym{background:var(--soft);border-radius:10px;padding:8px 12px;margin:2px 0 6px}.nosym b{display:block}.nosym span{font-size:11.5px;color:var(--mute)}
.rel{width:100%;border-collapse:collapse}.rel td{padding:4px 3px;border-top:0;vertical-align:middle;font-size:11.5px}.rel tr.np td{border-top:1px solid var(--line);padding-top:6px}.rel tr:first-child td{border-top:0}.rel td.w small{display:block;font-size:9.5px;color:var(--mute)}.rel td.pa{font-weight:600;width:34%;overflow-wrap:anywhere}.rel td.pr{text-align:center;font-size:15px;width:7%;color:color-mix(in srgb,#15803d 85%,var(--ink))}.rel td.pr.small{font-size:10.5px;line-height:1.5;width:28%;text-align:left}
.rel td.w{font-size:11px;white-space:nowrap;width:12%}.rel td.e{font-size:11px;color:var(--mute);white-space:nowrap;width:13%}.rel .tm{color:#15803d;font-weight:600}.rel .mu{color:var(--mute)}.rel .fr{color:#2563eb}
.rel tr.og td{opacity:.75}.rel .ogt{display:block;font-weight:400;font-size:9.5px;color:var(--mute)}.legendline{font-size:10px;color:var(--mute);margin-top:6px}
.relb{display:grid;grid-template-columns:30% 40% 30%;gap:4px;padding:7px 0;border-top:1px solid var(--line);align-items:start}.relb .rs{font-size:11.5px;line-height:1.25;overflow-wrap:anywhere}.relb .rs.r{text-align:right}
.relb .lns{display:flex;flex-wrap:wrap;gap:3px;margin-top:4px;max-height:58px;overflow-y:auto}.relb .rs.r .lns{justify-content:flex-end}.relb .lns span{font-size:9.5px;padding:0 4px;border-radius:4px;background:var(--soft);color:var(--mute)}.relb .lns span i{font-style:normal;opacity:.75}.relb .lns span.u{background:var(--ink);color:var(--bg)}
.relb .rm{display:flex;flex-direction:column;gap:4px}.relb .dv{display:flex;gap:5px;align-items:flex-start;font-size:11px;border-radius:7px;padding:3px 5px;background:var(--soft)}.relb .dv.ing{background:color-mix(in srgb,#16a34a 15%,transparent)}.relb .dv .da{font-weight:700;font-size:13px;line-height:1.1}.relb .dv small{display:block;font-size:9.5px;color:var(--mute)}.relb .dv i{font-style:normal;font-weight:400;font-size:9.5px}
.relb .tm{color:color-mix(in srgb,#15803d 85%,var(--ink))}.relb .fr{color:#2563eb}.relb .mu{color:var(--mute);font-weight:600}
.relb .dv .dl{display:flex;flex-direction:column;min-width:0}.relb .dv .l1,.relb .dv .l2{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.relb .dv .l1{font-weight:700}.relb .dv .l2{font-size:10px;color:var(--mute)}.relb .dv .l2 s{text-decoration:none;opacity:.85}
.relb .lns span.ln{display:inline-flex;padding:0;overflow:hidden;cursor:pointer;border:1px solid var(--line);background:var(--bg);color:var(--ink)}.relb .lns span.ln b{padding:0 4px;font-weight:700}.relb .lns span.ln i{padding:0 4px;background:var(--soft);color:var(--mute);font-style:normal;border-left:1px solid var(--line)}
.relb .lns span.ln.u{border-color:var(--ink)}.relb .lns span.ln.u b{background:var(--ink);color:var(--bg)}.relb .lns span.ln:not(.u){opacity:.65}
.stl{cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px}.lnb{cursor:pointer;font-weight:700;text-decoration:underline dotted}
#ttpanel{position:fixed;right:12px;top:60px;z-index:15;width:340px;max-width:calc(100vw - 24px);max-height:calc(100vh - 90px);overflow-y:auto;overflow-x:hidden;background:var(--bg);color:var(--ink);border-radius:12px;box-shadow:0 8px 30px #0005}#ttpanel[hidden]{display:none}
#ttpanel .hd{position:relative;padding-right:48px}#ttpanel .pp{width:100%;box-sizing:border-box}.ttx{position:absolute;right:8px;top:8px;width:30px;height:30px;border-radius:50%;border:0;background:rgba(255,255,255,.18);color:#fff;font-size:16px;font-weight:700;cursor:pointer}.ttx:hover{background:rgba(255,255,255,.35)}
.ttb{max-height:260px;overflow-y:auto;border:1px solid var(--line);border-radius:8px}#ttpanel .ttb{max-height:none}.ttt{width:100%;border-collapse:collapse;table-layout:fixed}.ttt td:nth-child(1){width:38px}.ttt td:nth-child(2){width:40px}.ttt td:nth-child(3){width:50px}.ttt td{padding:2px 6px;font-size:11px;border-top:1px solid var(--line);overflow-wrap:anywhere}.ttt td:nth-child(3){white-space:nowrap}.ttt small{display:inline}.ttt tr:first-child td{border-top:0}.ttt td.tm2{font-variant-numeric:tabular-nums;width:38px;white-space:nowrap}.ttt tr.th td{font-size:9.5px;text-transform:uppercase;color:var(--mute);letter-spacing:.04em}.ttt small{color:var(--mute)}
.netbox{border:1px solid var(--line);border-radius:10px;background:var(--soft);margin-bottom:4px}.netsvg{display:block}.netsvg .nlab{font-size:10px;fill:var(--ink)}.netsvg .nnm{font-weight:700;font-size:11.5px}.netsvg .nsu{font-weight:700;fill:var(--ink)}.netsvg .nsn{fill:var(--mute)}.netsvg .nmin,.netsvg .nmout{font-size:11px;font-weight:700;fill:var(--ink);text-anchor:middle}.netsvg .narr{font-size:9px;fill:var(--ink)}.netsvg .nfq{opacity:.6;font-weight:600}.netsvg .ngr{fill:var(--hw2)}.netsvg .ngr .narr{fill:var(--hw2)}.netsvg .nwkl{font-size:9.5px;fill:var(--mute)}.netsvg .onl{paint-order:stroke;stroke:var(--soft);stroke-width:4px;stroke-linejoin:round}.netsvg .nrep{font-size:9px;font-weight:600;fill:var(--hw2)}.netsvg .nmut{fill:var(--hw2);font-weight:500;font-style:italic}.netsvg .nmut .narr{fill:var(--hw2)}.netsvg .nsep{fill:var(--mute);font-weight:400}.netsvg .nhwg{fill:var(--hw2);font-size:9px}.netsvg .nhw{font-size:9px;fill:var(--mute)}.netsvg .nhwd{font-size:9px;font-weight:700;fill:var(--hw1)}.netsvg .nleg{font-size:9.5px;fill:var(--mute)}.netsvg .nleg .nmin,.netsvg .nleg .nmout{font-size:9.5px;text-anchor:start}.netst{font-size:10.5px;color:var(--mute);margin:2px 0 4px}.netsvg .nwk{font-size:9px;fill:var(--mute);text-anchor:middle}
.mc.ig{opacity:.38}.mins{display:flex;flex-wrap:wrap;align-items:baseline}.mins .mc{font-size:11px;padding:0 5px;margin:1px 2px 1px 0}
.trs{max-height:230px;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin}.tt td{font-size:11.5px;padding:4px 4px 4px 0;vertical-align:top}.tt td.r{white-space:nowrap}
.tt tr.rev td{color:var(--mute)}
.tt tr.th td{position:sticky;top:0;z-index:2;background:var(--bg);box-shadow:0 1px 0 var(--line)}
.pp{width:min(380px,calc(100vw - 60px));font-size:12px}
.pp .hd{padding:8px 32px 8px 12px}.pp h3{font-size:15px}.pp .pills{margin-bottom:3px}.pp .pill{font-size:9.5px;padding:0 7px}
.pp .bd{padding:0 12px 10px}.pp .sec{margin:9px 0 3px}
.pp .blk{margin-top:8px;padding:6px 8px}.pp .blk .bh{margin-bottom:3px}
.pp .stat{margin:5px 0 3px;color:var(--ink)}.pp .stat b{font-weight:650}.pp .stat small{color:var(--mute)}
.pp .symcard{margin-top:8px;padding:6px 9px;gap:9px}.pp .symcard svg{width:36px;height:36px}.pp .symcard b{font-size:12px}
.pp .dir{margin:0}.pp .dir em{min-width:70px}
.mins .mc{font-size:10.5px;padding:0 4px;margin:1px 2px 1px 0}.trs{max-height:170px}
.chips{display:flex;flex-wrap:wrap;gap:4px}.chip{background:var(--soft);border-radius:999px;padding:1px 9px;font-size:11px;max-width:100%;overflow-wrap:anywhere}
</style></head><body><div id="map"></div>
<div id="stack">
<div id="ui"><div class="top"><h1>__TITLE__</h1><button id="themebtn" title="Light / dark map">☾</button></div>
<div class="row"><span>Day</span><div class="seg" data-g="day"><button data-v="weekday" class="on">Weekday</button><button data-v="saturday">Sat</button><button data-v="sunday">Sun</button></div></div>
<div class="row"><span>Time</span><div class="seg" data-g="per"><button data-v="peak" class="on" title="__PEAK__">Peak</button><button data-v="day" title="__DAYB__">Day</button><button data-v="night" title="__NIGHT__">Night</button></div></div>
<div class="row"><span>Trip</span><div class="seg" data-g="time"><button data-v="t_min">Min</button><button data-v="t_med" class="on">Median</button><button data-v="t_max">Max</button></div></div>
<div class="row"><span>Base</span><select id="basesel"><option value="minimal">Minimal</option><option value="streets">Streets</option><option value="detailed">Detailed</option><option value="satellite">Google satellite</option><option value="hybrid">Google hybrid</option></select></div>
<div class="t">Connections &amp; nodes</div>
__ROWS__
<label><input type="checkbox" data-l="walk" checked><span class="sw dot"></span>Walk between stations</label>
<label class="conn" title="Only lines that belong to a symmetry group (selected day and time); nodes left without lines are hidden"><input type="checkbox" id="connonly"> Coordinated only</label>
<div class="foot"><span><i class="dotn mix"></i>Merged</span><span><svg width="14" height="14" viewBox="-8 -8 16 16"><circle r="6" fill="#bbb" stroke="#fff" stroke-width="1.5"/><line x1="0" y1="0" x2="0" y2="-8" stroke="#000" stroke-width="2"/><line x1="0" y1="0" x2="0" y2="8" stroke="#000" stroke-width="2"/></svg><b id="symcount">0</b>&nbsp;symmetry nodes</span><button id="infobtn" title="How connections and symmetry are defined">i</button></div>
</div>
<div id="supplybox"><div class="t">Service supply per day</div><table id="supply"></table><button id="vbtn">Open video</button></div>
<div id="clock"><div class="row"><svg id="ck" width="52" height="52" viewBox="-32 -32 64 64"><circle r="30" fill="var(--bg)" stroke="var(--ink)" stroke-width="2"/>
<g id="ticks"></g><line id="hh" x1="0" y1="2" x2="0" y2="-15" stroke="var(--ink)" stroke-width="3" stroke-linecap="round"/>
<line id="mh" x1="0" y1="3" x2="0" y2="-24" stroke="#d62728" stroke-width="2" stroke-linecap="round"/><circle r="2.5" fill="var(--ink)"/></svg>
<div><div class="time" id="ctime">06:30</div><div class="day" id="cday">weekday</div></div></div>
<input type="range" id="cslider" min="0" max="1830" step="1" value="390">
<label id="hidefl"><input type="checkbox" id="hidef"> Hide frequent lines (headway under 15 min)</label>
<label id="connfl" title="Only vehicles on lines and trips that belong to a symmetry group"><input type="checkbox" id="connv"> Coordinated only</label>
<div class="ctl"><button id="cplay">▶ Play</button><button data-sp="1">1×</button><button data-sp="2">2×</button><button data-sp="3" class="on">3×</button><button data-sp="10">10×</button></div></div>
</div>
<div id="ttpanel" hidden></div>
<div id="info" hidden><div class="ibox"><button id="infox" title="Close">×</button><h2>Clock-face hub</h2>
<canvas id="anim" width="720" height="330"></canvas>
<p style="margin:8px 0 0;font-size:13px"><a href="../../explain/symmetry/" target="_blank">Why symmetry</a> · <a href="../../docs/rules.html" target="_blank">Rules</a> · <a href="../../index.html">All regions</a></p></div></div><script>/*JS*/</script><script>
const CFG=__CFG__;const SYS=CFG.systems,SK=SYS.map(s=>s.key),COL=Object.fromEntries(SYS.map(s=>[s.key,s.color]));
const D=__DATA__,BOUND=__BOUNDARY__;let PER='peak',TIME='t_med',DAY='weekday',BASE='minimal',MODE='light',WALK=true,CONN=false;const ON=new Set(SK);
const STYLES={minimal:'https://tiles.openfreemap.org/styles/positron',streets:'https://tiles.openfreemap.org/styles/bright',detailed:'https://tiles.openfreemap.org/styles/liberty'};
try{const sv=JSON.parse(localStorage.getItem('mapPrefs')||'{}');if(STYLES[sv.base]||sv.base==='satellite'||sv.base==='hybrid')BASE=sv.base;if(sv.mode==='dark'||sv.mode==='light')MODE=sv.mode;}catch(e){}
const OFF=()=>false;                              // (night view: links without service between 00:00 and 05:00 are hidden per link, see 'nn')
const NODE={};for(const d in D){NODE[d]={};for(const f of D[d].n.features)NODE[d][f.properties.id]=f.properties;}
// ---- dark mode: recolour a style (invert lightness, keep hue). Pure-JS colour parsing (no canvas).
const NAMED={white:[255,255,255,1],black:[0,0,0,1],transparent:[0,0,0,0],red:[255,0,0,1],gray:[128,128,128,1],grey:[128,128,128,1]};
function parseCol(str){str=str.trim().toLowerCase();if(NAMED[str])return NAMED[str];let m;
 if(m=str.match(/^#([0-9a-f]{3,8})$/)){let h=m[1];if(h.length<=4)h=h.split('').map(c=>c+c).join('');const n=[0,2,4].map(i=>parseInt(h.slice(i,i+2),16));return [...n,h.length===8?parseInt(h.slice(6,8),16)/255:1];}
 if(m=str.match(/^rgba?\(([^)]*)\)$/)){const p=m[1].split(/[\s,\/]+/).filter(Boolean).map(x=>x.endsWith('%')?parseFloat(x)*2.55:parseFloat(x));return [p[0],p[1],p[2],p.length>3?(String(m[1]).includes('%')&&p[3]>1?p[3]/255:p[3]):1];}
 if(m=str.match(/^hsla?\(([^)]*)\)$/)){const p=m[1].split(/[\s,\/]+/).filter(Boolean).map(x=>parseFloat(x));const h=p[0]/360,s=p[1]/100,l=p[2]/100;
  const f=(n)=>{const k=(n+h*12)%12,a=s*Math.min(l,1-l);return Math.round(255*(l-a*Math.max(-1,Math.min(k-3,9-k,1))));};return [f(0),f(8),f(4),p.length>3?p[3]:1];}
 return null;}
function conv(str){const c=parseCol(str);if(!c||c.some(x=>x!==x))return str;let [r,g,b,a]=c;r/=255;g/=255;b/=255;const mx=Math.max(r,g,b),mn=Math.min(r,g,b);let h=0,sa=0,l=(mx+mn)/2;
 if(mx!==mn){const d=mx-mn;sa=l>.5?d/(2-mx-mn):d/(mx+mn);h=mx===r?(g-b)/d+(g<b?6:0):mx===g?(b-r)/d+2:(r-g)/d+4;h*=60;}
 const l2=0.10+0.78*(1-l);return `hsla(${h.toFixed(0)},${(sa*80).toFixed(0)}%,${(l2*100).toFixed(1)}%,${(+a).toFixed(3)})`;}
const isCol=v=>typeof v==='string'&&/^(#[0-9a-f]{3,8}$|rgba?\(|hsla?\(|white$|black$)/i.test(v.trim());
function recolor(v){if(isCol(v))return conv(v);if(Array.isArray(v))return v.map(recolor);if(v&&typeof v==='object'){const o={};for(const k in v)o[k]=k==='stops'?v[k].map(([z,c])=>[z,recolor(c)]):recolor(v[k]);return o;}return v;}
function darken(st){for(const L of st.layers){if(!L.paint)continue;for(const k in L.paint)if(/color/.test(k))L.paint[k]=recolor(L.paint[k]);}return st;}
const SAT=()=>BASE==='satellite'||BASE==='hybrid';
function rasterStyle(){   // Google satellite (lyrs=s) / hybrid (lyrs=y: imagery with labels and roads)
 const ly=BASE==='hybrid'?'y':'s',T=['0','1','2','3'].map(k=>`https://mt${k}.google.com/vt/lyrs=${ly}&x={x}&y={y}&z={z}`);
 return {version:8,glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',sources:{sat:{type:'raster',tiles:T,tileSize:256,maxzoom:21,attribution:'Imagery © Google'}},
  layers:[{id:'sat',type:'raster',source:'sat',paint:{'raster-brightness-max':MODE==='dark'?0.6:1}}]};}
async function styleFor(){if(SAT())return rasterStyle();const st=await (await fetch(STYLES[BASE])).json();if(MODE!=='dark')return st;try{return darken(JSON.parse(JSON.stringify(st)));}catch(e){console.error('dark style failed',e);return st;}}
function theme(){document.body.classList.toggle('dark',MODE==='dark');const d=MODE==='dark'||SAT();
 const set=(l,p,v)=>{if(map.getLayer(l))map.setPaintProperty(l,p,v);};
 set('boundary','line-color',d?'#fff':'#000');set('nodes_lbl','text-color',d?'#e8ebf2':'#1d2433');set('nodes_lbl','text-halo-color',d?'#10141c':'#fff');
 set('walk_lbl','text-halo-color',d?'#10141c':'#fff');set('walk_lbl','text-color',d?'#bbb':'#555');set('walk','line-color',d?'#aaa':'#777');
 for(const k of SK)set(k+'_lbl','text-halo-color',d?'#10141c':'#fff');}
let map;
(async()=>{
 map=new maplibregl.Map({container:'map',style:withCustom(await styleFor()),center:CFG.center,zoom:CFG.zoom});
 map.addControl(new maplibregl.NavigationControl(),'top-right');map.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-right');
 // node icons: pie of the active systems + black hand at the symmetry minute (line through the centre if 30-min)
 map.on('styleimagemissing',e=>{if(e.id.startsWith('veh_')){const q=e.id.split('_'),sy=SYS.find(x=>x.key===q[1]);if(sy)map.addImage(e.id,vehImg(sy.icon,sy.color,q[2]==='l'),{pixelRatio:3});return;}const p=e.id.split('|');if(p[0]!=='n')return;const day=p[1],per=p[2],mask=p[3],id=p.slice(4).join('|');const n=NODE[day]&&NODE[day][id];if(!n)return;
  const act=n.sys.split(',').filter(s=>mask.split(',').includes(s));if(!act.length)return;
  const R=n.r,pad=5,S=Math.ceil((R+pad)*2),k=2,c=document.createElement('canvas');c.width=c.height=S*k;const g=c.getContext('2d');g.scale(k,k);g.translate(S/2,S/2);
  g.lineWidth=2.5;g.strokeStyle='#fff';
  // several modes: concentric rings (outer = first mode), never slices -- a straight line through the node means symmetry
  act.forEach((s,i)=>{const r=R*(1-i/act.length);g.beginPath();g.arc(0,0,r,0,7);g.fillStyle=COL[s];g.fill();if(i){g.lineWidth=1.2;g.strokeStyle='#fff';g.stroke();g.lineWidth=2.5;}});
  g.beginPath();g.arc(0,0,R,0,7);g.stroke();
  const pk=({peak:'p',day:'d',night:'n'})[per],L=(v)=>(v||'').split(',').filter(x=>x!=='').map(Number);
  const hs=L(n['h'+pk]),hx=L(n['x'+pk]).filter(x=>!hs.includes(x));
  const hand=(h,w,col,dash)=>{const t=h/60*2*Math.PI-Math.PI/2;g.setLineDash(dash);g.lineWidth=w;g.strokeStyle=col;g.beginPath();g.moveTo(0,0);g.lineTo(Math.cos(t)*(R+2.5),Math.sin(t)*(R+2.5));g.stroke();};
  g.lineCap='round';
  for(const h of hs){hand(h,4.2,'#fff',[]);hand(h,2,'#000',[]);}
  for(const h of hx){hand(h,4.2,'#fff',[]);g.lineCap='butt';hand(h,2,'#000',[2.2,2]);g.lineCap='round';}
  g.setLineDash([]);
  map.addImage(e.id,g.getImageData(0,0,S*k,S*k),{pixelRatio:k});});
 function vehImg(kind,color,flip){
  const WK={bus:52,train:70,tram:58},W=WK[kind]||52,H=30,k=3,X=0.62,c=document.createElement('canvas');c.width=Math.round(W*X*k);c.height=H*k;const g=c.getContext('2d');g.scale(k*X,k);
  if(flip){g.translate(W,0);g.scale(-1,1);}
  const dark='#1d2433',glass='rgba(232,244,252,.96)';
  const rr=(x,y,w,h,r)=>{g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath();};
  let shape;
  if(kind==='bus')shape=()=>{g.moveTo(5,3);g.lineTo(W-6,3);g.quadraticCurveTo(W-1,3,W-0.5,9);g.lineTo(W,20);g.lineTo(2,20);g.lineTo(2,6);g.quadraticCurveTo(2,3,5,3);g.closePath();};
  else if(kind==='tram')shape=()=>{rr(2,3,W-4,17,6);};
  else shape=()=>{g.moveTo(5,4);g.lineTo(W-24,4);g.quadraticCurveTo(W-4,4.5,W-0.5,15);g.lineTo(W,20);g.lineTo(2,20);g.lineTo(2,7);g.quadraticCurveTo(2,4,5,4);g.closePath();};
  if(kind!=='bus'){const px=kind==='tram'?W/2:W-38;g.lineCap='round';g.lineJoin='round';
   for(const [w,col] of [[3.6,'rgba(20,24,34,.55)'],[1.6,'#fff']]){g.lineWidth=w;g.strokeStyle=col;g.beginPath();g.moveTo(px-5,kind==='tram'?3:4);g.lineTo(px,-0.3);g.lineTo(px+5,kind==='tram'?3:4);g.moveTo(px-3,-0.3);g.lineTo(px+3,-0.3);g.stroke();}}
  g.lineJoin='round';
  for(const [w,col] of [[4.6,'rgba(20,24,34,.55)'],[2.6,'#fff']]){g.lineWidth=w;g.strokeStyle=col;g.beginPath();shape();g.stroke();}
  g.fillStyle=color;g.beginPath();shape();g.fill();
  g.save();g.beginPath();shape();g.clip();g.fillStyle='rgba(255,255,255,.30)';g.fillRect(0,14.2,W,2);g.fillStyle='rgba(0,0,0,.28)';g.fillRect(0,17.8,W,3);g.restore();
  g.fillStyle=glass;const win=(x,y,w,h)=>{g.beginPath();rr(x,y,w,h,1.3);g.fill();};
  if(kind==='bus'){for(const x of [5.5,14.5,23.5])win(x,5.5,7.5,7.5);win(32.5,5.5,5,12.5);g.beginPath();g.moveTo(40,5.5);g.lineTo(W-4,5.5);g.lineTo(W-2,13);g.lineTo(40,13);g.closePath();g.fill();}
  else if(kind==='tram'){for(const x of [6,16])win(x,6,7.5,7.5);win(26,6,5,12);g.beginPath();g.moveTo(35,6);g.lineTo(W-9,6);g.quadraticCurveTo(W-5,7,W-4,13);g.lineTo(35,13);g.closePath();g.fill();}
  else{for(const x of [6,14.5,23])win(x,6.5,6.5,6.5);win(31.5,6.5,4.5,11.5);g.beginPath();g.moveTo(W-30,6.5);g.lineTo(W-22,6.5);g.lineTo(W-9,13);g.lineTo(W-30,13);g.closePath();g.fill();}
  g.fillStyle='#ffe9a8';g.beginPath();g.arc(W-2.8,16.8,1.5,0,7);g.fill();
  const wh=kind==='bus'?[12,W-12]:(kind==='tram'?[11,22,W-22,W-11]:[10,20,W-26,W-14]);
  for(const x of wh){if(kind==='bus'){g.fillStyle=dark;g.beginPath();g.arc(x,20,5.2,Math.PI,0);g.fill();}
   g.beginPath();g.arc(x,22,kind==='bus'?3.1:2.6,0,7);g.fillStyle=dark;g.fill();g.lineWidth=1.1;g.strokeStyle='#fff';g.stroke();}
  return g.getImageData(0,0,c.width,c.height);}
 // custom sources + layers are merged INTO the style JSON, so swapping the base style can never lose them
 function custom(){const srcs={},lays=[];const S=(id,d)=>{srcs[id]=d;},Ly=(l)=>{lays.push(l);};
  S('b',{type:'geojson',data:BOUND});
  Ly({id:'boundary',type:'line',source:'b',paint:{'line-color':'#000','line-width':1.6,'line-dasharray':[0.4,2]},layout:{'line-cap':'round'}});
  S('e',{type:'geojson',data:D[DAY].e});S('n',{type:'geojson',data:D[DAY].n});S('w',{type:'geojson',data:D[DAY].w});
  S('v',{type:'geojson',data:{type:'FeatureCollection',features:[]}});S('hl',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
  Ly({id:'hl',type:'line',source:'hl',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#facc15','line-width':['+',['get','w_peak'],9],'line-opacity':.85,'line-offset':['get','off']}});
  Ly({id:'walk',type:'line',source:'w',paint:{'line-color':'#777','line-width':2,'line-dasharray':[0.5,1.5]}});
  for(const s of [...SYS].reverse()){
   Ly({id:s.key,type:'line',source:'e',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':s.color,'line-width':['get','w_peak'],'line-offset':['get','off'],'line-opacity':.85,
    ...(s.dash?{'line-dasharray':[2,1.5]}:{})}});
   Ly({id:s.key+'_lbl',type:'symbol',source:'e',layout:{'symbol-placement':'line-center','text-field':['get','t_med'],'text-size':12,'text-font':['Noto Sans Bold'],'text-allow-overlap':false},
    paint:{'text-color':s.color,'text-halo-color':'#fff','text-halo-width':2.2}});
  }
  Ly({id:'walk_lbl',type:'symbol',source:'w',layout:{'symbol-placement':'line-center','text-field':['get','lbl'],'text-size':10,'text-font':['Noto Sans Regular']},paint:{'text-color':'#555','text-halo-color':'#fff','text-halo-width':2}});
  Ly({id:'nodes',type:'symbol',source:'n',layout:{'icon-image':'n|weekday|peak|'+SK.join(',')+'|x','icon-allow-overlap':true,'icon-ignore-placement':true}});
  Ly({id:'nodes_lbl',type:'symbol',source:'n',minzoom:9.5,layout:{'text-field':['get','name'],'text-size':11.5,'text-offset':[0,1.6],'text-anchor':'top','text-font':['Noto Sans Bold']},paint:{'text-color':'#1d2433','text-halo-color':'#fff','text-halo-width':1.8}});
  Ly({id:'veh',type:'symbol',source:'v',layout:{'icon-image':['concat','veh_',['get','s'],'_',['get','f']],'icon-size':['interpolate',['linear'],['zoom'],8,.38,11,.52,14,.8],'icon-allow-overlap':true,'icon-ignore-placement':true,
    'icon-offset':['case',['==',['get','d'],0],['literal',[0,-6]],['==',['get','d'],1],['literal',[0,6]],['literal',[0,0]]]}});
  return {srcs,lays};}
 function withCustom(st){const c=custom();st.sources=Object.assign(st.sources||{},c.srcs);st.layers=(st.layers||[]).concat(c.lays);return st;}
 let needApply=true;
 async function restyle(){needApply=true;map.setStyle(withCustom(await styleFor()),{diff:false});}

 const apply=()=>{if(!map.getSource('e'))return;if(!map.isStyleLoaded()){map.once('idle',apply);return;}/* wait for the base map */for(const s of SK){
   const f=['all',['==',['get','system'],s],['>',['get','n_'+PER],0],...(PER==='night'?[['==',['get','nn'],1]]:[]),...(CONN?[['==',['get','c_'+PER],1]]:[])];
   map.setFilter(s,f);map.setFilter(s+'_lbl',f);map.setPaintProperty(s,'line-width',['get','w_'+PER]);
   map.setLayoutProperty(s+'_lbl','text-field',['get',TIME]);}
  for(const [id,k] of [['e','e'],['n','n'],['w','w']])map.getSource(id).setData(D[DAY][k]);flt();};
 const flt=()=>{
  const act=new Set(),cnt=Object.fromEntries(SK.map(k=>[k,0]));
  for(const f of D[DAY].e.features){const p=f.properties;if(p['n_'+PER]>0&&(PER!=='night'||p.nn===1)&&(!CONN||p['c_'+PER]===1)){cnt[p.system]++;if(ON.has(p.system)){act.add(p.a);act.add(p.b);}}}
  {let ns=0,so=0,dt=0;for(const g of act){const y=(D[DAY].nd[g]&&D[DAY].nd[g].sym[PER])||[];if(y.length){ns++;if(y.some(k=>k.st==='solid'))so++;else dt++;}}
   const sc=document.getElementById('symcount');sc.textContent=ns;sc.parentElement.title=so+' solid, '+dt+' dotted ('+DAY+', '+PER+')';}
  if(OFF())act.clear();
  const any=['any',...[...ON].map(s=>['==',['get','s_'+s],1])];
  const nd=['all',['>',['get','dep'],0],any,['in',['get','id'],['literal',[...act]]]];
  map.setFilter('nodes',nd);map.setFilter('nodes_lbl',nd);
  map.setLayoutProperty('nodes','icon-image',['concat','n|'+DAY+'|'+PER+'|'+SK.filter(s=>ON.has(s)).join(',')+'|',['get','id']]);
  const w=['all',['in',['get','na'],['literal',[...act]]],['in',['get','nb'],['literal',[...act]]]];
  map.setFilter('walk',w);map.setFilter('walk_lbl',w);
  for(const l of ['walk','walk_lbl'])map.setLayoutProperty(l,'visibility',WALK?'visible':'none');
  for(const k of SK){for(const id of [k,k+'_lbl'])map.setLayoutProperty(id,'visibility',ON.has(k)?'visible':'none');
   document.getElementById('nl-'+k).classList.toggle('off',!ON.has(k)||cnt[k]==0);
   document.querySelector('#ui input[data-l='+k+']').parentElement.classList.toggle('off',cnt[k]==0);}};
 map.on('styledata',()=>{if(needApply&&map.getLayer('veh')){needApply=false;theme();apply();}});   // after every style (re)load

 // ---- popups are built here for the band selected in the legend (peak / day / night)
 const BN={peak:'Peak',day:'Day',night:'Night'},pad2=(x)=>String(x).padStart(2,'0');
 const fh=(h)=>(h==null||!isFinite(h))?'no service':(h<100?Math.round(h)+' min':(h/60).toFixed(1)+' h');
 const mc=(l)=>l.length?l.map(x=>Array.isArray(x)?`<span class="mc${x[2]?'':' ig'}">:${pad2(x[0])}</span>`:`<span class="mc">:${pad2(x)}</span>`).join(''):'<span class="none">–</span>';
 const dotk=(k)=>`<i class="dotn" style="background:${COL[k]};width:9px;height:9px;vertical-align:-1px"></i>`;
 const symSvg=(hs,dot,sz)=>{const r=15;let l='',t='';for(const h of hs){const a=h*6*Math.PI/180;l+=`<line x1="0" y1="0" x2="${((r+3)*Math.sin(a)).toFixed(1)}" y2="${(-(r+3)*Math.cos(a)).toFixed(1)}" stroke="currentColor" stroke-width="2.4" ${dot?'stroke-dasharray="2.5 2.2"':'stroke-linecap="round"'}/>`;}
  for(const a of [0,90,180,270]){const q=a*Math.PI/180;t+=`<line x1="${((r-3)*Math.sin(q)).toFixed(1)}" y1="${(-(r-3)*Math.cos(q)).toFixed(1)}" x2="${(r*Math.sin(q)).toFixed(1)}" y2="${(-r*Math.cos(q)).toFixed(1)}" stroke="currentColor" opacity=".45"/>`;}
  return `<svg width="${sz||46}" height="${sz||46}" viewBox="-20 -20 40 40"><circle r="${r}" fill="none" stroke="currentColor" opacity=".5" stroke-width="1.4"/>${t}${l}</svg>`;};
 const bandPill=(b)=>`<span class="pill" title="${CFG.bands[b]}">${BN[b]} · ${CFG.bands[b]}</span>`;
 function nodePop(id){const n=D[DAY].nd[id],b=PER,q=id.replace(/'/g,"\\'");
  let h=`<div class="pp"><div class="hd" style="--c:${COL[n.sy[0].k]}"><div class="pills">${n.sy.map(s=>`<span class="pill">${CFG.names[s.k]}</span>`).join('')}${bandPill(b)}</div><h3>${n.name}</h3></div><div class="bd">`;
  const ys=n.sym[b]||[];let G=(window.SELG&&window.SELG.id===id)?window.SELG.g:0;if(G>=ys.length)G=0;
  const mn=(x)=>x.map(v=>':'+pad2(v)).join(' ');
  const inG=(d)=>ys.length&&d&&d[0]==='c'&&d[6]===G;
  if(ys.length){
   if(ys.length>1)h+=`<div class="tabs">${ys.map((y,gi)=>`<button class="${gi===G?'on':''}" onclick="window.selSym('${q}',${gi})">${symSvg(y.h,y.st==='dotted',18)} ${mn(y.h)}</button>`).join('')}</div>`;
   const y=ys[G];
   h+=`<div class="symcard${y.st==='dotted'?' dot':''}"><div class="symclock">${symSvg(y.h,y.st==='dotted')}</div><div><b>${y.st==='solid'?'Symmetry':'Half symmetry'} ${mn(y.h)}${y.p==30?' · every 30 min':''}</b>`+
      `<small>${y.lv} · ${Math.round(y.both*100)}% both ways</small></div></div>`;}
  // ---- node diagram (Knotenspinne): one spoke per direction at its real bearing, arrival / departure minutes of the
  //      symmetry lines next to the node, symmetry hand(s) in the centre
  const net=n.net&&n.net[b];
  if(net&&net.ed.length){
   const W=520,cx=W/2,cy=0,la0=net.st.reduce((s,x)=>s+x[3],0)/net.st.length,lo0=net.st.reduce((s,x)=>s+x[4],0)/net.st.length,kx=Math.cos(la0*Math.PI/180);
   const gk=String(G),hs=ys.length?ys[G].h:[];
   // one spoke per neighbour (modes / stations of the same neighbour together)
   // walk from a station of this node to its main station (the one of the popup): a spoke leaving from another station
   // (bus station, local-rail station) needs that walk for its changes
   const mainI=Math.max(0,net.st.findIndex(x=>x[0]===id)),wkTo=(i)=>i===mainI||i<0?0:((net.wk.find(w=>(w[0]===i&&w[1]===mainI)||(w[1]===i&&w[0]===mainI))||[0,0,0])[2]);
   const spk={};for(const e of net.ed){if(e[9]!=null&&!(ys.length&&e[6][gk]))continue;   // walk directions: only when used in the selected symmetry
    const k=e[9]!=null?e[1]+'¦w':e[1];const s=spk[k]||(spk[k]={nb:e[1],wk:e[9],via:e[10],sy:e[2],la:e[3],lo:e[4],ln:{},in:[],out:[],hwi:null,hwo:null,used:new Set(),fh:999});
    s.fh=Math.min(s.fh,e[7]??999,e[8]??999);
    for(const [l,h_] of e[5])spk[k].ln[l]=Math.min(spk[k].ln[l]??999,h_);
    const g=ys.length?e[6][gk]:null;if(g){if(g[0]){s.in.push(...g[0][0]);s.hwi=g[0][2];}if(g[1]){s.out.push(...g[1][0]);s.hwo=g[1][2];}g[2].forEach(x=>s.used.add(x));s.wch=Math.max(s.wch||0,g[3]||0);}s.wkc=Math.min(s.wkc??99,wkTo(e[0]));}
   for(const s of Object.values(spk))if(s.wkc===99)s.wkc=0;
   let E=Object.values(spk).map(s=>({s,a:Math.atan2((s.lo-lo0)*kx,(s.la-la0))})).sort((p,q)=>p.a-q.a);
   const minA=Math.min(0.62,2*Math.PI/Math.max(1,E.length)*0.92);
   for(let it=0;it<60;it++)for(let k=0;k<E.length;k++){const p=E[k],q=E[(k+1)%E.length];let d=q.a-p.a;if(k===E.length-1)d+=2*Math.PI;if(d<minA&&E.length>1){const f=(minA-d)/2;p.a-=f;q.a+=f;}}
   const R0=17,R1=138,Pp=ys.length?(ys[G].p||60):60;
   const off=(a,arr)=>[...new Set(a.map(x=>Math.min(...hs.map(h_=>arr?((h_-x)%Pp+Pp)%Pp:((x-h_)%Pp+Pp)%Pp))))].sort((u,v)=>u-v);
   const med=(a,arr)=>{const o=off(a,arr);return o.length?o[0]:null;};   // the timed service closest to the symmetry minute: last arrival before it / first departure after it (min)
   const tw_=(t)=>[...t].reduce((w,c)=>w+(/[0-9]/.test(c)?5.2:c==='′'?2.4:c===' '?2.6:c==='/'||c==='·'?3:5.6),0);   // approx. text width at 9px
   let sv='';const LB=[],SL=[],SEG=[];
   for(const [ki,p] of E.entries()){const s=p.s,sx=Math.sin(p.a),sy_=-Math.cos(p.a),lim=(s.sy==='bus'?12:6)+Math.max(s.wch||0,s.wkc?s.wkc+2:0);   // + walk and change penalty when its timed changes need a walk
    // numbers: the REAL timetable (all services, no arrival left out): mean over every symmetry minute in the band of the minutes
    // from the last arrival before it and to the next departure after it
    let fvi=null,fvo=null;
    if(hs.length){const T_=D[DAY],TT=(T_.tt||{})[id]||[];
     const am=TT.filter(r=>r[5]===1&&T_.ttn[r[2]]===s.nb).map(r=>r[0]).sort((u,v)=>u-v),dm=TT.filter(r=>r[5]===0&&T_.ttn[r[2]]===s.nb).map(r=>r[0]).sort((u,v)=>u-v);
     const occ=[];for(const [a0,b0] of CFG.periods[PER])for(let t=Math.floor(a0/Pp)*Pp;t<b0+Pp;t+=Pp)for(const h_ of hs){const T0=t+(h_%Pp);if(T0>=a0&&T0<b0)occ.push(T0);}
     const mean=(v)=>v.length?Math.round(v.reduce((x,y)=>x+y,0)/v.length):null;
     // to the NEAREST pulse, signed: arrivals before the symmetry minute > 0, just after it < 0 (departures the other way);
     // the symmetry minute is a computed centre, so trains a few minutes either side of it are in the same pulse
     const near=(ts,T0)=>{let b_=null;for(const x of ts){if(b_==null||Math.abs(x-T0)<Math.abs(b_-T0))b_=x;}return b_==null||Math.abs(b_-T0)>Pp/2?null:b_;};
     const occA=occ.map(T0=>{const x=near(am,T0);return x==null?null:T0-x;}).filter(x=>x!=null),occD=occ.map(T0=>{const x=near(dm,T0);return x==null?null:x-T0;}).filter(x=>x!=null);
     // no service within half a period of a pulse: fall back to the last arrival before / next departure after (longer gaps)
     fvi=occA.length?mean(occA):mean(occ.map(T0=>{let b_=null;for(const x of am){if(x<=T0)b_=x;else break;}return b_==null||T0-b_>180?null:T0-b_;}).filter(x=>x!=null));
     fvo=occD.length?mean(occD):mean(occ.map(T0=>{const x=dm.find(y=>y>=T0);return x==null||x-T0>180?null:x-T0;}).filter(x=>x!=null));
    }
    // style: a side is coordinated in this symmetry when it has timed changes in it and its timetable mean is within the window
    // (arriving / leaving at the symmetry minute itself, mean 0 min, is part of the symmetry)
    const vi=hs.length&&fvi!=null&&Math.abs(fvi)<=lim&&(s.in.length||fvi<=0)?fvi:null,vo=hs.length&&fvo!=null&&Math.abs(fvo)<=lim&&(s.out.length||fvo<=0)?fvo:null;
    // frequent (< 15 min): needs no timing, works in the symmetry and is highlighted as frequent (per direction for the style)
    let fI_=false,fO_=false;for(const e of net.ed)if(e[1]===s.nb&&(e[9]??null)===(s.wk??null)){if((e[7]??999)<CFG.freq)fI_=true;if((e[8]??999)<CFG.freq)fO_=true;}
    const wI=vi!=null||fI_,wO=vo!=null||fO_,both=wI&&wO,one=wI||wO,fq=s.fh<CFG.freq;
    // edge headways, all services (arr / dep)
    s.ahi=null;s.aho=null;for(const e of net.ed)if(e[1]===s.nb&&(e[9]??null)===(s.wk??null)){if(e[7]!=null&&e[7]<999)s.ahi=Math.min(s.ahi??999,e[7]);if(e[8]!=null&&e[8]<999)s.aho=Math.min(s.aho??999,e[8]);}
    if(fq)sv+=`<line x1="${(cx+sx*R0).toFixed(1)}" y1="${(cy+sy_*R0).toFixed(1)}" x2="${(cx+sx*R1).toFixed(1)}" y2="${(cy+sy_*R1).toFixed(1)}" stroke="${COL[s.sy]}" stroke-width="9" stroke-linecap="round" opacity=".28"/>`;
    sv+=`<line x1="${(cx+sx*R0).toFixed(1)}" y1="${(cy+sy_*R0).toFixed(1)}" x2="${(cx+sx*R1).toFixed(1)}" y2="${(cy+sy_*R1).toFixed(1)}" stroke="${one?COL[s.sy]:'#9ca3af'}" stroke-width="${one?4:2}" ${both||!one?'':'stroke-dasharray="6 4"'} stroke-linecap="round" opacity="${one?.95:.55}"/>`;
    // minutes: arrival on the left of the spoke (seen from outside), departure on the right
    // labels parallel to the spoke: arrival arrow points to the node, departure arrow away from it (text never upside down)
    let ang=Math.atan2(sy_,sx)*180/Math.PI;const flip=ang>90||ang<-90;if(flip)ang+=180;
    const outA=`<tspan class="narr">${flip?'◀':'▶'}</tspan>`,inA=`<tspan class="narr">${flip?'▶':'◀'}</tspan>`;
    const px=-sy_,py=sx;
    const ai=vi!=null?vi:fvi,ao=vo!=null?vo:fvo;
    // labels along the spoke (placed later without overlaps): arrival on one side, departure on the other; ↻ = headway of the symmetry services
    const pri=one?0:2;
    // one label on the line: "◀ min′ ↻headway │ ↻headway min′ ▶" (each arrow in its real direction: arrival towards the node, departure away);
    // ↻ = headway of the symmetry services of that direction (only on symmetry spokes)
    // each side: coordinated in the symmetry (or frequent) -> normal style; otherwise the mean of all services, muted
    const hI=vi!=null?s.hwi:null,hO=vo!=null?s.hwo:null,lc=one||fq?COL[s.sy]:'#9ca3af';
    // a side counts (normal style) when it is timed in the symmetry or its own direction is frequent (e.g. a train every 10 min leaving at :00)
    const mI=vi==null&&!fI_,mO=vo==null&&!fO_;
    const rep=(h_)=>h_?`<tspan class="nrep">↻${h_}′</tspan>`:'';
    // left part = the one whose arrow points to the left (arrival if the spoke points right, else departure)
    const half=(mn,h_,arrowLeft,mut)=>{if(mn==null)return null;const mn_=String(mn).replace('-','−'),t=arrowLeft?`<tspan class="narr">◀</tspan> ${mn_}′${h_?' '+rep(h_):''}`:`${h_?rep(h_)+' ':''}${mn_}′ <tspan class="narr">▶</tspan>`;return mut?`<tspan class="nmut">${t}</tspan>`:t;};
    const wH=(mn,h_)=>mn==null?0:7+String(mn).length*6.3+3+(h_?3+8+String(h_).length*5.2+2.5:0);
    const same=hI&&hO&&Math.abs(hI-hO)<5;    // (nearly) the same symmetry headway both ways (< 5 min apart): shown once, in the middle
    const hI_=same?null:hI,hO_=same?null:hO;
    const Lh=flip?half(ao,hO_,true,mO):half(ai,hI_,true,mI),Rh=flip?half(ai,hI_,false,mI):half(ao,hO_,false,mO);
    const wL=flip?wH(ao,hO_):wH(ai,hI_),wR=flip?wH(ai,hI_):wH(ao,hO_);
    // a divider only between a coordinated (normal) and a non-coordinated (grey) side
    const mL=flip?mO:mI,mR=flip?mI:mO,sep=(mL!==mR)?' <tspan class="nsep">│</tspan> ':'\u2002',mid=same?'\u2002'+rep(Math.round((hI+hO)/2))+'\u2002':sep;
    if(Lh||Rh)SL.push({sx,sy_,ang,cls:'nmin',t:[Lh,Rh].filter(Boolean).join(mid),col:lc,fs:11,w:wL+wR+(Lh&&Rh?10:0)+(same?30:0)+8,pri:one||fq?0:2,r0:70});
    SEG.push([sx,sy_]);
    const L=Object.entries(s.ln).map(([l,h_])=>[l.split(' ')[0].slice(0,8),h_,s.used.has(l)]).sort((u,v)=>(v[2]-u[2])||u[1]-v[1]);
    const Ls=[];for(const x of L)if(!Ls.some(y=>y[0]===x[0]))Ls.push(x);
    const lns=Ls.slice(0,3).map(([l,,u])=>`<tspan class="${u?'nsu':'nsn'}">${l}</tspan>`).join(' ')+(Ls.length>3?` <tspan class="nsn">+${Ls.length-3}</tspan>`:'');
    const hi=vi!=null?s.hwi:null,ho=vo!=null?s.hwo:null;
    const gh=[s.ahi,s.aho].map(x=>x==null?null:Math.round(x));
    // under the name: headway of the edge, all services ("arr′/dep′" when they differ)
    const hT=(a,b)=>a&&b&&Math.abs(a-b)>2?`${a}′/${b}′`:(a||b?`every ${a||b}′`:null);
    const hE=fq?`frequent · every ${Math.round(s.fh)}′`:hT(gh[0],gh[1]);
    const nl=2+(hE?1:0),side=sx>=-0.02?1:-1;
    LB.push({side,tx:cx+sx*(R1+3),ty:cy+sy_*(R1+3),h:nl*10+4,col:one||fq?COL[s.sy]:'#6b7280',nm:s.nb,wk:s.wk,lns,hE});}
   // place the spoke labels: each one moves outward along its spoke until it touches no other label and no other spoke
   {const P=[],near=(x,y,q)=>{let c=0;for(const o of P)for(const [u,v] of o.pts){const d=Math.hypot(u-x,v-y);if(d<13)c+=13-d;}
      for(const [ux,uy] of SEG){if(q&&ux===q[0]&&uy===q[1])continue;const t=Math.max(R0,Math.min(R1,(x-cx)*ux+(y-cy)*uy)),d=Math.hypot(x-cx-ux*t,y-cy-uy*t);if(d<8)c+=8-d;}return c;};
    const tW=(t,fs)=>[...t.replace(/<[^>]+>/g,'')].reduce((w,c)=>w+(/[0-9]/.test(c)?0.6:c==='′'?0.28:c===' '?0.28:c==='\u2002'?0.5:c==='·'?0.3:0.75),0)*fs+8;
    SL.sort((u,v)=>u.pri-v.pri);
    for(const L_ of SL){let best=null;
     for(let r=Math.min(L_.r0,Math.max(R0+L_.w/2,R1-L_.w/2));r<=Math.max(L_.r0,R1-L_.w/2);r+=3){const ccx=cx+L_.sx*r,ccy=cy+L_.sy_*r,n=Math.max(2,Math.round(L_.w/7));
      const pts=[];for(let k=0;k<n;k++){const f=(k/(n-1)-0.5)*(L_.w-6);pts.push([ccx+L_.sx*f,ccy+L_.sy_*f]);}
      const c=pts.reduce((a,[x,y])=>a+near(x,y,[L_.sx,L_.sy_]),0);
      if(!best||c<best.c-0.01)best={c,x:ccx,y:ccy,pts};if(c===0)break;}
     P.push(best);const hh=L_.fs+3;
     sv+=`<g transform="translate(${best.x.toFixed(1)},${best.y.toFixed(1)}) rotate(${L_.ang.toFixed(1)})"><rect x="${(-L_.w/2).toFixed(1)}" y="${(-hh/2).toFixed(1)}" width="${L_.w.toFixed(1)}" height="${hh}" rx="${hh/2}" fill="var(--bg)" stroke="${L_.col}" stroke-width="1.2"/><text dy="${(L_.fs*0.35).toFixed(1)}" class="${L_.cls}">${L_.t}</text></g>`;}}
   // labels: one column per side, stacked without overlap (leader line when moved away from the spoke tip)
   let y0=cy-R1-12,y1=cy+R1+12;
   for(const sd of [1,-1]){const B=LB.filter(b=>b.side===sd).sort((u,v)=>u.ty-v.ty);
    B.forEach(b=>b.y=b.ty-b.h/2);
    for(let it=0;it<30;it++){let mv=false;for(let k=1;k<B.length;k++){const o=B[k-1].y+B[k-1].h-B[k].y;if(o>0.5){B[k-1].y-=o/2;B[k].y+=o/2;mv=true;}}if(!mv)break;}
    for(const b of B){const x=b.tx+sd*7,yc=b.y+b.h/2,an=sd>0?'start':'end';
     if(Math.abs(yc-b.ty)>5)sv+=`<polyline points="${b.tx.toFixed(1)},${b.ty.toFixed(1)} ${(x-sd*2).toFixed(1)},${yc.toFixed(1)}" fill="none" stroke="var(--mute)" stroke-width=".6" opacity=".6"/>`;
     sv+=`<text x="${x.toFixed(1)}" y="${(b.y+10).toFixed(1)}" text-anchor="${an}" class="nlab"><tspan class="nnm" fill="${b.col}">${b.nm}</tspan>${b.wk!=null?`<tspan class="nwkl"> 🚶${b.wk}′</tspan>`:''}<tspan x="${x.toFixed(1)}" dy="10">${b.lns}</tspan>${b.hE?`<tspan x="${x.toFixed(1)}" dy="10" class="nhwg">${b.hE}</tspan>`:''}</text>`;
     y0=Math.min(y0,b.y-2);y1=Math.max(y1,b.y+b.h+2);}}
   // centre: the node with its symmetry hand(s)
   sv+=`<circle cx="${cx}" cy="${cy}" r="${R0}" fill="var(--bg)" stroke="var(--ink)" stroke-width="2"/>`;
   for(const h_ of hs){const t=h_/60*2*Math.PI;sv+=`<line x1="${cx}" y1="${cy}" x2="${(cx+Math.sin(t)*(R0-3)).toFixed(1)}" y2="${(cy-Math.cos(t)*(R0-3)).toFixed(1)}" stroke="var(--ink)" stroke-width="2.4" stroke-linecap="round" ${ys[G].st==='dotted'?'stroke-dasharray="2.5 2"':''}/>`;}
   sv=`<svg class="netsvg" viewBox="0 ${y0.toFixed(0)} ${W} ${(y1-y0).toFixed(0)}" width="100%">`+sv+`</svg>`;
   const stc=net.st.length>1?`<div class="netst">${dotk(net.st[mainI][2])} ${net.st[mainI][1]}${net.st.map((s,i)=>i===mainI?'':` · ${dotk(s[2])} 🚶${wkTo(i)}′`).join('')}</div>`:'';
   h+=`<div class="netbox">${sv}</div>${stc}`;}
  // one block per relation: station A (lines below) | → with timing / without timing, ← the same | station B (lines below)
  const f1=(v)=>v==null?'–':Math.round(v)+'′';
  const val=(w,wk,hw)=>`${f1(w)}${wk?`<i>+${Math.round(wk)}′ walk</i>`:''} · every ${f1(hw)}`;
  // two lines per direction: timed -> values with timing / values without timing (muted); otherwise the status / the values
  const dir=(d,arrow)=>{if(!d)return `<div class="dv"><span class="da">${arrow}</span><span class="l1 mu">no service</span></div>`;
   const nt=d[9]!=null?val(d[9],d[13],d[10]):'';
   const l1=d[0]==='c'?`<span class="l1 tm">${val(d[4],d[5],d[3])}</span>`:d[0]==='f'?`<span class="l1 fr">frequent${d[2]!=null&&d[9]!=null&&Math.round(d[9])===0&&d[10]===d[2]?' · direct · every '+f1(d[2]):''}</span>`:d[0]==='d'?`<span class="l1 fr">direct · every ${f1(d[2])}</span>`:`<span class="l1 mu">not timed</span>`;
   const same=(d[0]==='c'&&nt&&nt===val(d[4],d[5],d[3]))||d[14]===1||(d[0]==='f'&&d[2]!=null&&d[9]!=null&&Math.round(d[9])===0&&d[10]===d[2]);   // one line is enough
   const l2=nt&&!same?`<span class="l2" title="all services, real timetable (direct services with wait 0): mean wait and headway">${nt}</span>`:'';
   const allDirect=d[2]!=null&&d[9]!=null&&Math.round(d[9])===0&&d[10]===d[2];      // all services = the direct ones
   const l3=d[2]!=null&&d[0]!=='d'&&!allDirect?`<span class="l2" title="direct services only">direct · every ${f1(d[2])}</span>`:'';
   return `<div class="dv${inG(d)?' ing':''}"><span class="da">${arrow}</span><span class="dl">${l1}${l2}${l3}</span></div>`;};
  const lines=(L,used)=>`<div class="lns">${(L||[]).map(([l,hw])=>`<span class="ln${used.has(l)?' u':''}" onclick="window.showTT('${q}','line','${String(l).replace(/'/g,"\\'")}')" title="timetable of line ${l}"><b>${l}</b><i>${hw}′</i></span>`).join('')}</div>`;
  const stn=(lab)=>`<b class="stl" onclick="window.showTT('${q}','dir','${String(lab).replace(/'/g,"\\'")}')" title="timetable towards / from ${lab}">${lab}</b>`;
  const usedA=(x)=>new Set([...(x[8]&&x[8][11]||[]),...(x[9]&&x[9][12]||[])]),usedB=(x)=>new Set([...(x[8]&&x[8][12]||[]),...(x[9]&&x[9][11]||[])]);
  const nb=(l)=>String(l).replace(/ \((fast|slow)\)$/,'');
  const rel=(x)=>`<div class="relb"><div class="rs">${dotk(x[1])}&nbsp;${stn(nb(x[0]))}${x[0]!==nb(x[0])?' <small>'+x[0].slice(nb(x[0]).length)+'</small>':''}${lines(x[10],usedA(x))}</div><div class="rm">${dir(x[8],'→')}${dir(x[9],'←')}</div><div class="rs r">${dotk(x[5])}&nbsp;${stn(nb(x[4]))}${x[4]!==nb(x[4])?' <small>'+x[4].slice(nb(x[4]).length)+'</small>':''}${lines(x[11],usedB(x))}</div></div>`;
  const ep=n.ep[b]||[];
  const coord=ep.filter(x=>ys.length?(inG(x[8])||inG(x[9])):([x[8],x[9]].some(d=>d&&d[0]==='c')));
  const rest=ep.filter(x=>!coord.includes(x));
  const modeOf=(x)=>{const r=Math.max(SK.indexOf(x[1]),SK.indexOf(x[5]));return SK[r];};
  if(coord.length){h+=`<div class="sec">Coordinated relations</div>`+coord.map(rel).join('');}
  else if(ys.length)h+=`<div class="none">No relations in this symmetry.</div>`;
  for(const k of SK){const g=rest.filter(x=>modeOf(x)===k);if(!g.length)continue;
   h+=`<details class="fq"><summary>${dotk(k)} ${g.length} other ${CFG.names[k].toLowerCase()} relations</summary>${g.map(rel).join('')}</details>`;}
  h+=`<div class="sec">Timetable <span class="hint">arrivals and departures · ${BN[b]}</span></div>`+ttHTML(id,()=>true);
  return h+'</div></div>';}
 // ---- timetables (node, line, direction) for the selected day and time band
 const hm=(t)=>pad2(Math.floor(t/60)%24)+':'+pad2(Math.floor(t%60));
 const inPer=(t)=>CFG.periods[PER].some(([a,b])=>t>=a&&t<b);
 // one row per vehicle call: arrival, departure, line, from (origin), to (destination)
 function ttHTML(id,flt){const T=D[DAY],all=(T.tt||{})[id]||[];const calls={};
  for(const r of all){const k=r[6]+'|'+r[1];const c=calls[k]||(calls[k]={l:r[1],s:r[4],a:null,d:null,fr:null,to:null,or:null,de:null});
   if(r[5]===1){c.a=r[0];c.fr=r[2];c.or=r[3];}else{c.d=r[0];c.to=r[2];c.de=r[3];}}
  // trips split at this station (same line, arrival then departure within 15 min, not going back): one call
  const cl=Object.values(calls),oa=cl.filter(c=>c.d==null).sort((x,y)=>x.a-y.a),od=cl.filter(c=>c.a==null).sort((x,y)=>x.d-y.d),used=new Set();
  for(const c of oa){const m=od.find(e=>!used.has(e)&&e.l===c.l&&e.d>=c.a&&e.d-c.a<=15&&T.ttn[e.to]!==T.ttn[c.fr]);
   if(m){used.add(m);c.d=m.d;c.to=m.to;c.de=m.de;m.dead=true;}}
  for(const k in calls)if(calls[k].dead)delete calls[k];
  const rows=Object.values(calls).filter(c=>(c.a!=null&&inPer(c.a))||(c.d!=null&&inPer(c.d))).filter(flt).sort((x,y)=>(x.d??x.a)-(y.d??y.a));
  if(!rows.length)return '<div class="none">No services in this period.</div>';
  const nm=(i)=>i==null?'':T.ttn[i];
  const twn=(s)=>String(s).split(' · ')[0];
  const end=(i,j,w)=>i==null?'<span class="mu">–</span>':nm(i)+(j!=null&&twn(nm(j))!==twn(nm(i))?` <small>(${w} ${nm(j)})</small>`:'');
  return `<div class="ttb"><table class="tt ttt"><tr class="th"><td>arr</td><td>dep</td><td>line</td><td>from</td><td>to</td></tr>${rows.map(c=>`<tr><td class="tm2">${c.a!=null?hm(c.a):'–'}</td><td class="tm2"><b>${c.d!=null?hm(c.d):'–'}</b></td><td>${dotk(SK[c.s])}&nbsp;<span class="lnb" onclick="window.showTT('${id.replace(/'/g,"\\'")}','line','${T.ttl[c.l].replace(/'/g,"\\'")}')">${T.ttl[c.l]}</span></td><td>${end(c.fr,c.or,'from')}</td><td>${end(c.to,c.de,'to')}</td></tr>`).join('')}</table></div>`;}
 const hlSet=(fs)=>{const s=map.getSource('hl');if(s)s.setData({type:'FeatureCollection',features:fs||[]});};
 const hlDir=(id,val)=>{const T=D[DAY],strip=(s)=>String(s).replace(/ \((fast|slow)\)$/,'');
  hlSet(T.e.features.filter(f=>{const e=T.ed[f.properties.ei];return (f.properties.a===id&&strip(e.b)===strip(val))||(f.properties.b===id&&strip(e.a)===strip(val));}));};
 window.closeTT=()=>{document.getElementById('ttpanel').hidden=true;hlSet([]);};
 window.showTT=(id,kind,val)=>{const T=D[DAY],n=T.nd[id];if(!n)return;const box=document.getElementById('ttpanel');
  if(kind==='dir')hlDir(id,val);else hlSet([]);
  let title,body;
  if(kind==='line'){const li=T.ttl.indexOf(val);title=`Line ${val} at ${n.name}`;body=ttHTML(id,c=>c.l===li);}
  else{const ni=T.ttn.indexOf(val);title=`${n.name} ⇄ ${val}${val===n.name?' (other station)':''}`;body=ttHTML(id,c=>c.to===ni||c.fr===ni);}
  box.innerHTML=`<div class="pp"><div class="hd" style="--c:#334155"><div class="pills">${bandPill(PER)}</div><h3>${title}</h3><button class="ttx" onclick="window.closeTT()" title="Close (Esc)">✕</button></div><div class="bd">${body}</div></div>`;box.hidden=false;};
 function edgePop(i){const e=D[DAY].ed[i],b=PER,q=e.hw[b],m=e.mn[b];
  let h=`<div class="pp"><div class="hd" style="--c:${COL[e.k]}"><div class="pills"><span class="pill">${CFG.names[e.k]}</span>${bandPill(b)}</div><h3>${e.a} <span class="arr">↔</span> ${e.b}</h3></div><div class="bd">`;
  h+=`<div class="stat">Travel time · min <b>${e.tt[0]}′</b> · median <b>${e.tt[1]}′</b> · max <b>${e.tt[2]}′</b></div>`;
  h+=`<div class="stat"><b>${q[2]}</b> services · <b>${q[3]}</b> lines · longest wait <b>${fh(q[1])}</b></div>`;
  const hd=(e.hd&&e.hd[b])||[null,null],hv=(x)=>x==null?'no service':'every <b>'+fh(x)+'</b>';
  for(const [f,t,j] of [[e.a,e.b,0],[e.b,e.a,1]])h+=`<div class="dirb"><div class="dh"><span>${f} <span class="arr">→</span> ${t}</span><span class="hwt">${hv(hd[j])}</span></div><div class="mins">${mc(m[j])}</div></div>`;
  h+=`<div class="chips" style="margin-top:6px">${e.rt.map(x=>`<span class="chip">${x}</span>`).join('')}</div></div></div>`;return h;}
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){const t=document.getElementById('ttpanel');if(!t.hidden){window.closeTT();return;}const i=document.getElementById('info');if(!i.hidden){i.hidden=true;try{ANIM.stop();}catch(_){}}}});
 window.selSym=(id,g)=>{window.SELG={id,g};if(POP)POP.setHTML(nodePop(id));};
 const popHtml=(f)=>f.layer.id==='nodes'?nodePop(f.properties.id):(SK.includes(f.layer.id)?edgePop(f.properties.ei):f.properties.html);
 // ONE click handler: the top-most feature wins (nodes > connections > walking links); only one popup is open
 let POP=null,CURF=null;const ORDER=()=>['nodes',...SK,'walk'].filter(l=>map.getLayer(l));
 const hit=(pt)=>{const pad=4,box=[[pt.x-pad,pt.y-pad],[pt.x+pad,pt.y+pad]];for(const l of ORDER()){const f=map.queryRenderedFeatures(box,{layers:[l]});if(f.length)return f[0];}return null;};
 map.on('click',e=>{window.closeTT();if(POP){POP.remove();POP=null;}const f=hit(e.point);if(!f)return;
  POP=new maplibregl.Popup({maxWidth:'460px',offset:8,closeOnClick:true}).setLngLat(f.layer.id==='nodes'?f.geometry.coordinates:e.lngLat).setHTML(popHtml(f)).addTo(map);CURF=f;if(SK.includes(f.layer.id)){const p=f.properties,ed=D[DAY].ed[p.ei];if(ed&&D[DAY].nd[p.a]){window.showTT(p.a,'dir',ed.b);hlSet([f]);}}});
 map.on('mousemove',e=>{map.getCanvas().style.cursor=hit(e.point)?'pointer':'';});
 // ---- video mode
 const ck=document.getElementById('ticks');for(let i=0;i<12;i++){const a=i*Math.PI/6;ck.insertAdjacentHTML('beforeend',`<line x1="${Math.sin(a)*26}" y1="${-Math.cos(a)*26}" x2="${Math.sin(a)*(i%3?28:24)}" y2="${-Math.cos(a)*(i%3?28:24)}" stroke="var(--ink)" stroke-width="${i%3?1:2}"/>`);}
 window.VID={on:false,T:390,sp:3,playing:false,last:0};const BAND=Object.fromEntries(Object.entries(CFG.periods).map(([k,w])=>[k,w[0][0]]));
 const inBand=(T)=>{const W=CFG.periods[PER];for(const [a,b] of W)if(T>=a&&T<b)return T;for(const [a,b] of W)if(T<a)return a;return W[0][0];};
 const setClock=()=>{const T=VID.T,h=Math.floor(T/60)%24,m=Math.floor(T%60);
  document.getElementById('ctime').textContent=String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');
  document.getElementById('hh').setAttribute('transform','rotate('+((h%12)*30+m*0.5)+')');document.getElementById('mh').setAttribute('transform','rotate('+(m*6)+')');
  document.getElementById('cslider').value=T;};
 const PIX={peak:0,day:1,night:2};
 const ecn=(i)=>{const e=D[DAY].ed[i];return !!(e&&e.cn&&e.cn[PER]);};   // edge takes part in a working connection in this band
 const efq=(i)=>{const q=D[DAY].ed[i].hw[PER];return q&&q[0]!=null&&q[0]<CFG.freq;};   // edge headway of the selected band (all lines together)
 const frame=(ts)=>{if(!VID.on)return;if(VID.playing&&VID.last){VID.T=inBand(VID.T+(ts-VID.last)/1000*VID.sp);}VID.last=ts;setClock();
  const T=VID.T,feats=[],E=D[DAY].e.features;
  const G=0.5*VID.sp/60;   // 0.5 real second, in timetable minutes
  for(const L of D[DAY].legs){if(L[2]-G>T)break;if(T>=L[2]+L[3]+G)continue;if(T<L[2]&&!L[6])continue;if(T>=L[2]+L[3]&&!L[7])continue;const s=SK[L[4]];if(OFF()||!ON.has(s)||(VID.hidef&&(L[5]||efq(L[0])))||((CONN||VID.conn)&&!(ecn(L[0])&&(L[8]>>PIX[PER]&1))))continue;
   const f=E[L[0]],c=f.geometry.coordinates;let u=Math.min(1,Math.max(0,(T-L[2])/L[3]));if(L[1])u=1-u;
   feats.push({type:'Feature',geometry:{type:'Point',coordinates:[c[0][0]+(c[1][0]-c[0][0])*u,c[0][1]+(c[1][1]-c[0][1])*u]},properties:{s,d:L[1],f:((c[1][0]-c[0][0])*(L[1]?-1:1)>=0)?'r':'l'}});}
  for(const Y of D[DAY].lay){if(Y[2]>T)break;if(T>=Y[3]||(Y[6]&&T>=Y[2]+0.5*VID.sp/60))continue;const s=SK[Y[4]];if(OFF()||!ON.has(s)||(VID.hidef&&(Y[5]||efq(Y[7])))||((CONN||VID.conn)&&!ecn(Y[7])))continue;feats.push({type:'Feature',geometry:{type:'Point',coordinates:[Y[0],Y[1]]},properties:{s,d:2,f:'r'}});}   // stopped, waiting to reverse
  const src=map.getSource('v');if(src)src.setData({type:'FeatureCollection',features:feats});requestAnimationFrame(frame);};
 document.getElementById('vbtn').onclick=function(){VID.on=!VID.on;this.classList.toggle('on',VID.on);this.textContent=VID.on?'Close video':'Open video';
  document.getElementById('clock').style.display=VID.on?'block':'none';
  if(VID.on){VID.playing=false;VID.last=0;const pb=document.getElementById('cplay');pb.textContent='▶ Play';pb.classList.remove('on');document.getElementById('cday').textContent=DAY;requestAnimationFrame(frame);}
  else{const src=map.getSource('v');if(src)src.setData({type:'FeatureCollection',features:[]});}};
 document.getElementById('cplay').onclick=function(){VID.playing=!VID.playing;this.textContent=VID.playing?'⏸ Pause':'▶ Play';this.classList.toggle('on',VID.playing);VID.last=0;};
 document.getElementById('hidef').onchange=function(){VID.hidef=this.checked;};
 document.getElementById('connv').onchange=function(){VID.conn=this.checked;};
 document.getElementById('connonly').onchange=function(){CONN=this.checked;const v=document.getElementById('connv');v.disabled=CONN;if(CONN)v.checked=true;else v.checked=!!VID.conn;
  document.getElementById('connfl').classList.toggle('dis',CONN);apply();};
 document.getElementById('infobtn').onclick=()=>{document.getElementById('info').hidden=false;ANIM.start();};
 document.getElementById('infox').onclick=()=>{document.getElementById('info').hidden=true;ANIM.stop();};
 document.getElementById('info').onclick=(e)=>{if(e.target.id==='info'){e.currentTarget.hidden=true;ANIM.stop();}};
 // ---- explanation animation: an invented station with a pulse at :00 (trains arrive :55-:57, buses up to :48-:52, all leave :00-:05)
 const ANIM=(()=>{const cv=document.getElementById('anim'),g=cv.getContext('2d'),W=cv.width,H=cv.height;let raf=0,t0=0;
  const css=(v)=>getComputedStyle(document.body).getPropertyValue(v).trim()||'#222';
  const RED=(COL[SK[0]]||'#d62728'),GRN=(SK[1]&&COL[SK[1]])||'#2ca02c',BLU=COL[SK[SK.length-1]]||'#1f77b4';
  // vehicles: [kind, colour, y, from x, stop x, to x, arrive min, depart min, label]
  // 2 running tracks; at the station 4 tracks: fast trains on the centre tracks, locals on the outer ones (overtaken)
  // vehicle: [kind, colour, main track y, station track y, from x, stop x, to x, arrive min, depart min, label]
  const yA=118,yB=150,oA=86,oB=182,S0=140,S1=W-140;
  const V=[['r',GRN,yA,oA,-140,270,W+140,50,2,'local A'],['r',GRN,yB,oB,W+140,450,-140,51,3,'local B'],
   ['t',RED,yA,yA,-180,330,W+180,55,0,'fast train A'],['t',RED,yB,yB,W+180,390,-180,56,1,'fast train B'],
   ['b',BLU,0,250,-80,170,-80,49,2,'bus 1'],['b',BLU,0,250,W+80,330,W+80,50,3,'bus 2'],['b',BLU,0,296,W+80,520,W+80,48,4,'bus 3']];
  const pos=(v,m)=>{const tr=4,a=v[7],d=v[8]+(v[8]<30?60:0),mm=m<30?m+60:m;
   if(mm<a-tr||mm>d+tr)return null;if(mm<a)return v[4]+(v[5]-v[4])*(1-(a-mm)/tr);if(mm<=d)return v[5];return v[5]+(v[6]-v[5])*((mm-d)/tr);};
  const ypos=(v,x)=>{if(v[0]==='b')return v[3];const r=30;const f=x<S0-r||x>S1+r?0:(x<S0?(x-(S0-r))/r:(x>S1?((S1+r)-x)/r:1));return v[2]+(v[3]-v[2])*Math.max(0,Math.min(1,f));};
  const draw=(m)=>{const ink=css('--ink'),mute=css('--mute');g.clearRect(0,0,W,H);
   g.fillStyle=css('--soft');g.fillRect(0,0,W,H);
   // platforms (islands between an outer and a centre track: cross-platform changes)
   g.fillStyle='rgba(120,120,120,.28)';g.fillRect(S0+10,oA+12,S1-S0-20,yA-oA-20);g.fillRect(S0+10,yB+12,S1-S0-20,oB-yB-20);
   g.fillStyle=mute;g.font='10px sans-serif';g.fillText('platform',S0+16,oA+24);g.fillText('platform',S0+16,yB+24);
   // tracks: 2 running tracks, splitting into 4 at the station
   g.strokeStyle=mute;g.lineWidth=2;
   for(const y of [yA,yB]){g.beginPath();g.moveTo(0,y+9);g.lineTo(W,y+9);g.stroke();}
   for(const [ym,yo] of [[yA,oA],[yB,oB]]){g.beginPath();g.moveTo(S0-30,ym+9);g.lineTo(S0,yo+9);g.lineTo(S1,yo+9);g.lineTo(S1+30,ym+9);g.stroke();}
   g.fillStyle='rgba(120,120,120,.18)';g.fillRect(120,226,460,96);g.fillStyle=mute;g.fillText('bus station',128,316);
   const mm=m<30?m+60:m;if(mm>=57&&mm<=61){g.fillStyle=ink;for(let i=0;i<16;i++){const p=((mm-57)/4+i/16)%1,x0=S0+30+i*24,y0=i%2?oA+20:yB+20,y1=i%3?yA+20:(i%2?262:300);g.globalAlpha=.7;g.beginPath();g.arc(x0+(i%2?16:-8)*p,y0+(y1-y0)*p,2.6,0,7);g.fill();}g.globalAlpha=1;}
   for(const v of V){const x=pos(v,m);if(x==null)continue;const L=v[0]==='t'?150:v[0]==='r'?96:52,h=v[0]==='b'?20:16,y=ypos(v,x)-h/2+(v[0]==='b'?0:2);
    g.fillStyle=v[1];g.strokeStyle='#fff';g.lineWidth=1.5;g.beginPath();g.roundRect?g.roundRect(x-L/2,y,L,h,5):g.rect(x-L/2,y,L,h);g.fill();g.stroke();
    g.fillStyle='rgba(255,255,255,.9)';for(let k=x-L/2+8;k<x+L/2-10;k+=14)g.fillRect(k,y+4,8,5);
    g.fillStyle=ink;g.font='10px sans-serif';g.fillText(v[9],x-L/2,y-3);}
   const cx=W-48,cy=40,R=28;g.fillStyle=css('--bg');g.strokeStyle=ink;g.lineWidth=2;g.beginPath();g.arc(cx,cy,R,0,7);g.fill();g.stroke();
   g.strokeStyle='#000';g.lineWidth=2;g.beginPath();g.moveTo(cx,cy);g.lineTo(cx,cy-R);g.stroke();
   const a=m/60*2*Math.PI-Math.PI/2;g.strokeStyle='#d62728';g.lineWidth=2.4;g.beginPath();g.moveTo(cx,cy);g.lineTo(cx+Math.cos(a)*(R-5),cy+Math.sin(a)*(R-5));g.stroke();
   g.fillStyle=ink;g.font='bold 15px sans-serif';g.fillText(':'+String(Math.floor(m)%60).padStart(2,'0'),cx-62,cy+5);
   g.font='12px sans-serif';const txt=mm<53?'the local trains and the buses arrive first (outer tracks, bus station)':mm<57?'the fast trains arrive on the centre tracks; the locals wait':mm<=61?'symmetry minute :00 - changes across the platform - the fast trains leave first':mm<=64?'the locals follow behind the fast trains':'all have left';g.fillText(txt,16,22);};
  const loop=(ts)=>{if(!t0)t0=ts;const m=(47+((ts-t0)/1000*2.0)%22)%60;draw(m);raf=requestAnimationFrame(loop);};   // :47 -> :09, then again
  return {start(){t0=0;cancelAnimationFrame(raf);raf=requestAnimationFrame(loop);},stop(){cancelAnimationFrame(raf);},frame:draw};})();
 window.__ANIM=ANIM;
 document.getElementById('cslider').oninput=function(){VID.T=+this.value;setClock();};
 document.querySelectorAll('#clock [data-sp]').forEach(b=>b.onclick=()=>{VID.sp=+b.dataset.sp;document.querySelectorAll('#clock [data-sp]').forEach(x=>x.classList.toggle('on',x===b));});
 // ---- service supply (vehicle-km) table
 const supply=()=>{const vk=D[DAY].vehkm||{},P=CFG.pop;let tot=0,h='<tr><th></th><th>veh-km</th><th>per 1000 pop</th></tr>';
  for(const s of SYS){const on=ON.has(s.key),v=on?(vk[s.key]||0):0;tot+=v;h+=`<tr style="${on?'':'opacity:.35'}"><td><i class="dotn" style="background:${s.color};width:9px;height:9px"></i> ${CFG.names[s.key]}</td><td>${on?Math.round(v).toLocaleString('en'):'–'}</td><td>${on&&P?(v/P*1000).toFixed(1):'–'}</td></tr>`;}
  h+=`<tr class="tot"><td>Total</td><td>${Math.round(tot).toLocaleString('en')}</td><td>${P?(tot/P*1000).toFixed(1):'–'}</td></tr>`;document.getElementById('supply').innerHTML=h;};
 // ---- UI
 const seg=(g)=>document.querySelector('#ui .seg[data-g='+g+']');
 const mark=(g,v)=>seg(g).querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.v===v));const tb=document.getElementById('themebtn');const tIcon=()=>{tb.textContent=MODE==='dark'?'☀':'☾';};tIcon();tb.onclick=async()=>{MODE=MODE==='dark'?'light':'dark';tIcon();try{localStorage.setItem('mapPrefs',JSON.stringify({base:BASE,mode:MODE}));}catch(e){}document.body.classList.toggle('dark',MODE==='dark');restyle();};const bs=document.getElementById('basesel');bs.value=BASE;bs.onchange=async()=>{BASE=bs.value;try{localStorage.setItem('mapPrefs',JSON.stringify({base:BASE,mode:MODE}));}catch(e){}restyle();};
 document.querySelectorAll('#ui .seg').forEach(g=>g.querySelectorAll('button').forEach(b=>b.onclick=async()=>{
  g.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');const gg=g.dataset.g,v=b.dataset.v;
    if(gg=='per'){PER=v;VID.T=BAND[PER];}else if(gg=='day'){DAY=v;document.getElementById('cday').textContent=DAY;supply();if(POP){POP.remove();POP=null;CURF=null;}}else TIME=v;apply();if(gg=='per'&&POP&&CURF){try{POP.setHTML(popHtml(CURF));}catch(e){POP.remove();POP=null;}}}));
 document.querySelectorAll('#ui input[type=checkbox][data-l]').forEach(cb=>cb.onchange=()=>{const l=cb.dataset.l;
  if(l=='walk'){WALK=cb.checked;}else{cb.checked?ON.add(l):ON.delete(l);}flt();supply();});
 document.body.classList.toggle('dark',MODE==='dark');setClock();supply();
})();
</script></body></html>"""
