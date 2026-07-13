"""
Join CAL FIRE DINS damage onto the extracted building footprints, per fire.

For each fire that has both a footprint layer (from extract_footprints.py) and a
per-fire DINS file (from split_dins.py), assigns each DINS point to the nearest
footprint within TOLERANCE metres and writes a GeoPackage of buildings carrying
DAMAGE / STRUCTURETYPE (matching the eaton_buildings.gpkg example). Buildings
with no nearby DINS point get null damage (not inspected / undamaged).

Run with the fire-naip env (geopandas), NOT the arcpy base env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" join_dins_to_footprints.py
"""
import glob
import os

import geopandas as gpd
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
FOOT_DIR    = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints"
FOOT_SUFFIX = "_pre_footprints.shp"
DINS_DIR    = r"C:\Users\shoang12\Downloads\dins_by_fire"
OUT_DIR     = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\buildings"
OUT_LAYER   = "buildings_raw"      # layer name (matches the example gpkg)
TOLERANCE   = 15.0                 # max metres from a DINS point to a footprint

# Most-severe damage wins when several DINS points map to one building.
SEVERITY = {"Destroyed (>50%)": 4, "Major (25-50%)": 3, "Minor (10-25%)": 2,
            "Affected (>0-10%)": 1, "No Damage": 0, "Inaccessible": 0}

# DINS field (shapefile-truncated) -> output field name
DINS_FIELDS = {"DAMAGE": "DAMAGE", "STRUCTURET": "STRUCTURETYPE", "GLOBALID": "GLOBALID"}
# ---------------------------------------------------------------------------


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    foots = sorted(glob.glob(os.path.join(FOOT_DIR, "*" + FOOT_SUFFIX)))
    if not foots:
        raise SystemExit(f"No *{FOOT_SUFFIX} found in {FOOT_DIR}")
    print(f"Found {len(foots)} footprint layer(s)\n")

    for fp in foots:
        key = os.path.basename(fp)[:-len(FOOT_SUFFIX)]
        dins_path = os.path.join(DINS_DIR, key + ".geojson")
        if not os.path.exists(dins_path):
            print(f"[{key}] no DINS file -- skipping")
            continue

        foot = gpd.read_file(fp).reset_index(drop=True)
        foot["__fid"] = foot.index
        dins = gpd.read_file(dins_path).to_crs(foot.crs)   # UTM metres

        # Each DINS point -> nearest footprint within TOLERANCE.
        dj = gpd.sjoin_nearest(dins, foot[["__fid", "geometry"]],
                               max_distance=TOLERANCE, how="inner")
        dj["__sev"] = dj["DAMAGE"].map(SEVERITY).fillna(-1) if "DAMAGE" in dj else -1
        dj = dj.sort_values("__sev", ascending=False).drop_duplicates("__fid")

        attrs = pd.DataFrame({dst: dj.set_index("__fid")[src]
                              for src, dst in DINS_FIELDS.items() if src in dj})
        out = foot.join(attrs, on="__fid").drop(columns="__fid")

        matched = int(out["DAMAGE"].notna().sum()) if "DAMAGE" in out else 0
        out_path = os.path.join(OUT_DIR, f"{key}_buildings.gpkg")
        out.to_file(out_path, layer=OUT_LAYER, driver="GPKG")
        print(f"[{key}] {len(out)} buildings, {matched} with DINS damage "
              f"-> {os.path.basename(out_path)}")

    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
