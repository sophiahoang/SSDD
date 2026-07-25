"""
Fetch Microsoft Global ML Building Footprints per fire and clip to the
perimeter -- an alternative footprint source to the deep-learning extractor.

For each fire it computes the level-9 quadkeys covering the perimeter bbox,
downloads those tiles from Microsoft's open dataset (cached locally), keeps the
footprints intersecting the perimeter, reprojects to the fire's NAD83/UTM zone,
and writes <FIRE>_<year>_pre_footprints.shp -- the same layout the DINS join
expects, so join_dins_to_footprints.py works unchanged.

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" fetch_ms_buildings.py
"""
import glob
import gzip
import json
import math
import os
import urllib.request
from collections import defaultdict

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PERIM_PATH = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME = "FIRE_NAME"
PERIM_DATE = "ALARM_DATE"
OUT_DIR    = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints"
CACHE_DIR  = r"C:\Users\shoang12\Downloads\ms_buildings_cache"
MANIFEST_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
ZOOM       = 9
ONLY       = None               # optional: limit to a list of keys; None = all fires
FOOT_SUFFIX = "_pre_footprints.shp"
# ---------------------------------------------------------------------------


def safe(s):
    return "".join(c if c.isalnum() else "_" for c in str(s).upper()).strip("_")


def fire_key(n, d):
    return f"{safe(n)}_{str(d)[:4]}"


def nad83_utm(lon):
    return 26900 + int((lon + 180) // 6) + 1


def latlon_to_tile(lat, lon, z):
    s = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    n = 2 ** z
    return min(int(x * n), n - 1), min(int(y * n), n - 1)


def to_quadkey(tx, ty, z):
    qk = []
    for i in range(z, 0, -1):
        d, m = 0, 1 << (i - 1)
        if tx & m:
            d += 1
        if ty & m:
            d += 2
        qk.append(str(d))
    return "".join(qk)


def bbox_quadkeys(minx, miny, maxx, maxy, z):
    x0, y0 = latlon_to_tile(maxy, minx, z)
    x1, y1 = latlon_to_tile(miny, maxx, z)
    qks = set()
    for tx in range(min(x0, x1), max(x0, x1) + 1):
        for ty in range(min(y0, y1), max(y0, y1) + 1):
            qks.add(to_quadkey(tx, ty, z))
    return qks


def load_manifest():
    os.makedirs(CACHE_DIR, exist_ok=True)
    local = os.path.join(CACHE_DIR, "dataset-links.csv")
    if not os.path.exists(local):
        print("downloading manifest...")
        urllib.request.urlretrieve(MANIFEST_URL, local)
    m = pd.read_csv(local)
    us = m[m["Location"].astype(str).str.contains("UnitedStates", case=False, na=False)]
    qk_url = {}
    for _, r in us.iterrows():
        qk_url[int(r["QuadKey"])] = r["Url"]      # keyed by int (manifest drops leading zeros)
    return qk_url


def tile_gdf(qk, url):
    local = os.path.join(CACHE_DIR, f"{qk}.csv.gz")
    if not os.path.exists(local):
        urllib.request.urlretrieve(url, local)
    with gzip.open(local, "rt", encoding="utf-8") as fh:
        feats = [json.loads(line) for line in fh if line.strip()]
    geoms = [shape(f["geometry"]) for f in feats]
    props = [f.get("properties", {}) or {} for f in feats]
    return gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    qk_url = load_manifest()

    perim = gpd.read_file(PERIM_PATH).to_crs("EPSG:4326")
    perim["__key"] = [fire_key(n, d) for n, d in zip(perim[PERIM_NAME], perim[PERIM_DATE])]

    for _, fire in perim.iterrows():
        key = fire["__key"]
        if ONLY and key not in ONLY:
            continue
        minx, miny, maxx, maxy = fire.geometry.bounds
        qks = bbox_quadkeys(minx, miny, maxx, maxy, ZOOM)
        urls = {q: qk_url[int(q)] for q in qks if int(q) in qk_url}
        if not urls:
            print(f"[{key}] no MS tiles for quadkeys {sorted(qks)}")
            continue

        parts = []
        for q, u in urls.items():
            try:
                parts.append(tile_gdf(q, u))
            except Exception as e:
                print(f"  tile {q} failed: {e}")
        if not parts:
            print(f"[{key}] no tiles downloaded")
            continue

        allb = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
        keep = allb[allb.intersects(fire.geometry)].copy()      # whole footprints
        keep = keep.to_crs(f"EPSG:{nad83_utm(fire.geometry.centroid.x)}")
        out = os.path.join(OUT_DIR, key + FOOT_SUFFIX)
        keep.to_file(out)
        print(f"[{key}] {len(keep)} MS buildings -> {os.path.basename(out)}")


if __name__ == "__main__":
    main()
