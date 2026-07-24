"""
Score how "ready" each fire's building-footprint data is, so we can start the
downstream analysis on the fires that need the least manual digitizing.

For every per-fire DINS damage file (produced by split_dins.py) it:
  1. takes the DINS points' extent as the area of interest,
  2. pulls the latest Overture building footprints over that bbox,
  3. counts how many DINS-damaged structures have an Overture footprint within
     MATCH_DIST metres (a spatial nearest-join),
and writes one row per fire to a CSV, ranked-friendly, with a readiness tier.

Interpreting the score:
  * match_pct is a COMPLETENESS proxy -- what share of damaged structures already
    have a footprint nearby. High = little manual work.
  * It is scored against the *latest* Overture release, so:
      - a low score can mean "too destroyed" (the footprints were removed from
        current data, e.g. Camp/Paradise) rather than "badly mapped" -- those
        fires genuinely need pre-fire imagery or a versioned release.
      - prefire_version flags fires new enough (2024+, after Overture's first
        release) that a date-accurate *pre-fire* Overture version actually exists.

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" assess_footprint_readiness.py
"""
import csv
import glob
import os
import time

import geopandas as gpd
import overturemaps.core as core

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DINS_DIR   = r"C:\Users\shoang12\Downloads\dins_by_fire"                 # split_dins.py output
OUT_CSV    = r"C:\Users\shoang12\Downloads\footprint_readiness_scorecard.csv"
METRIC_CRS = "EPSG:3310"     # CA Albers (metres) -- distances measured here
MATCH_DIST = 15.0            # DINS point -> footprint match tolerance (metres)
BBOX_PAD   = 0.003           # ~300 m padding around the DINS extent (degrees)
FIRST_OVERTURE_YEAR = 2024   # first full year a pre-fire Overture release exists
# ---------------------------------------------------------------------------

FIELDS = ["fire", "year", "dins_pts", "overture_bldgs", "dins_matched",
          "match_pct", "prefire_version", "readiness", "note"]


def readiness_tier(pct):
    if pct >= 80:
        return "ready"
    if pct >= 60:
        return "moderate"
    return "needs work"


def prefire_flag(year):
    yr = int(year) if str(year).isdigit() else 0
    if yr >= FIRST_OVERTURE_YEAR:
        return "yes"
    if yr == FIRST_OVERTURE_YEAR - 1:   # partial-year edge case (first release mid-year)
        return "maybe"
    return "no"


def score_fire(dins_path):
    """Return a result row (dict) for one per-fire DINS file."""
    base = os.path.splitext(os.path.basename(dins_path))[0]      # FIRE_YEAR
    fire, _, year = base.rpartition("_")
    row = {k: "" for k in FIELDS}
    row.update({"fire": fire, "year": year})

    d = gpd.read_file(dins_path)
    if d.crs is None:
        d = d.set_crs("EPSG:4326")

    # AOI = DINS extent (+pad). We only score against DINS, so this always covers
    # the damaged structures without needing to match a perimeter file by name.
    minx, miny, maxx, maxy = d.to_crs("EPSG:4326").total_bounds
    bbox = (minx - BBOX_PAD, miny - BBOX_PAD, maxx + BBOX_PAD, maxy + BBOX_PAD)

    ov = core.geodataframe("building", bbox=bbox)               # latest Overture
    if ov.crs is None:
        ov = ov.set_crs("EPSG:4326")
    ovm = ov[["geometry"]].to_crs(METRIC_CRS).reset_index(drop=True)
    ovm["__i"] = ovm.index                                     # stable id for nunique
    dm = d.to_crs(METRIC_CRS)

    npts = len(dm)
    if len(ovm) and npts:
        j = gpd.sjoin_nearest(dm, ovm[["__i", "geometry"]],
                              max_distance=MATCH_DIST, how="inner")
        matched = j.index.nunique()
    else:
        matched = 0
    pct = round(100 * matched / npts, 1) if npts else 0.0

    row.update({"dins_pts": npts, "overture_bldgs": len(ovm), "dins_matched": matched,
                "match_pct": pct, "prefire_version": prefire_flag(year),
                "readiness": readiness_tier(pct)})
    return row


def main():
    files = sorted(glob.glob(os.path.join(DINS_DIR, "*.geojson")))
    print(f"{len(files)} fires to score\n", flush=True)

    with open(OUT_CSV, "w", newline="") as f:                  # header + reset
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    for i, fp in enumerate(files, 1):
        base = os.path.splitext(os.path.basename(fp))[0]
        t0 = time.time()
        try:
            row = score_fire(fp)
        except Exception as e:                                 # keep going; record the failure
            fire, _, year = base.rpartition("_")
            row = {k: "" for k in FIELDS}
            row.update({"fire": fire, "year": year, "note": str(e)[:150]})

        with open(OUT_CSV, "a", newline="") as f:              # append incrementally
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        print(f"[{i:>2}/{len(files)}] {base:<34} match={row['match_pct']!s:>5}%  "
              f"bldgs={row['overture_bldgs']!s:>6}  ({time.time()-t0:.0f}s)  {row['note']}",
              flush=True)

    print("\nDONE ->", OUT_CSV, flush=True)


if __name__ == "__main__":
    main()
