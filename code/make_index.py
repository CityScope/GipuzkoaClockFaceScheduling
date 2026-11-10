"""Build the GitHub Pages front page (index.html) and HTML versions of the rules and literature notes (docs/).

    python3 code/make_index.py
"""
import importlib
import html
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code"))
REGIONS = ["gipuzkoa", "vorarlberg", "aargau", "luzern", "oberoesterreich"]
COUNTRY = {"gipuzkoa": "Spain · Basque Country", "vorarlberg": "Austria", "aargau": "Switzerland",
           "luzern": "Switzerland", "oberoesterreich": "Austria"}
NICE = {"gipuzkoa": "Gipuzkoa", "vorarlberg": "Vorarlberg", "aargau": "Aargau", "luzern": "Luzern",
        "oberoesterreich": "Oberösterreich"}

CSS = """
:root{--ink:#1d2433;--mute:#5d6678;--line:#e2e6ee;--bg:#f6f7fa;--card:#fff;--acc:#c62828;--link:#1d4ed8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#e8ebf2;--mute:#a3abba;--line:#2e3646;--bg:#161b25;--card:#1f2633;--acc:#ef5350;--link:#93b4ff}}
:root[data-theme="dark"]{--ink:#e8ebf2;--mute:#a3abba;--line:#2e3646;--bg:#161b25;--card:#1f2633;--acc:#ef5350;--link:#93b4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--link)}main{max-width:1100px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:28px;margin:0 0 6px}h2{font-size:18px;margin:32px 0 12px}.lead{color:var(--mute);max-width:760px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:transform .12s,box-shadow .12s}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 20px #0002}
.card img{width:100%;aspect-ratio:4/3;object-fit:cover;background:#fff;border-bottom:1px solid var(--line)}
.card .b{padding:12px 14px}.card h3{margin:0;font-size:17px}.card .c{color:var(--mute);font-size:13px}
.card .s{display:flex;gap:14px;margin-top:8px;font-size:13px}.card .s b{font-size:16px;display:block}
.links{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.links a{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-decoration:none;color:inherit}
.links a b{color:var(--link)}.links a span{display:block;color:var(--mute);font-size:13px}
.leg{display:flex;flex-wrap:wrap;gap:16px;color:var(--mute);font-size:13px;margin-top:12px}.leg i{display:inline-block;width:18px;height:4px;border-radius:2px;vertical-align:middle;margin-right:6px}
footer{color:var(--mute);font-size:12.5px;margin-top:36px;border-top:1px solid var(--line);padding-top:14px}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 28px 24px;max-width:900px;margin:0 auto}
article table{border-collapse:collapse;font-size:13.5px;width:100%;display:block;overflow-x:auto}article td,article th{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
article code{background:var(--bg);padding:1px 4px;border-radius:4px;font-size:90%}
.back{display:inline-block;margin-bottom:14px}
"""


def page(title, body, desc=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}"><style>{CSS}</style></head>
<body><main>{body}</main></body></html>"""


def stats(r):
    try:
        n = pd.read_csv(os.path.join(ROOT, "output", r, "nodes.csv"))
        s = pd.read_csv(os.path.join(ROOT, "output", r, "symmetry.csv"))
        return n["group"].nunique(), s[s.band == "peak"].gid.nunique()
    except Exception:
        return None, None


def md_page(src, out, title):
    import markdown
    txt = open(os.path.join(ROOT, src), encoding="utf-8").read()
    body = markdown.markdown(txt, extensions=["tables", "fenced_code", "sane_lists"])
    os.makedirs(os.path.dirname(os.path.join(ROOT, out)), exist_ok=True)
    open(os.path.join(ROOT, out), "w", encoding="utf-8").write(
        page(title, f'<a class="back" href="../index.html">← all regions and explainers</a><article>{body}</article>'))


def clock_phase_page():
    """explain/clock-phase/index.html: the hub animation of the map's info panel (code taken from make_map.py)."""
    src = open(os.path.join(ROOT, "code", "make_map.py"), encoding="utf-8").read()
    a = src.index(" const ANIM=(()=>{"); b = src.index(" window.__ANIM=ANIM;")
    js = src[a:b]
    css = CSS + """:root{--soft:#eceff4}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--soft:#262e3d}}:root[data-theme="dark"]{--soft:#262e3d}
canvas{width:100%;height:auto;display:block;border-radius:12px;background:var(--soft)}.stage{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px}
ul{color:var(--ink);font-size:14.5px;line-height:1.55;padding-left:20px}main{max-width:920px}"""
    body = """<a class="back" href="../../index.html">← all regions and explainers</a>
<h1>How clock-phase scheduling works</h1>
<p class="lead">One hub, one pulse. All lines repeat at the same rhythm and meet around a common minute, the symmetry minute (here :00).</p>
<div class="stage"><canvas id="anim" width="720" height="330"></canvas></div>
<ul>
<li>Local trains and buses arrive first, a few minutes before the symmetry minute. Buses may arrive up to 12′ early.</li>
<li>The fast trains arrive last, on the centre tracks, just before :00.</li>
<li>Around :00 everyone changes, often just across the platform. Then the fast trains leave first, and the locals and buses follow.</li>
<li>Arrivals before the minute mirror the departures after it, so the same changes work in every direction. This is what makes a hub symmetric.</li>
<li>Next: <a href="../symmetry/">why symmetry is needed and not just coordination</a>.</li>
</ul>"""
    script = """<script>
const SK=['bigrail','localrail','bus'],COL={bigrail:'#d32f2f',localrail:'#2e7d32',bus:'#1e6fd9'};
""" + js + """ANIM.start();
</script>"""
    out = os.path.join(ROOT, "explain", "clock-phase", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clock-Phase Scheduling</title><meta name="description" content="Animation of a clock-face timetable hub (Taktknoten)."><style>{css}</style></head>
<body><main>{body}</main>{script}</body></html>""")


def main():
    cards = []
    for r in REGIONS:
        mp = f"maps/{r}/"
        if not os.path.exists(os.path.join(ROOT, mp, "index.html")):
            continue
        try:
            title = importlib.import_module(f"regions.{r}").TITLE
        except Exception:
            title = NICE[r]
        nn, ns = stats(r)
        img = f"output/{r}/overview.png"
        im = f'<img src="{img}" alt="Network overview of {NICE[r]}" loading="lazy">' if os.path.exists(os.path.join(ROOT, img)) else ""
        cards.append(f"""<a class="card" href="{mp}">{im}<div class="b"><h3>{NICE[r]}</h3><div class="c">{COUNTRY[r]} · {html.escape(title)}</div>
<div class="s"><div><b>{nn if nn is not None else '–'}</b>nodes</div><div><b>{ns if ns is not None else '–'}</b>symmetry nodes (peak)</div></div></div></a>""")
    md_page("sources/network_rules.md", "docs/rules.html", "Network rules")
    md_page("literature/taktfahrplan_review.md", "docs/literature.html", "Literature notes")
    md_page("README.md", "docs/readme.html", "README")
    clock_phase_page()
    papers = sorted(os.listdir(os.path.join(ROOT, "literature", "papers")))
    plinks = "".join(f'<a href="literature/papers/{p}"><b>{html.escape(p.rsplit(".", 1)[0].replace("_", " "))}</b><span>PDF</span></a>' for p in papers)
    body = f"""<h1>Takt / timetable network maps</h1>
<p class="lead">Interactive maps of the regional public-transport network built from GTFS timetables: nodes, links and headways,
timed connections between directions, and symmetry nodes (Taktknoten) where arrivals come just before and departures just after a
common minute. Choose a region to open its map — the day and time band can be changed on the map; click a node for its symmetry diagram,
connections and timetable.</p>
<div class="leg"><span><i style="background:#d32f2f"></i>national / mainline rail</span><span><i style="background:#2e7d32"></i>local rail</span><span><i style="background:#1e6fd9"></i>regional bus</span></div>
<h2>Regions</h2><div class="grid">{''.join(cards)}</div>
<h2>Explainers</h2><div class="links">
<a href="explain/clock-phase/"><b>How clock-phase scheduling works</b><span>Animation of a pulse at a hub: locals and buses arrive first, fast trains at the symmetry minute, everyone changes and leaves</span></a>
<a href="explain/symmetry/"><b>Why symmetry, not just coordination</b><span>Animation: different headways, a timed line without symmetry, symmetric hubs, and the loop condition in a grid</span></a></div>
<h2>Method and background</h2><div class="links">
<a href="docs/rules.html"><b>Network rules</b><span>How nodes, links, connections and symmetries are defined</span></a>
<a href="docs/literature.html"><b>Literature notes</b><span>Taktfahrplan / ITF review with page references</span></a>
<a href="docs/readme.html"><b>README · code</b><span>Folders, how to run the Python analysis and map generation</span></a></div>
<h2>Papers</h2><div class="links">{plinks}</div>
<footer>Timetable data: Mobilitätsverbünde Österreich OG (Austria), opentransportdata.swiss (Switzerland), Basque / Spanish open data and
Transitland (Gipuzkoa). Base map: OpenFreeMap / OpenStreetMap contributors; satellite: Esri. Population: WorldPop.
Papers are the property of their authors and publishers.</footer>"""
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(
        page("Takt network maps", body, "Interactive public-transport network and symmetry-node maps for five regions"))
    print("index.html, docs/rules.html, docs/literature.html written")


if __name__ == "__main__":
    main()
