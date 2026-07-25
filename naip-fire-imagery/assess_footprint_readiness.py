"""
Rank every fire by how "ready" its building-footprint data is, so downstream
work starts on the fires that need the least manual digitizing.

For each per-fire DINS damage file (from split_dins.py) it takes the DINS
extent as the area of interest and scores what share of the damaged structures
have a building footprint within MATCH_DIST metres. It does this in a TIERED
way, because the right footprint source depends on the fire's date:

  * LATEST  -- the newest Overture release (a completeness proxy, always computed).
  * PRE-FIRE -- for fires new enough to have a date-accurate snapshot in the Fused
    archive (see fetch_overture_prefire.py), the latest release strictly before
    the fire. This is what actually lines up with the pre-fire NAIP imagery.

The `recovered_delta` column (pre-fire % minus latest %) is the interesting one:
a positive value means the fire destroyed buildings that were then dropped from
current Overture, so the pre-fire snapshot recovers them (e.g. Palisades). A
negative value usually means the only pre-fire release is stale (archive gap),
so current data is actually more complete (e.g. Park).

`recommended` picks the source to use per fire:
  * "pre-fire"            -- a close pre-fire release exists; use it.
  * "latest+NAIP"         -- a pre-fire release exists but is too stale (gap);
                             current data is more complete, verify with NAIP.
  * "latest / NSI+NAIP"   -- fire predates the archive; no pre-fire Overture at
                             all, so filter current data by NSI year or use NAIP.

Run with the fire-naip env (imports fetch_overture_prefire.py alongside it):
  & "C:/Users/shoang12/fire-naip-env/python.exe" assess_footprint_readiness.py
"""
import csv
import datetime
import glob
import os
import sys
import time

import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_overture_prefire import (          # noqa: E402
    connect, building_releases, pick_prefire, release_date, fetch_buildings, safe,
)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DINS_DIR       = r"C:\Users\shoang12\Downloads\dins_by_fire"
PERIM_PATH     = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME     = "FIRE_NAME"
PERIM_DATE     = "ALARM_DATE"
OUT_CSV        = r"C:\Users\shoang12\Downloads\footprint_readiness_scorecard.csv"
METRIC_CRS     = "EPSG:3310"    # CA Albers (metres)
MATCH_DIST     = 15.0           # DINS point -> footprint match tolerance (metres)
BBOX_PAD       = 0.003          # ~300 m around the DINS extent (degrees)
LEAD_WARN_DAYS = 45             # a pre-fire release older than this counts as "stale"
# ---------------------------------------------------------------------------

FIELDS = ["fire", "year", "dins_pts",
          "latest_release", "latest_bldgs", "latest_pct",
          "prefire_release", "lead_days", "prefire_bldgs", "prefire_pct",
          "recovered_delta", "recommended", "best_pct", "readiness", "note"]


def readiness_tier(pct):
    return "ready" if pct >= 80 else ("moderate" if pct >= 60 else "needs work")


def fire_dates(perim):
    """Map (safe FIRE_NAME, year) -> fire ALARM_DATE from the perimeter file."""
    out = {}
    for _, r in perim.iterrows():
        try:
            d = datetime.date.fromisoformat(str(r[PERIM_DATE])[:10])
        except Exception:
            continue
        out[(safe(r[PERIM_NAME]), d.year)] = d
    return out


def match_pct(dins_m, ov):
    """% of DINS points with a footprint within MATCH_DIST; also returns bldg count."""
    if not len(ov):
        return 0, 0.0
    ovm = ov.to_crs(METRIC_CRS).reset_index(drop=True)
    ovm["__i"] = ovm.index
    j = gpd.sjoin_nearest(dins_m, ovm[["__i", "geometry"]], max_distance=MATCH_DIST, how="inner")
    return len(ovm), round(100 * j.index.nunique() / len(dins_m), 1)


def main():
    perim = gpd.read_file(PERIM_PATH).to_crs("EPSG:4326")
    dates = fire_dates(perim)
    con = connect()
    rels = building_releases(con)
    latest_rel = rels[-1]

    files = sorted(glob.glob(os.path.join(DINS_DIR, "*.geojson")))
    print(f"{len(files)} fires | latest archive release {latest_rel}\n", flush=True)

    with open(OUT_CSV, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    for i, fp in enumerate(files, 1):
        base = os.path.splitext(os.path.basename(fp))[0]     # FIRE_YEAR
        fire, _, yr = base.rpartition("_")
        row = {k: "" for k in FIELDS}
        row.update({"fire": fire, "year": yr})
        t0 = time.time()
        try:
            d = gpd.read_file(fp)
            if d.crs is None:
                d = d.set_crs("EPSG:4326")
            d4 = d.to_crs("EPSG:4326")
            minx, miny, maxx, maxy = d4.total_bounds
            bbox = (minx - BBOX_PAD, miny - BBOX_PAD, maxx + BBOX_PAD, maxy + BBOX_PAD)
            dm = d.to_crs(METRIC_CRS)
            row["dins_pts"] = len(dm)

            # LATEST (always)
            lb, lpct = match_pct(dm, fetch_buildings(con, latest_rel, bbox))
            row.update({"latest_release": latest_rel, "latest_bldgs": lb, "latest_pct": lpct})

            # PRE-FIRE (only if a snapshot before this fire exists)
            fdate = dates.get((fire, int(yr))) if yr.isdigit() else None
            if fdate is None and yr.isdigit():
                fdate = datetime.date(int(yr), 6, 1)          # fallback (pre-2024 -> no release anyway)
            rel = pick_prefire(rels, fdate) if fdate else None

            if rel is None:
                rec, best = "latest / NSI+NAIP", lpct
            else:
                lead = (fdate - release_date(rel)).days
                pb, ppct = match_pct(dm, fetch_buildings(con, rel, bbox))
                row.update({"prefire_release": rel, "lead_days": lead,
                            "prefire_bldgs": pb, "prefire_pct": ppct,
                            "recovered_delta": round(ppct - lpct, 1)})
                if lead <= LEAD_WARN_DAYS:
                    rec, best = "pre-fire", ppct
                else:
                    rec, best = "latest+NAIP", lpct       # pre-fire release too stale
            row.update({"recommended": rec, "best_pct": best, "readiness": readiness_tier(best)})
        except Exception as e:
            row["note"] = str(e)[:150]

        with open(OUT_CSV, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        print(f"[{i:>2}/{len(files)}] {base:<34} best={row['best_pct']!s:>5}% "
              f"({row['recommended']})  ({time.time()-t0:.0f}s)  {row['note']}", flush=True)

    print("\nDONE ->", OUT_CSV, flush=True)


if __name__ == "__main__":
    main()
