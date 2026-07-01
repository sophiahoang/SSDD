"""
Completeness check: for every fire folder under TILES_ROOT, compare the NAIP
tiles you've downloaded against the full set Earth Engine says the fire needs,
and list what's missing. Run this BEFORE clip_fire_raster.py so you catch a
short download before wasting a clip.

For each <FIRE>_<year>[_pre|_post] folder it:
  1. reads the tiles present and the NAIP year they belong to (from filenames),
  2. matches the fire perimeter,
  3. queries USDA/NAIP/DOQQ for that perimeter + year,
  4. prints have / need / missing (and any extra tiles that don't belong).

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" check_tiles.py
"""
import glob
import os
import csv
from collections import Counter

import geopandas as gpd
import ee

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
EE_PROJECT  = "ssdd-499921"
TILES_ROOT  = r"C:\Users\shoang12\Downloads\NAIP_TILES"
TILE_EXTS   = ("*.tif", "*.tiff", "*.jp2")
PERIM_PATH  = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_LAYER = None
NAME_FIELD  = "FIRE_NAME"
DATE_FIELD  = "ALARM_DATE"
REPORT_CSV  = r"C:\Users\shoang12\Downloads\NAIP_tile_check.csv"
# ---------------------------------------------------------------------------

ee.Initialize(project=EE_PROJECT)
NAIP = ee.ImageCollection("USDA/NAIP/DOQQ")


def fire_key(name, year):
    safe = "".join(c if c.isalnum() else "_" for c in str(name)).strip("_")
    return f"{safe}_{year}"


def load_perimeters():
    gdf = gpd.read_file(PERIM_PATH, layer=PERIM_LAYER)
    gdf["__key"] = [fire_key(n, str(d)[:4])
                    for n, d in zip(gdf[NAME_FIELD], gdf[DATE_FIELD])]
    return gdf


def find_tiles(folder):
    tiles = []
    for pat in TILE_EXTS:
        tiles += glob.glob(os.path.join(folder, pat))
    return tiles


def tile_id(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def tile_year(path):
    # m_3411733_se_11_060_20200621  ->  '2020'
    return tile_id(path).split("_")[-1][:4]


def needed_tiles(perim_subset, year):
    geom = ee.Geometry(perim_subset.to_crs("EPSG:4326").union_all().__geo_interface__)
    ids = (NAIP.filterBounds(geom)
           .filter(ee.Filter.calendarRange(year, year, "year"))
           .aggregate_array("system:index").getInfo())
    return set(i.lower() for i in ids)


def main():
    perims = load_perimeters()
    fire_dirs = [d for d in sorted(glob.glob(os.path.join(TILES_ROOT, "*")))
                 if os.path.isdir(d)]
    print(f"Checking {len(fire_dirs)} folder(s) in {TILES_ROOT}\n")

    rows, complete, incomplete = [], 0, 0
    for d in fire_dirs:
        key = os.path.basename(d)
        tiles = find_tiles(d)
        if not tiles:
            print(f"[{key}] no tiles in folder")
            continue

        have = set(tile_id(t) for t in tiles)
        years = Counter(tile_year(t) for t in tiles)

        cand = [k for k in perims["__key"].unique()
                if key == k or key.startswith(k + "_")]
        subset = perims[perims["__key"] == max(cand, key=len)] if cand \
            else perims.iloc[0:0]
        if subset.empty:
            print(f"[{key}] no matching perimeter -- check the folder name")
            continue

        need = set()
        for yr in years:
            need |= needed_tiles(subset, int(yr))

        missing = sorted(need - have)
        extra = sorted(have - need)
        yr_str = "+".join(sorted(years))
        status = "COMPLETE" if not missing else f"MISSING {len(missing)}"
        if missing:
            incomplete += 1
        else:
            complete += 1

        print(f"[{key}]  year {yr_str}  have {len(have)} / need {len(need)}  -> {status}")
        for t in missing:
            print(f"     missing: {t}")
        for t in extra:
            print(f"     extra (not part of this fire): {t}")

        rows.append({
            "folder": key, "year": yr_str,
            "have": len(have), "need": len(need),
            "missing_count": len(missing), "extra_count": len(extra),
            "status": status,
            "missing_tiles": "; ".join(missing),
            "extra_tiles": "; ".join(extra),
        })

    if rows:
        with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nReport written: {REPORT_CSV}")
    print(f"Complete: {complete}   Incomplete: {incomplete}")


if __name__ == "__main__":
    main()
