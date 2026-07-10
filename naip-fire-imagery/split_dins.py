"""
Split the CAL FIRE DINS point layer into one GeoJSON per fire.

Two methods (set METHOD):
  "spatial" (default) -- assign each DINS point to a fire by LOCATION: clip the
      points to each study-fire perimeter. This resolves naming differences
      automatically (e.g. DINS "CZU Lightning Cmplx" vs perimeter
      "CZU LIGHTNING COMPLEX") and correctly splits sub-fires that DINS rolls
      up into a parent complex (Hennessey/Walbridge inside "LNU", Castle inside
      "SQF") -- geometry doesn't care what the incident is named.
  "name" -- group by the DINS incident name field (raw per-incident split).

Output files are named <FIRE>_<year>.geojson (same key convention as the NAIP
tiles / AOIs / footprints) in EPSG:4326.

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" split_dins.py
"""
import os

import geopandas as gpd
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DINS_SRC   = r"C:\Users\shoang12\Downloads\DINS_PointLayer\DINS_PointLayer.shp"
DINS_NAME  = "INCIDENTNA"   # DINS incident name (used only by METHOD="name")
DINS_DATE  = "INCIDENTST"   # DINS incident start date -> year

METHOD     = "spatial"      # "spatial" (clip to perimeters) or "name"

# For METHOD="spatial": the study-fire perimeters to clip against.
PERIM_PATH  = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME  = "FIRE_NAME"
PERIM_DATE  = "ALARM_DATE"
MATCH_YEAR  = True          # also require DINS year == fire year (separates
                            # different fires that overlap in space)

OUT_DIR    = r"C:\Users\shoang12\Downloads\dins_by_fire"
OUT_CRS    = "EPSG:4326"
# ---------------------------------------------------------------------------


def fire_key(name, year):
    safe = "".join(c if c.isalnum() else "_" for c in str(name).upper()).strip("_")
    return f"{safe}_{year}"


def year_of(series):
    return pd.to_datetime(series, errors="coerce").dt.year


def split_by_name(dins):
    yrs = year_of(dins[DINS_DATE])
    keys = [fire_key(n, int(y)) if pd.notna(y) else fire_key(n, "unknown")
            for n, y in zip(dins[DINS_NAME], yrs)]
    return dins.assign(__key=keys)


def split_by_perimeter(dins):
    perim = gpd.read_file(PERIM_PATH)
    perim["__key"] = [fire_key(n, str(d)[:4])
                      for n, d in zip(perim[PERIM_NAME], perim[PERIM_DATE])]
    perim["__pyear"] = [int(str(d)[:4]) for d in perim[PERIM_DATE]]

    dins = dins.to_crs(perim.crs)
    dins["__dyear"] = year_of(dins[DINS_DATE])

    joined = gpd.sjoin(dins, perim[["__key", "__pyear", "geometry"]],
                       predicate="within", how="inner")
    if MATCH_YEAR:
        joined = joined[joined["__dyear"] == joined["__pyear"]]
    # a point could fall in two same-year overlapping perimeters; keep one
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined


def main():
    dins = gpd.read_file(DINS_SRC)
    orig_cols = [c for c in dins.columns]        # keep only real DINS fields

    if METHOD == "spatial":
        tagged = split_by_perimeter(dins)
    elif METHOD == "name":
        tagged = split_by_name(dins)
    else:
        raise SystemExit(f"Unknown METHOD: {METHOD!r}")

    os.makedirs(OUT_DIR, exist_ok=True)
    n = 0
    for key, sub in tagged.groupby("__key"):
        out_gdf = sub[orig_cols].to_crs(OUT_CRS)
        out_gdf.to_file(os.path.join(OUT_DIR, f"{key}.geojson"), driver="GeoJSON")
        print(f"{key:32s} {len(out_gdf):6d} points")
        n += 1

    print(f"\nMETHOD={METHOD}: wrote {n} per-fire GeoJSON files to {OUT_DIR}")


if __name__ == "__main__":
    main()
