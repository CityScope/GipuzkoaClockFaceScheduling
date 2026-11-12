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
        return n["group"].nunique(), s[s.band == "day"].gid.nunique()
    except Exception:
        return None, None


def md_page(src, out, title):
    import markdown
    txt = open(os.path.join(ROOT, src), encoding="utf-8").read()
    body = markdown.markdown(txt, extensions=["tables", "fenced_code", "sane_lists"])
    os.makedirs(os.path.dirname(os.path.join(ROOT, out)), exist_ok=True)
    open(os.path.join(ROOT, out), "w", encoding="utf-8").write(
        page(title, f'<a class="back" href="../index.html">← back</a><article>{body}</article>'))


def clock_face_page():
    """explain/clock-face/index.html: the hub animation of the map's info panel (code taken from make_map.py)."""
    src = open(os.path.join(ROOT, "code", "make_map.py"), encoding="utf-8").read()
    a = src.index(" const ANIM=(()=>{"); b = src.index(" window.__ANIM=ANIM;")
    js = src[a:b]
    css = CSS + """:root{--soft:#eceff4}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--soft:#262e3d}}:root[data-theme="dark"]{--soft:#262e3d}
canvas{width:100%;height:auto;display:block;border-radius:12px;background:var(--soft)}.stage{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px}
ul{color:var(--ink);font-size:14.5px;line-height:1.55;padding-left:20px}main{max-width:920px}"""
    body = """<a class="back" href="../../index.html">← back</a>
<h1>Clock-face hub</h1>
<div class="stage"><canvas id="anim" width="720" height="330"></canvas></div>"""
    script = """<script>
const SK=['bigrail','localrail','bus'],COL={bigrail:'#d32f2f',localrail:'#2e7d32',bus:'#1e6fd9'};
""" + js + """ANIM.start();
</script>"""
    out = os.path.join(ROOT, "explain", "clock-face", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clock-Face Scheduling</title><meta name="description" content="Animation of a clock-face timetable hub (Taktknoten)."><style>{css}</style></head>
<body><main>{body}</main>{script}</body></html>""")


REDIRECTS = {   # old published path -> new path (relative to the site root); kept so old links keep working
    "explain/clock-phase/index.html": "explain/clock-face/",
    **{f"output/{r}/{r}_network_map.html": f"maps/{r}/" for r in REGIONS},
}


def redirect_pages():
    """Small pages at old addresses that forward to the new ones (keeping the #... part of the link)."""
    for old, new in REDIRECTS.items():
        depth = old.count("/")
        target = "../" * depth + new
        out = os.path.join(ROOT, old)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w", encoding="utf-8").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Moved</title><meta http-equiv="refresh" content="0; url={target}"><link rel="canonical" href="{target}">
<script>location.replace("{target}" + location.search + location.hash);</script></head>
<body><a href="{target}">Moved here</a></body></html>""")


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
        cards.append(f"""<a class="card" href="{mp}">{im}<div class="b"><h3>{NICE[r]}</h3><div class="c">{COUNTRY[r]}</div>
<div class="s"><div><b>{nn if nn is not None else '–'}</b>nodes</div><div><b>{ns if ns is not None else '–'}</b>symmetric</div></div></div></a>""")
    md_page("sources/network_rules.md", "docs/rules.html", "Network rules")
    md_page("literature/taktfahrplan_review.md", "docs/literature.html", "Literature notes")
    md_page("README.md", "docs/readme.html", "README")
    clock_face_page()
    redirect_pages()
    papers = sorted(os.listdir(os.path.join(ROOT, "literature", "papers")))
    plinks = "".join(f'<a href="literature/papers/{p}"><b>{html.escape(p.rsplit(".", 1)[0].replace("_", " "))}</b></a>' for p in papers)
    body = f"""<h1>Clock-face timetable maps</h1>
<div class="leg"><span><i style="background:#d32f2f"></i>rail</span><span><i style="background:#2e7d32"></i>local rail</span><span><i style="background:#1e6fd9"></i>bus</span></div>
<h2>Regions</h2><div class="grid">{''.join(cards)}</div>
<h2>Explainers</h2><div class="links">
<a href="explain/clock-face/"><b>Clock-face hub</b></a>
<a href="explain/symmetry/"><b>Why symmetry</b></a></div>
<h2>Method</h2><div class="links">
<a href="docs/rules.html"><b>Rules</b></a>
<a href="docs/literature.html"><b>Literature</b></a>
<a href="docs/readme.html"><b>Code</b></a></div>
<h2>Papers</h2><div class="links">{plinks}</div>
<footer>Data: Mobilitätsverbünde Österreich, opentransportdata.swiss, Basque open data, Transitland, OpenStreetMap, OpenFreeMap, Google, WorldPop.</footer>"""
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(
        page("Takt network maps", body, "Interactive public-transport network and symmetry-node maps for five regions"))
    print("index.html, docs/rules.html, docs/literature.html written")


if __name__ == "__main__":
    main()
