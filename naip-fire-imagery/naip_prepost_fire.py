"""
NAIP pre-fire / post-fire imagery downloader (Google Earth Engine backend)
==========================================================================

For each fire perimeter in a File Geodatabase, this script finds the nearest
NAIP acquisition BEFORE ignition (pre-fire) and the nearest AFTER containment
(post-fire), clips NAIP to the perimeter, and exports a GeoTIFF per period.

NAIP CADENCE CAVEAT: NAIP is flown ~every 2 years in CA, in summer only.
"Pre" = newest NAIP whose image date < ignition date.
"Post" = oldest NAIP whose image date > containment date.
There can be a multi-year gap, so post-fire imagery may include regrowth.

------------------------------------------------------------------------------
SETUP (one time):
    pip install earthengine-api geopandas geemap
    earthengine authenticate          # opens a browser, logs you in
Then set EE_PROJECT below to your Cloud project id.
------------------------------------------------------------------------------
"""

import csv
import os

import ee
import geopandas as gpd

# ----------------------------------------------------------------------------
# CONFIG -- edit these to match your data
# ----------------------------------------------------------------------------
EE_PROJECT   = "your-gcp-project-id"          # from earthengine / cloud console
INPUT_PATH   = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
LAYER_NAME   = None        # None = first/only layer (shapefiles have one)
NAME_FIELD   = "FIRE_NAME" # confirmed in this dataset
IGNITE_FIELD = "ALARM_DATE"# confirmed in this dataset
CONTAIN_FIELD= "CONT_DATE" # confirmed in this dataset (falls back to ignite)
STATE_FIELD  = "STATE"     # set STATE_FILTER below to limit which fires run
STATE_FILTER = None        # e.g. ["CA"] for CA-only; None = all 76 fires
DRIVE_FOLDER = "NAIP_fire_exports"
EXPORT_SCALE = 1           # meters/pixel for export (NAIP native ~0.6-1 m)
MANIFEST_CSV = r"C:\Users\shoang12\Downloads\NAIP_fire_availability.csv"
MANIFEST_ONLY= True        # True = build the availability table only (no image
                           # exports). Flip to False once you like the table.
# ----------------------------------------------------------------------------

ee.Initialize(project=EE_PROJECT)

NAIP = ee.ImageCollection("USDA/NAIP/DOQQ")


def to_ee_geometry(geom):
    """Shapely geometry (in EPSG:4326) -> ee.Geometry."""
    return ee.Geometry(geom.__geo_interface__)


def nearest_naip(ee_geom, date_str, direction):
    """
    Find the NAIP acquisition nearest to date_str on the given side.
    direction = 'before' or 'after'.
    Returns (ee.Image mosaic, year, acquisition_date 'YYYY-MM-DD').
    Returns (None, None, None) if no NAIP exists on that side.
    """
    over_aoi = NAIP.filterBounds(ee_geom)

    if direction == "before":
        coll = over_aoi.filterDate("2000-01-01", date_str).sort("system:time_start", False)
    else:  # after
        coll = over_aoi.filterDate(date_str, "2100-01-01").sort("system:time_start", True)

    n = coll.size().getInfo()
    if n == 0:
        return None, None, None

    # Take the single nearest acquisition date, then mosaic all DOQQ tiles
    # from that same campaign year so the perimeter is fully covered.
    nearest = ee.Image(coll.first())
    nearest_date = ee.Date(nearest.get("system:time_start"))
    year     = nearest_date.get("year").getInfo()
    acq_date = nearest_date.format("YYYY-MM-dd").getInfo()

    same_year = over_aoi.filter(ee.Filter.calendarRange(year, year, "year"))
    mosaic = same_year.mosaic().clip(ee_geom)
    return mosaic, year, acq_date


def export_clip(image, ee_geom, filename):
    """Queue a Drive export of the clipped image."""
    task = ee.batch.Export.image.toDrive(
        image=image.toUint8(),          # NAIP DOQQ is 8-bit
        description=filename[:100],      # EE caps description length
        folder=DRIVE_FOLDER,
        fileNamePrefix=filename,
        region=ee_geom,
        scale=EXPORT_SCALE,
        crs="EPSG:4326",
        maxPixels=1e13,
    )
    task.start()
    print(f"  -> queued export: {filename}")
    # --- Local-disk alternative for small fires (uncomment, needs geemap) ---
    # import geemap, os
    # geemap.download_ee_image(
    #     image.toUint8(), filename=os.path.join("naip_out", filename + ".tif"),
    #     region=ee_geom, scale=EXPORT_SCALE, crs="EPSG:4326")


def safe_name(value, fid):
    s = "".join(c if c.isalnum() else "_" for c in str(value or f"fire_{fid}"))
    return s.strip("_") or f"fire_{fid}"


def main():
    gdf = gpd.read_file(INPUT_PATH, layer=LAYER_NAME)
    if STATE_FILTER:
        gdf = gdf[gdf[STATE_FIELD].isin(STATE_FILTER)].copy()
    gdf = gdf.to_crs("EPSG:4326")  # GEE expects lon/lat

    print(f"Loaded {len(gdf)} fire features from {INPUT_PATH}\n")

    manifest = []
    for fid, row in gdf.iterrows():
        name = safe_name(row.get(NAME_FIELD), fid)
        ignite  = row.get(IGNITE_FIELD)
        contain = row.get(CONTAIN_FIELD) or ignite
        if ignite is None or row.geometry is None or row.geometry.is_empty:
            print(f"[{name}] skipped -- missing date or geometry")
            continue

        ignite_str  = str(ignite)[:10]   # 'YYYY-MM-DD'
        contain_str = str(contain)[:10]
        ee_geom = to_ee_geometry(row.geometry)

        print(f"[{name}]  ignite={ignite_str}  contain={contain_str}")

        pre_img,  pre_yr,  pre_date  = nearest_naip(ee_geom, ignite_str,  "before")
        post_img, post_yr, post_date = nearest_naip(ee_geom, contain_str, "after")

        # --- availability record for this fire ---
        gap = (post_yr - pre_yr) if (pre_yr and post_yr) else ""
        manifest.append({
            "FIRE_NAME":              row.get(NAME_FIELD),
            "STATE":                  row.get(STATE_FIELD),
            "ALARM_DATE":             ignite_str,
            "CONT_DATE":              contain_str,
            "NAIP_PreFire_Available": "yes" if pre_img  is not None else "no",
            "NAIP_PreFire_Date":      pre_date  or "",
            "NAIP_PreFire_Year":      pre_yr    or "",
            "NAIP_PostFire_Available":"yes" if post_img is not None else "no",
            "NAIP_PostFire_Date":     post_date or "",
            "NAIP_PostFire_Year":     post_yr   or "",
            "Pre_to_Post_Year_Gap":   gap,
        })
        print(f"  pre:  {'yes ' + str(pre_date) if pre_img is not None else 'no'}"
              f"   post: {'yes ' + str(post_date) if post_img is not None else 'no'}")

        if not MANIFEST_ONLY:
            if pre_img is not None:
                export_clip(pre_img, ee_geom, f"{name}_pre_{pre_yr}")
            if post_img is not None:
                export_clip(post_img, ee_geom, f"{name}_post_{post_yr}")

    # --- write the availability table ---
    if manifest:
        with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
            w.writeheader()
            w.writerows(manifest)
        print(f"\nWrote availability table ({len(manifest)} fires): {MANIFEST_CSV}")

    if MANIFEST_ONLY:
        print("MANIFEST_ONLY is True -- no images exported. "
              "Review the CSV, then set MANIFEST_ONLY = False to export GeoTIFFs.")
    else:
        print("\nExports queued. Track progress in the Tasks tab at "
              "https://code.earthengine.google.com/tasks")


if __name__ == "__main__":
    main()
