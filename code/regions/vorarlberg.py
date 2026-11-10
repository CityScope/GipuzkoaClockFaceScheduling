"""Region configuration: Vorarlberg (data-driven: every municipality with service gets its own node)."""
from regions._at import *      # noqa: F401,F403  (shared systems, route classification, dates)

NAME = "vorarlberg"
TITLE = "Vorarlberg public transport"
GTFS_ROOT = "sources/vorarlberg_gtfs"
BBOX = dict(lat_min=46.80, lat_max=47.65, lon_min=9.45, lon_max=10.30)
MAP_CENTER, MAP_ZOOM = [9.85, 47.25], 9.0
BOUNDARY_FILE = "sources/vorarlberg_boundary.geojson"
MUNI_FILE = "sources/vorarlberg_municipalities.geojson"
FEEDS = {"rail": ("Rail Austria", "auto:rail"), "vmobil": ("VMOBIL", "auto")}
PRIORITY = ["Bregenz", "Dornbirn", "Feldkirch", "Bludenz", "Lindau (Bodensee)", "Sankt Margrethen", "Buchs", "Lustenau", "Hohenems"]
