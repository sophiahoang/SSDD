"""
Split oversized fires into manageable portions for NAIP download + clipping.

Some fires are too large to upload as one AOI to EarthExplorer / to clip in one
mosaic (August Complex ~1.2M ac, Dixie ~1.2M ac, the lightning complexes...).
For each fire in FIRES this writes, into OUT_DIR:

  * per-portion AOI zips  <prefix>_<portion>.zip  -- upload each to EarthExplorer
    (a low-vertex convex hull covering that portion of the fire), and
  * a cutline file        <prefix>_quadrants.gpkg -- the perimeter split into the
    same portions, used by clip_split_fire.py to clip each portion separately.

Portions are cut to be roughly EQUAL AREA (a binary search finds the cut lines):
fires over SPLIT4_ACRES get a balanced 2x2 (SW/NW/SE/NE); smaller ones get a
2-way cut along their longer axis (W/E or S/N). The `portion` field records the
label. Download AOIs are the convex hull of each portion (slightly oversized so
you never miss a tile); the cutlines are the tight perimeter (so final clips
have no wasted coverage and tile back together seamlessly).

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" split_large_fire_aois.py
"""
import os
import shutil
import zipfile

import geopandas as gpd
from shapely.geometry import box

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PERIM_PATH = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME = "FIRE_NAME"
PERIM_DATE = "ALARM_DATE"
OUT_DIR    = r"C:\Users\shoang12\Downloads\CA_fire_AOIs"
SPLIT4_ACRES = 600000        # fires bigger than this get a 2x2 (4-way) split, else 2-way
ACRE = 4046.86

# (FIRE_NAME key, year) of the fires to split -- keys are the safe() form
FIRES = [
    ("AUGUST_COMPLEX", "2020"),
    ("DIXIE", "2021"),
    ("SCU_LIGHTNING_COMPLEX", "2020"),
    ("NORTH_COMPLEX", "2020"),
    ("CZU_LIGHTNING_COMPLEX", "2020"),
    ("CREEK", "2020"),                 # big Fresno-area Creek fire (the 2017 one is small)
]
# ---------------------------------------------------------------------------


def safe(s):
    return "".join(c if str(c).isalnum() else "_" for c in str(s).upper()).strip("_")


def bisect(poly, rect_fn, lo, hi, target):
    """Find the cut coordinate where poly ∩ rect_fn(coord) has `target` area."""
    for _ in range(30):
        mid = (lo + hi) / 2
        if poly.intersection(rect_fn(mid)).area < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def split_cells(poly, n):
    """Return [(label, cell_box)] cutting poly into n roughly equal-area cells."""
    minx, miny, maxx, maxy = poly.bounds
    total = poly.area
    if n == 2:
        if (maxx - minx) >= (maxy - miny):                       # cut the longer axis
            cx = bisect(poly, lambda m: box(minx, miny, m, maxy), minx, maxx, total / 2)
            return [("W", box(minx, miny, cx, maxy)), ("E", box(cx, miny, maxx, maxy))]
        cy = bisect(poly, lambda m: box(minx, miny, maxx, m), miny, maxy, total / 2)
        return [("S", box(minx, miny, maxx, cy)), ("N", box(minx, cy, maxx, maxy))]
    cx = bisect(poly, lambda m: box(minx, miny, m, maxy), minx, maxx, total / 2)
    west, east = box(minx, miny, cx, maxy), box(cx, miny, maxx, maxy)
    cyw = bisect(poly, lambda m: box(minx, miny, cx, m), miny, maxy, poly.intersection(west).area / 2)
    cye = bisect(poly, lambda m: box(cx, miny, maxx, m), miny, maxy, poly.intersection(east).area / 2)
    return [("SW", box(minx, miny, cx, cyw)), ("NW", box(minx, cyw, cx, maxy)),
            ("SE", box(cx, miny, maxx, cye)), ("NE", box(cx, cye, maxx, maxy))]


def write_aoi_zip(gdf_wgs84, base, tmp):
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    gdf_wgs84.to_file(os.path.join(tmp, base + ".shp"))
    with zipfile.ZipFile(os.path.join(OUT_DIR, base + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            f = os.path.join(tmp, base + ext)
            if os.path.exists(f):
                z.write(f, base + ext)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    g = gpd.read_file(PERIM_PATH)
    g["__key"] = g[PERIM_NAME].apply(safe)
    tmp = os.path.join(OUT_DIR, "_tmp")

    for fire, year in FIRES:
        sub = g[(g["__key"] == fire) & (g[PERIM_DATE].astype(str).str[:4] == year)].to_crs("EPSG:3310")
        if sub.empty:
            print(f"!! no perimeter for {fire}_{year}")
            continue
        poly = sub.geometry.union_all()
        acres = poly.area / ACRE
        n = 4 if acres > SPLIT4_ACRES else 2
        print(f"\n{fire}_{year}: ~{acres:,.0f} acres -> {n} portions", flush=True)

        cut_rows = []
        for label, rect in split_cells(poly, n):
            piece = poly.intersection(rect)
            aoi = piece.convex_hull.intersection(rect)          # download AOI (low-vertex, oversized)
            base = f"{fire}_{year}_{label}"
            write_aoi_zip(gpd.GeoDataFrame({"portion": [label]}, geometry=[aoi],
                                           crs="EPSG:3310").to_crs("EPSG:4326"), base, tmp)
            cut_rows.append({PERIM_NAME: f"{fire.replace('_', ' ')} {label}", "portion": label,
                             PERIM_DATE: f"{year}-01-01", "geometry": piece})   # tight clip boundary
            print(f"   {label}: ~{piece.area / ACRE:,.0f} acres -> {base}.zip", flush=True)

        gpd.GeoDataFrame(cut_rows, crs="EPSG:3310").to_crs("EPSG:4326").to_file(
            os.path.join(OUT_DIR, f"{fire}_{year}_quadrants.gpkg"), layer="quadrants", driver="GPKG")

    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    print("\ndone")


if __name__ == "__main__":
    main()
