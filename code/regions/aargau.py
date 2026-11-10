"""Region configuration: Aargau public transport (data-driven: every municipality with service gets its own node)."""
from regions._ch import *      # noqa: F401,F403  (shared systems, route classification, dates)

NAME = "aargau"
TITLE = "Aargau public transport"
BBOX = dict(lat_min=46.95, lat_max=47.80, lon_min=7.55, lon_max=8.70)
MAP_CENTER, MAP_ZOOM = [8.07, 47.38], 9.6
BOUNDARY_FILE = "sources/aargau_boundary.geojson"
MUNI_FILE = "sources/aargau_municipalities.geojson"
PRIORITY = ["Zürich","Basel","Olten","Luzern","Bern","Aarau","Baden","Brugg","Lenzburg","Zofingen","Rheinfelden","Wohlen","Rotkreuz","Zug"]
