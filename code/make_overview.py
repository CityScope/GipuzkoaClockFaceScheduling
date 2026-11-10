"""Static overview of a region (output/<region>/overview.svg + overview.png via Chromium): boundary, connections
(colour = system, width = trips), nodes (merged nodes as multi-colour pies) and symmetry-minute hands.
Run: python3 code/make_overview.py <region>"""
import os, sys, json, math, subprocess
os.environ["REGION"] = sys.argv[1]
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
import numpy as np, pandas as pd
import towns
from analysis import merge_groups

R = Path(__file__).parent.parent
out = R / "output" / sys.argv[1]
node = pd.read_csv(out / "nodes.csv", index_col=0)
edges = pd.read_csv(out / "edges.csv")
sym = pd.read_csv(out / "symmetry.csv"); sym = sym[sym.band == "peak"].set_index("gid")      # peak band hands
groups = merge_groups(node)
mem = {}
for k, g in groups.items():
    mem.setdefault(g, []).append(k)
pos = {g: (node.loc[m, "lon"].mean(), node.loc[m, "lat"].mean()) for g, m in mem.items()}
S = towns.SYSTEMS; keys = list(S)
bj = json.load(open(R / towns.BOUNDARY_FILE))
lines = []
for f in bj["features"]:
    gm = f["geometry"]; lines += gm["coordinates"] if gm["type"] == "MultiLineString" else [gm["coordinates"]]
allx = [p[0] for p in pos.values()] + [c[0] for l in lines for c in l]; ally = [p[1] for p in pos.values()] + [c[1] for l in lines for c in l]
x0, x1, y0, y1 = min(allx), max(allx), min(ally), max(ally)
k = math.cos(math.radians((y0 + y1) / 2)); W = 1500; sc = W / ((x1 - x0) * k + 0.02); H = int(((y1 - y0) + 0.02) * sc) + 40
X = lambda lon: ((lon - x0) * k + 0.01) * sc; Y = lambda lat: (y1 - lat + 0.01) * sc + 20
svg = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' style='background:#f3f5f8;font-family:sans-serif'>"]
for l in lines:
    svg.append("<polyline fill='none' stroke='#000' stroke-width='1.2' stroke-dasharray='1 4' points='" + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in l) + "'/>")
for r in edges.sort_values("trips_day").itertuples():
    a, b = pos[groups[r.a]], pos[groups[r.b]]
    svg.append(f"<line x1='{X(a[0]):.1f}' y1='{Y(a[1]):.1f}' x2='{X(b[0]):.1f}' y2='{Y(b[1]):.1f}' stroke='{S[r.mode]['color']}' "
               f"stroke-width='{0.7 + min(r.trips_day / 60, 3.5):.1f}' stroke-opacity='.75'" + (" stroke-dasharray='6 4'" if S[r.mode]["dash"] else "") + "/>")
dep = node.assign(g=node.index.map(groups)).groupby("g").departures.sum()
for g, m in mem.items():
    sy = sorted({node.loc[q, "system"] for q in m}, key=keys.index); x, y = X(pos[g][0]), Y(pos[g][1]); r = 3.5 + 0.28 * math.sqrt(dep[g])
    if len(sy) == 1:
        svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r:.1f}' fill='{S[sy[0]]['color']}' stroke='#fff' stroke-width='1.2'/>")
    else:
        for i, s_ in enumerate(sy):                        # concentric rings (slices would look like a symmetry hand)
            ri = r * (1 - i / len(sy))
            svg.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{ri:.1f}' fill='{S[s_]['color']}' stroke='#fff' stroke-width='{1.2 if i == 0 else 1}'/>")
    for _, sr in sym[sym.index == g].iterrows():
        dash = " stroke-dasharray='2.5 2'" if sr.get("style", "solid") == "dotted" else " stroke-linecap='round'"
        for h in [int(x) for x in str(sr["hands"]).split(",")]:
            a = math.radians(h * 6); svg.append(f"<line x1='{x:.1f}' y1='{y:.1f}' x2='{x + (r + 3) * math.sin(a):.1f}' y2='{y - (r + 3) * math.cos(a):.1f}' stroke='#000' stroke-width='2'{dash}/>")
for g in dep.nlargest(30).index:
    svg.append(f"<text x='{X(pos[g][0]) + 6:.1f}' y='{Y(pos[g][1]) - 6:.1f}' font-size='11' fill='#222' stroke='#fff' stroke-width='3' paint-order='stroke'>{node.loc[mem[g][0], 'town']}</text>")
svg.append(f"<text x='14' y='20' font-size='15' font-weight='bold'>{towns.TITLE} - weekday: {len(node)} nodes, {len(edges)} connections, {sym.index.nunique()} symmetry nodes (peak)</text></svg>")
p = out / "overview.svg"; p.write_text("\n".join(svg), encoding="utf-8")
subprocess.run(["chromium", "--headless=new", "--no-sandbox", f"--window-size={W},{H}", f"--screenshot={out / 'overview.png'}", f"file://{p}"], capture_output=True)
print("wrote", out / "overview.png", W, H)
