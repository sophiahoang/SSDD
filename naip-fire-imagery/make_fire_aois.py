"""
Split AllFires_1kmBuffer into one zipped shapefile per CA fire (those with
post-fire NAIP), in EPSG:4326, ready to upload to USGS EarthExplorer as an AOI.

Each fire's AOI is its convex hull -- a simple polygon that fully covers the
fire so EarthExplorer returns every overlapping NAIP tile, while staying low
on vertices so the upload is always accepted.
"""
import os
import shutil
import zipfile

import geopandas as gpd

SHP = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
OUT = r"C:\Users\shoang12\Downloads\CA_fire_AOIs"

# CA fires that have NO post-fire NAIP yet -- skip these (nothing to download).
NO_POST = {"MOUNTAIN", "MILL", "EATON", "PALISADES",
           "MCKINNEY", "AIRPORT", "PARK", "BOREL"}

g = gpd.read_file(SHP)
g = g[g["STATE"] == "CA"].copy()
g = g[~g["FIRE_NAME"].isin(NO_POST)].copy()
g["geometry"] = g.geometry.convex_hull
g = g.to_crs("EPSG:4326")          # EarthExplorer expects geographic WGS84

os.makedirs(OUT, exist_ok=True)
tmp = os.path.join(OUT, "_tmp")
seen, count = {}, 0

for idx in g.index:
    name = "".join(c if c.isalnum() else "_"
                   for c in str(g.loc[idx, "FIRE_NAME"])).strip("_")
    yr = str(g.loc[idx, "ALARM_DATE"])[:4]
    base = f"{name}_{yr}"
    seen[base] = seen.get(base, 0) + 1
    if seen[base] > 1:                       # guard against same name+year
        base = f"{base}_{seen[base]}"

    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)

    g.loc[[idx]].to_file(os.path.join(tmp, base + ".shp"))

    with zipfile.ZipFile(os.path.join(OUT, base + ".zip"),
                         "w", zipfile.ZIP_DEFLATED) as z:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            f = os.path.join(tmp, base + ext)
            if os.path.exists(f):
                z.write(f, base + ext)
    count += 1
    print(f"{count:2d}. {base}.zip")

if os.path.exists(tmp):
    shutil.rmtree(tmp)
print(f"\nWrote {count} per-fire AOI zips to {OUT}")
