"""Population inside a region polygon from a WorldPop 100 m raster -> sources/population/<region>_population.json.
Run: python3 code/make_population.py gipuzkoa|vorarlberg"""
import json
import sys
from pathlib import Path
import numpy as np
import rasterio
import rasterio.mask
import geopandas as gpd

SRC = Path(__file__).parent.parent / "sources"
AUT, CHE = "aut_pop_2025_CN_100m_R2025A_v1.tif", "che_pop_2025_CN_100m_R2025A_v1.tif"
RASTER = {"gipuzkoa": "gipuzkoa_worldpop_2025_100m.tif", "vorarlberg": AUT, "oberoesterreich": AUT,
          "aargau": CHE, "luzern": CHE}
region = sys.argv[1]
poly = gpd.read_file(SRC / f"{region}_polygon.geojson").to_crs(4326)
with rasterio.open(SRC / "population" / RASTER[region]) as ds:
    poly = poly.to_crs(ds.crs)
    arr, _ = rasterio.mask.mask(ds, poly.geometry, crop=True, nodata=ds.nodata or -99999, filled=True)
    a = arr[0].astype("float64"); a = a[(a > 0) & np.isfinite(a)]
pop = int(round(a.sum()))
json.dump(dict(population=pop, year=2025, source="WorldPop R2025A constrained 100 m, summed inside the province polygon"),
          open(SRC / "population" / f"{region}_population.json", "w"), indent=1)
print(region, pop)
