# Takt / timetable network maps

Interactive maps of the regional public-transport network (nodes, links, headways, timed connections and symmetry
nodes / Taktknoten) for five regions: `gipuzkoa`, `vorarlberg`, `aargau`, `luzern`, `oberoesterreich`.

Open `index.html` (or the GitHub Pages site of this repository) and choose a region.

## Folders
- `index.html` — front page: choose a region map or an explainer (GitHub Pages site).
- `maps/<region>/index.html` — the interactive map of each region (self-contained; internet needed only for the base map), one URL per region.
- `explain/clock-face/`, `explain/symmetry/` — animations: how a clock-face hub works; why symmetry is needed and not just coordination.
- `docs/` — HTML versions of the rules, literature notes and this README (built by `code/make_index.py`).
- `output/<region>/` — `overview.png`, CSVs (`nodes`, `edges`, `walk_links`, `symmetry`, `transfers`, `vehicle_km`, `services_audit`; `_saturday` / `_sunday` variants).
- `code/` — analysis and map generation (`towns.py` = generic rules, `regions/<region>.py` = region settings, `vendor/` = MapLibre).
- `sources/` — `network_rules.md` (full rule list), OSM municipality / boundary / polygon GeoJSON, per-municipality population (WorldPop).
- `literature/` — `taktfahrplan_review.md` (grounded notes with page numbers) and `papers/` (Austrian Zielnetz plan, ITF and PESP papers).

## Data not in the repository
GTFS feeds, the parsed-feed cache, WorldPop rasters and `results.pkl` files are too large for git (see `.gitignore`). To rerun the analysis put the feeds in
`sources/gtfs/` (Gipuzkoa), `sources/vorarlberg_gtfs/`, `sources/austria_gtfs/` and `sources/switzerland_gtfs/`
(sources: Basque / Spanish open data and Transitland; Mobilitätsverbünde Österreich OG; opentransportdata.swiss).

## Repository checks
After cloning run `git config core.hooksPath .githooks` to enable the pre-commit size check: files above 10 MB stop the commit
(override with `ALLOW_LARGE_FILES=1 git commit ...`), files above 50 MB are always refused. The same check runs on GitHub
(`.github/workflows/file-size.yml`: error above 50 MB, warning above 10 MB).

## Run
```
pip install -r code/requirements.txt
python3 code/run_all.py                   # every region in parallel: analysis + map, overview, audit
python3 code/run_analysis.py <region>     # one region: analysis + map
python3 code/rebuild_map.py <region>      # map only, from results.pkl
python3 code/make_overview.py <region>    # overview.png / .svg
python3 code/audit_services.py <region>   # which routes are (not) on the map
python3 code/make_region_geo.py <region>  # municipalities / boundary from OpenStreetMap
python3 code/make_index.py                # index.html, docs/, explain/clock-face/
```
GTFS files are read with polars and cached in `sources/cache/`; connection analysis runs on all CPU cores.
Typical times: 20–70 s per region, all five regions about 2 min.

## Rules in short (full list: `sources/network_rules.md`)
- **Services**: rail, local rail and regional buses (≥ 3 municipalities and ≥ 10 km; buses serving 2 municipalities only add links / trips between existing nodes; town buses dropped). Colours: red = national / mainline rail, green = local rail, blue = regional bus.
- **Nodes**: stations where lines branch (≥ 3 directions), line ends, or stations needed so that every line can be drawn; redundant stations and stations on short links (< 10 min) not needed for connections are removed.
- **Headways**: pyGTFSHandler formula, all lines of a direction pooled, per time band (peak 07–09 + 17–19, day 09–17, night).
- **Connections**: a change is timed when the wait is ≤ 6 min (≤ 12 min arriving by bus, walk ≤ 5 min + 2 min penalty) and the timed services (with the direct trips) save more wait than half the headway they lose against taking any service; directions with a headway < 15 min are frequent and need no timing.
- **Symmetry nodes**: a symmetry minute inside every timed change of the group (arrival before it, departure after it); ≥ 2 timed directions to ≥ 3 places, most pairs working both ways (solid) or one way (dotted).
- **Map**: day / band selectors, node popups with a symmetry diagram (minutes before / after the symmetry minute and headways per spoke), connections and timetable, "Coordinated only" filter, video mode.
