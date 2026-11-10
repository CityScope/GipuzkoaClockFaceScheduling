"""Region configuration: Lucerne canton public transport (data-driven: every municipality with service gets its own node)."""
from regions._ch import *      # noqa: F401,F403  (shared systems, route classification, dates)

NAME = "luzern"
TITLE = "Lucerne canton public transport"
BBOX = dict(lat_min=46.65, lat_max=47.40, lon_min=7.75, lon_max=8.60)
MAP_CENTER, MAP_ZOOM = [8.15, 47.05], 9.6
BOUNDARY_FILE = "sources/luzern_boundary.geojson"
MUNI_FILE = "sources/luzern_municipalities.geojson"
PRIORITY = ["Luzern","Zürich","Zug","Olten","Bern","Sursee","Emmen","Kriens","Hochdorf","Wolhusen","Willisau","Escholzmatt"]
