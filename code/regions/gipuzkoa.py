"""Region configuration: Gipuzkoa (Basque Country)."""
import datetime as dt

NAME = "gipuzkoa"
TITLE = "Gipuzkoa public transport"
GTFS_ROOT = "sources/gtfs"
DATE_RANGE = (dt.date(2026, 2, 9), dt.date(2026, 5, 10))   # feeds are valid early 2026
BBOX = dict(lat_min=42.78, lat_max=43.52, lon_min=-3.00, lon_max=-1.40)   # Gipuzkoa + Bilbao, Vitoria, Pamplona, Hendaye
MAP_CENTER, MAP_ZOOM = [-2.15, 43.2], 9.2
BOUNDARY_FILE = "sources/gipuzkoa_boundary.geojson"
MUNI_FILE = "sources/gipuzkoa_municipalities.geojson"     # data-driven: every municipality with service is a node (see make_region_geo.py)
MIN_EDGE_MIN = 2
MIN_TRIPS_DAY = 1
PASSTHROUGH = True

# system key -> display name, colour, dashed?, vehicle emoji, max straight-line speed (km/h),
# max distance of a stop from the node's station to count as a visit (m), rail-like station anchoring?
SYSTEMS = {
    "renfe":     dict(icon="train", name="Renfe",     color="#d62728", dash=False, emoji="\U0001F686", vmax=100, anchor_m=1000, rail=True),
    "euskotren": dict(icon="tram", name="Euskotren", color="#2ca02c", dash=False, emoji="\U0001F68B", vmax=80,  anchor_m=1000, rail=True),
    "bus":       dict(icon="bus", name="Bus",       color="#1f77b4", dash=True,  emoji="\U0001F68C", vmax=80,  anchor_m=1500, rail=False),
}
AUTO_SYSTEM = None   # feeds below name their system explicitly

# feed dir -> (label, system)
FEEDS = {
    "mdb2715_raw_data_f_euskotren": ("Euskotren", "euskotren"),
    "mdb2653_commuter_t_renfe_comm": ("Renfe Cercanias", "renfe"),
    "mdb2620_highspeed_renfe": ("Renfe MD/Alvia", "renfe"),
    "mdb2825_raw_data_f_alsa_buses": ("ALSA", "bus"),   # state concessions = public system
    "mdb1135__bizkaibus": ("Bizkaibus", "bus"),
    "mdb2824_raw_data_f_alavabus": ("Alavabus", "bus"),
    # Public/subsidized operators only. Commercial BlaBlaCar (tdg52605) is OFF; urban city-bus feeds
    # (Dbus, Irunbus, Onati, Tolosa) are excluded on purpose (inter-urban focus).
    **{f"mdb{n}_raw_data_f_lurraldebu": ("Lurraldebus", "bus") for n in
       (2725, 2726, 2728, 2731, 2732, 2733, 2734, 2735, 2736, 2756, 2757, 2759, 2760, 2776)},
}

BUS_STATION_RE = r"autobus geltok|estaci[oó]n de autob|bus station|autobus-geltok|bus geltok|estaci[oó]n autob"

DISPLAY = {"Soraluze-Placencia de las Armas": "Soraluze", "Donostia / San Sebastián": "Donostia", "Arrasate / Mondragón": "Arrasate",
           "Vitoria-Gasteiz": "Vitoria-Gasteiz"}
