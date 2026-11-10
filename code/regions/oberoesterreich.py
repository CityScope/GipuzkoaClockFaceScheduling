"""Region configuration: Upper Austria (Linz–Wels–Steyr) public transport (data-driven: every municipality with service gets its own node)."""
from regions._at import *      # noqa: F401,F403  (shared systems, route classification, dates)

NAME = "oberoesterreich"
TITLE = "Upper Austria (Linz–Wels–Steyr) public transport"
BBOX = dict(lat_min=47.50, lat_max=48.65, lon_min=13.30, lon_max=15.10)
MAP_CENTER, MAP_ZOOM = [14.2, 48.15], 9.3
BOUNDARY_FILE = "sources/oberoesterreich_boundary.geojson"
MUNI_FILE = "sources/oberoesterreich_municipalities.geojson"
FEEDS = {"rail": ("Rail Austria", "auto:rail"), "ooevv": ("OÖVV", "auto"), "linzag": ("Linz AG", "auto")}
PRIORITY = ["Wien","Salzburg","Linz","Wels","Steyr","Attnang-Puchheim","Amstetten","St. Valentin","Enns","Traun","Leonding"]
