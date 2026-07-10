"""
Split the combined CAL FIRE DINS point layer into one GeoJSON per fire.

Output files are named <FIRE>_<year>.geojson using the same key convention as
the NAIP tiles / AOIs / footprints (uppercase fire name + incident-start year),
so DINS lines up 1:1 with the rest of the pipeline. Reprojected to EPSG:4326
(the GeoJSON standard).

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
NAME_FIELD = "INCIDENTNA"   # incident name (truncated shapefile field)
DATE_FIELD = "INCIDENTST"   # incident start date -> year for the key
OUT_DIR    = r"C:\Users\shoang12\Downloads\dins_by_fire"
OUT_CRS    = "EPSG:4326"
# ---------------------------------------------------------------------------


def fire_key(name, year):
    safe = "".join(c if c.isalnum() else "_" for c in str(name).upper()).strip("_")
    return f"{safe}_{year}"


def main():
    g = gpd.read_file(DINS_SRC)
    g = g.to_crs(OUT_CRS)

    years = pd.to_datetime(g[DATE_FIELD], errors="coerce").dt.year
    g = g.assign(__year=years)
    g["__key"] = [fire_key(n, int(y)) if pd.notna(y) else fire_key(n, "unknown")
                  for n, y in zip(g[NAME_FIELD], g["__year"])]

    os.makedirs(OUT_DIR, exist_ok=True)
    n_fires = 0
    for key, sub in g.groupby("__key"):
        sub = sub.drop(columns=["__key", "__year"])
        out = os.path.join(OUT_DIR, f"{key}.geojson")
        sub.to_file(out, driver="GeoJSON")
        print(f"{key:32s} {len(sub):6d} points")
        n_fires += 1

    print(f"\nWrote {n_fires} per-fire GeoJSON files to {OUT_DIR}")


if __name__ == "__main__":
    main()
