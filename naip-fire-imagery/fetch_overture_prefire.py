"""
Pull PRE-FIRE Overture building footprints from the Fused archive.

Why this exists: Overture's own S3 keeps only the latest ~2 releases, so the
historical (pre-fire) snapshots are gone from there -- the overturemaps package
can only give you *current* buildings. Fused mirrors *every* release on
source.coop:

    data.source.coop/fused/overture/<RELEASE>/theme=buildings/type=building/part=*/*.parquet

We query that archive directly with DuckDB, filtered by the fire's bounding box.
Two deliberate choices that sidestep the problems people hit with Fused's own
UDF runtime:
  * we control the spatial filter (a bbox WHERE clause) -> no server-side tiling,
    so no "perimeter cut in half";
  * we SELECT only the geometry -> none of Overture's nested list/struct columns
    (`sources`, `names`) come back, so no "data type <list> not understood".

For each fire it auto-picks the latest release strictly BEFORE the fire's
ALARM_DATE, clips to the perimeter, and writes
<FIRE>_<year>_prefire_footprints.gpkg.

Caveats worth knowing:
  * The archive's earliest buildings release is 2024-02 -> there is NO pre-fire
    snapshot for older fires. Those must use current Overture + NSI year-filter
    or NAIP extraction instead (see assess_footprint_readiness.py).
  * There is a gap in the archive (2024-03 -> 2024-08); a fire in that window
    falls back to the 2024-03 release, which may be too stale to beat current
    data. LEAD_WARN_DAYS flags those.

Run with the fire-naip env (all eligible fires, or name specific ones):
  & "C:/Users/shoang12/fire-naip-env/python.exe" fetch_overture_prefire.py
  & "C:/Users/shoang12/fire-naip-env/python.exe" fetch_overture_prefire.py MOUNTAIN AIRPORT
"""
import datetime
import os
import re
import sys

import duckdb
import geopandas as gpd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PERIM_PATH = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_NAME = "FIRE_NAME"
PERIM_DATE = "ALARM_DATE"
OUT_DIR    = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints_prefire"
ONLY       = None            # optional list of FIRE_NAME to limit to; None = all eligible
BBOX_PAD   = 0.003           # ~300 m padding around the perimeter bbox (degrees)
LEAD_WARN_DAYS = 45          # warn if the nearest pre-fire release is older than this
ARCHIVE    = "s3://fused/overture"     # Fused mirror on source.coop
# ---------------------------------------------------------------------------


def safe(s):
    return "".join(c if c.isalnum() else "_" for c in str(s).upper()).strip("_")


def connect():
    """A DuckDB connection wired to the source.coop S3 endpoint (anonymous)."""
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_endpoint='data.source.coop'; SET s3_url_style='path'; "
                "SET s3_use_ssl=true; SET s3_region='us-east-1';")
    return con


def building_releases(con):
    """Sorted list of every release in the archive that has a buildings theme."""
    rows = con.execute(f"SELECT file FROM glob('{ARCHIVE}/*/"
                       "theme=buildings/type=building/part=0/0.parquet')").fetchall()
    return sorted({re.search(r"overture/([^/]+)/theme=buildings", f[0]).group(1) for f in rows})


def release_date(rel):
    return datetime.date.fromisoformat(rel[:10])


def pick_prefire(rels, fire_date):
    """Latest release strictly before the fire; None if none exists (fire predates Overture)."""
    before = [r for r in rels if release_date(r) < fire_date]
    return max(before, default=None, key=release_date)


def bbox_fields(con, rel):
    """Overture renamed the bbox struct fields across schema versions -- detect which."""
    path = f"{ARCHIVE}/{rel}/theme=buildings/type=building/part=0/0.parquet"
    typ = dict((c[0], c[1]) for c in
               con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall())["bbox"]
    return ("xmin", "xmax", "ymin", "ymax") if "xmin" in typ else ("minx", "maxx", "miny", "maxy")


def fetch_buildings(con, rel, bbox):
    """Buildings from one release intersecting bbox=(minx,miny,maxx,maxy). Geometry only."""
    qminx, qminy, qmaxx, qmaxy = bbox
    xmin, xmax, ymin, ymax = bbox_fields(con, rel)
    path = f"{ARCHIVE}/{rel}/theme=buildings/type=building/part=*/*.parquet"
    q = f"""SELECT ST_AsWKB(geometry) AS wkb
            FROM read_parquet('{path}', hive_partitioning=1)
            WHERE bbox.{xmin} <= {qmaxx} AND bbox.{xmax} >= {qminx}
              AND bbox.{ymin} <= {qmaxy} AND bbox.{ymax} >= {qminy}"""
    df = con.execute(q).fetch_df()
    geom = gpd.GeoSeries.from_wkb([bytes(b) for b in df["wkb"]], crs="EPSG:4326")
    return gpd.GeoDataFrame(geometry=geom, crs="EPSG:4326")


def main():
    only = [n.upper() for n in sys.argv[1:]] or ONLY   # e.g. `... MOUNTAIN AIRPORT`
    os.makedirs(OUT_DIR, exist_ok=True)
    perim = gpd.read_file(PERIM_PATH).to_crs("EPSG:4326")
    con = connect()
    rels = building_releases(con)
    print(f"archive has {len(rels)} building releases "
          f"({rels[0]} .. {rels[-1]})"
          + (f"  |  only: {', '.join(only)}" if only else "") + "\n", flush=True)

    for _, row in perim.iterrows():
        name = row[PERIM_NAME]
        if only and str(name).upper() not in only:
            continue
        try:
            fdate = datetime.date.fromisoformat(str(row[PERIM_DATE])[:10])
        except Exception:
            continue
        rel = pick_prefire(rels, fdate)
        if rel is None:
            continue                                  # fire predates the archive
        lead = (fdate - release_date(rel)).days
        warn = "  <-- STALE (archive gap)" if lead > LEAD_WARN_DAYS else ""

        poly = row.geometry
        minx, miny, maxx, maxy = poly.bounds
        bbox = (minx - BBOX_PAD, miny - BBOX_PAD, maxx + BBOX_PAD, maxy + BBOX_PAD)
        ov = fetch_buildings(con, rel, bbox)
        ov = ov[ov.intersects(poly)].reset_index(drop=True)   # clip to perimeter

        out = os.path.join(OUT_DIR, f"{safe(name)}_{fdate.year}_prefire_footprints.gpkg")
        ov.to_file(out, driver="GPKG")
        print(f"{safe(name):<12} {fdate}  release={rel:<20} lead={lead}d  "
              f"{len(ov):>7} bldgs -> {os.path.basename(out)}{warn}", flush=True)


if __name__ == "__main__":
    main()
