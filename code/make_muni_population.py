"""Population of every municipality of a region (WorldPop 100 m raster summed inside each OSM municipality polygon)
-> sources/population/<region>_municipalities_pop.json. Used as the importance of a town (e.g. which of two
'twin' stations stays a node). Run: python3 code/make_muni_population.py <region>"""
import json, sys
from pathlib import Path
import numpy as np
import rasterio, rasterio.mask
import geopandas as gpd

SRC = Path(__file__).parent.parent / "sources"
AUT, CHE = "aut_pop_2025_CN_100m_R2025A_v1.tif", "che_pop_2025_CN_100m_R2025A_v1.tif"
RASTER = {"gipuzkoa": "gipuzkoa_worldpop_2025_100m.tif", "vorarlberg": AUT, "oberoesterreich": AUT, "aargau": CHE, "luzern": CHE}
region = sys.argv[1]
mun = gpd.read_file(SRC / f"{region}_municipalities.geojson").to_crs(4326)
out = {}
with rasterio.open(SRC / "population" / RASTER[region]) as ds:
    mun = mun.to_crs(ds.crs)
    for name, geom in zip(mun["name"], mun.geometry):
        try:
            arr, _ = rasterio.mask.mask(ds, [geom], crop=True, nodata=ds.nodata or -99999, filled=True)
            a = arr[0].astype("float64"); a = a[(a > 0) & np.isfinite(a)]
            out[name] = out.get(name, 0) + int(round(a.sum()))
        except ValueError:                       # polygon outside the raster
            out.setdefault(name, 0)
json.dump(out, open(SRC / "population" / f"{region}_municipalities_pop.json", "w"), indent=0, ensure_ascii=False)
print(region, len(out), "municipalities", sorted(out.items(), key=lambda kv: -kv[1])[:5])
