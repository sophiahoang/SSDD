"""
Split the CAL FIRE DINS point layer into one GeoJSON per study fire.

METHOD (default "hybrid"):
  "hybrid"  -- gate points by DINS incident NAME (with an alias map for fires
      that DINS records under a different / parent-complex name), THEN spatially
      clip to the fire perimeter. This:
        * matches names that differ (CZU "Cmplx" vs "COMPLEX", Redwood(Valley),
          Sulpher/Sulphur),
        * splits a parent complex among its sub-fires by geometry
          (Hennessey/Walbridge from "LNU", Castle from "SQF"),
        * and does NOT bleed a neighbouring same-year fire's points into a fire
          that has no DINS of its own (e.g. Beckwourth must not become Sugar).
  "spatial" -- clip by geometry only (can cross-contaminate overlapping fires).
  "name"    -- group by incident name only (misses complex roll-ups).

Output: <FIRE>_<year>.geojson (pipeline key convention), EPSG:4326.

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
DINS_NAME  = "INCIDENTNA"
DINS_DATE  = "INCIDENTST"

METHOD     = "hybrid"       # "hybrid" (recommended) | "spatial" | "name"

PERIM_PATH = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME = "FIRE_NAME"
PERIM_DATE = "ALARM_DATE"

# Study fire (safe name) -> DINS incident name(s) it legitimately draws from,
# for cases where DINS names the incident differently or rolls it into a complex.
ALIASES = {
    "CZU_LIGHTNING_COMPLEX": ["CZU Lightning Cmplx"],
    "SCU_LIGHTNING_COMPLEX": ["SCU Lightning Cmplx"],
    "REDWOOD_VALLEY":        ["Redwood"],
    "SULPHER":               ["Sulphur"],
    "HENNESSEY":             ["LNU Lightning Cmplx"],
    "WALBRIDGE":             ["LNU Lightning Cmplx"],
    "CASTLE":                ["SQF Complex"],
}

OUT_DIR    = r"C:\Users\shoang12\Downloads\dins_by_fire"
OUT_CRS    = "EPSG:4326"
# ---------------------------------------------------------------------------


def safe_name(s):
    return "".join(c if c.isalnum() else "_" for c in str(s).upper()).strip("_")


def norm(s):
    return "".join(c for c in str(s).upper() if c.isalnum())


def fire_key(name, year):
    return f"{safe_name(name)}_{year}"


def year_of(series):
    return pd.to_datetime(series, errors="coerce").dt.year


def load_perims():
    perim = gpd.read_file(PERIM_PATH)
    perim["__key"] = [fire_key(n, str(d)[:4]) for n, d in zip(perim[PERIM_NAME], perim[PERIM_DATE])]
    perim["__ay"] = [int(str(d)[:4]) for d in perim[PERIM_DATE]]
    perim["__safe"] = [safe_name(n) for n in perim[PERIM_NAME]]
    return perim


def split_hybrid(dins):
    perim = load_perims()
    # allowed (fire key, normalized incident name) pairs
    allowed = set()
    for _, r in perim.iterrows():
        names = [r[PERIM_NAME]] + ALIASES.get(r["__safe"], [])
        for nm in names:
            allowed.add((r["__key"], norm(nm)))

    dins = dins.to_crs(perim.crs)
    dins["__ny"] = year_of(dins[DINS_DATE])
    dins["__nn"] = dins[DINS_NAME].map(norm)

    j = gpd.sjoin(dins, perim[["__key", "__ay", "geometry"]],
                  predicate="within", how="inner")
    j = j[j["__ny"] == j["__ay"]]
    keep = [(k, n) in allowed for k, n in zip(j["__key"], j["__nn"])]
    j = j[keep]
    j = j[~j.index.duplicated(keep="first")]
    return j


def split_spatial(dins):
    perim = load_perims()
    dins = dins.to_crs(perim.crs)
    dins["__ny"] = year_of(dins[DINS_DATE])
    j = gpd.sjoin(dins, perim[["__key", "__ay", "geometry"]],
                  predicate="within", how="inner")
    j = j[j["__ny"] == j["__ay"]]
    return j[~j.index.duplicated(keep="first")]


def split_name(dins):
    yrs = year_of(dins[DINS_DATE])
    keys = [fire_key(n, int(y)) if pd.notna(y) else fire_key(n, "unknown")
            for n, y in zip(dins[DINS_NAME], yrs)]
    return dins.assign(__key=keys)


def main():
    dins = gpd.read_file(DINS_SRC)
    orig_cols = list(dins.columns)

    tagged = {"hybrid": split_hybrid, "spatial": split_spatial,
              "name": split_name}[METHOD](dins)

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
