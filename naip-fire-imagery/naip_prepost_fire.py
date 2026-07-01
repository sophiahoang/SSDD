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
EE_PROJECT   = "ssdd-499921"                  # from earthengine / cloud console
INPUT_PATH   = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
LAYER_NAME   = None        # None = first/only layer (shapefiles have one)
NAME_FIELD   = "FIRE_NAME" # confirmed in this dataset
IGNITE_FIELD = "ALARM_DATE"# confirmed in this dataset
CONTAIN_FIELD= "CONT_DATE" # confirmed in this dataset (falls back to ignite)
STATE_FIELD  = "STATE"     # set STATE_FILTER below to limit which fires run
STATE_FILTER = None        # e.g. ["CA"] for CA-only; None = all 76 fires
ONLY_FIRES   = None        # test-batch: run only these FIRE_NAMEs. Set to None
                           # to process every fire that passes STATE_FILTER.
# Resolution: by default each image is written at its OWN native scale and
# native UTM projection -- highest possible quality, no reprojection blur.
# (Recent CA NAIP is 0.6 m; older years are 1 m.)
HIRES_MAX_KM2 = None       # None = always native res. If set (e.g. 200), fires
                           # LARGER than this many km2 are downsampled to
                           # COARSE_SCALE so the mega-fires stay manageable.
COARSE_SCALE  = 3          # meters/pixel used only for fires above HIRES_MAX_KM2
MANIFEST_CSV = r"C:\Users\shoang12\Downloads\NAIP_fire_availability.csv"
MANIFEST_ONLY= True        # True = build the availability table only (no image
                           # exports). Flip to False once you like the table.

# --- where the GeoTIFFs go when MANIFEST_ONLY is False ---
EXPORT_TARGET = "onedrive" # "onedrive" = download locally into OneDrive (syncs
                           #              to the cloud automatically)
                           # "drive"    = export to Google Drive instead
ONEDRIVE_BASE = r"C:\Users\shoang12\OneDrive - Cal Poly\NAIP_fire_imagery"
DRIVE_FOLDER  = "NAIP_fire_exports"   # only used if EXPORT_TARGET == "drive"
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
    Returns (mosaic, year, date_min, date_max, native_scale_m, native_crs),
    where date_min..date_max is the acquisition-date SPAN of that campaign
    year's tiles over the fire (NAIP flies a region across many days, so the
    search window should be the whole year, not a single date).
    Returns six Nones if no NAIP exists on that side.
    """
    over_aoi = NAIP.filterBounds(ee_geom)

    if direction == "before":
        coll = over_aoi.filterDate("2000-01-01", date_str).sort("system:time_start", False)
    else:  # after
        coll = over_aoi.filterDate(date_str, "2100-01-01").sort("system:time_start", True)

    n = coll.size().getInfo()
    if n == 0:
        return None, None, None, None, None, None

    # Nearest acquisition determines the campaign year; then mosaic all DOQQ
    # tiles from that year over the fire (they span multiple days).
    nearest = ee.Image(coll.first())
    year = ee.Date(nearest.get("system:time_start")).get("year").getInfo()

    # Native resolution + projection of the source tile -- export at THIS for
    # full quality (mosaic() otherwise defaults to a 1-degree EPSG:4326 grid).
    proj = nearest.select(0).projection()
    native_scale = proj.nominalScale().getInfo()
    native_crs   = proj.crs().getInfo()

    same_year = over_aoi.filter(ee.Filter.calendarRange(year, year, "year"))
    date_min = ee.Date(same_year.aggregate_min("system:time_start")).format("YYYY-MM-dd").getInfo()
    date_max = ee.Date(same_year.aggregate_max("system:time_start")).format("YYYY-MM-dd").getInfo()
    mosaic = same_year.mosaic().clip(ee_geom)
    return mosaic, year, date_min, date_max, native_scale, native_crs


def deliver(image, ee_geom, fire_folder, period, year, scale, crs):
    """
    Write one clipped NAIP image for a fire at the given scale (m) and crs.
    fire_folder = e.g. 'EATON_2025'; period = 'pre' or 'post'.
    Routes to OneDrive (local download) or Google Drive per EXPORT_TARGET.
    """
    out_name = f"{period}_{year}"   # e.g. pre_2022.tif / post_2022.tif

    if EXPORT_TARGET == "onedrive":
        import geemap
        out_dir = os.path.join(ONEDRIVE_BASE, fire_folder)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, out_name + ".tif")
        if os.path.exists(out_path):
            print(f"  -> exists, skipping: {fire_folder}\\{out_name}.tif")
            return
        # download_ee_image auto-tiles large images so big fires still work.
        geemap.download_ee_image(
            image.toUint8(), filename=out_path,
            region=ee_geom, scale=scale, crs=crs)
        print(f"  -> saved: {fire_folder}\\{out_name}.tif  ({scale} m, {crs})")

    else:  # "drive"
        task = ee.batch.Export.image.toDrive(
            image=image.toUint8(),
            description=f"{fire_folder}_{out_name}"[:100],
            folder=DRIVE_FOLDER,
            fileNamePrefix=f"{fire_folder}_{out_name}",
            region=ee_geom,
            scale=scale,
            crs=crs,
            maxPixels=1e13,
        )
        task.start()
        print(f"  -> queued Drive export: {fire_folder}_{out_name}  ({scale} m)")


def safe_name(value, fid):
    s = "".join(c if c.isalnum() else "_" for c in str(value or f"fire_{fid}"))
    return s.strip("_") or f"fire_{fid}"


def main():
    gdf = gpd.read_file(INPUT_PATH, layer=LAYER_NAME)
    if STATE_FILTER:
        gdf = gdf[gdf[STATE_FIELD].isin(STATE_FILTER)].copy()
    if ONLY_FIRES:
        gdf = gdf[gdf[NAME_FIELD].isin(ONLY_FIRES)].copy()
    gdf["__km2"] = gdf.geometry.area / 1e6   # area in projected CRS (pre-reproj)
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
        # Folder named for the fire + its year, so duplicate names (e.g. two
        # VALLEY fires, two CREEK fires) don't collide.
        fire_folder = f"{name}_{ignite_str[:4]}"
        ee_geom = to_ee_geometry(row.geometry)

        print(f"[{name}]  ignite={ignite_str}  contain={contain_str}")

        pre_img,  pre_yr,  pre_min,  pre_max,  pre_scale,  pre_crs  = nearest_naip(ee_geom, ignite_str,  "before")
        post_img, post_yr, post_min, post_max, post_scale, post_crs = nearest_naip(ee_geom, contain_str, "after")

        # Downsample only if this fire is bigger than the hi-res threshold.
        km2 = row["__km2"]
        downsample = HIRES_MAX_KM2 is not None and km2 > HIRES_MAX_KM2

        # Acquisition span of the campaign year -- search this whole window in
        # EarthExplorer, not a single date (tiles are flown across many days).
        def span(lo, hi):
            if not lo:
                return ""
            return lo if lo == hi else f"{lo} to {hi}"

        # --- availability record for this fire ---
        gap = (post_yr - pre_yr) if (pre_yr and post_yr) else ""
        manifest.append({
            "FIRE_NAME":               row.get(NAME_FIELD),
            "STATE":                   row.get(STATE_FIELD),
            "ALARM_DATE":              ignite_str,
            "CONT_DATE":               contain_str,
            "NAIP_PreFire_Available":  "yes" if pre_img  is not None else "no",
            "NAIP_PreFire_Year":       pre_yr or "",
            "NAIP_PreFire_DateRange":  span(pre_min, pre_max),
            "NAIP_PostFire_Available": "yes" if post_img is not None else "no",
            "NAIP_PostFire_Year":      post_yr or "",
            "NAIP_PostFire_DateRange": span(post_min, post_max),
            "Pre_to_Post_Year_Gap":    gap,
        })
        print(f"  pre:  {'yes ' + span(pre_min, pre_max) if pre_img is not None else 'no'}"
              f"   post: {'yes ' + span(post_min, post_max) if post_img is not None else 'no'}")

        if not MANIFEST_ONLY:
            if pre_img is not None:
                scale = COARSE_SCALE if downsample else pre_scale
                deliver(pre_img, ee_geom, fire_folder, "pre", pre_yr, scale, pre_crs)
            if post_img is not None:
                scale = COARSE_SCALE if downsample else post_scale
                deliver(post_img, ee_geom, fire_folder, "post", post_yr, scale, post_crs)

    # --- write the availability table (skip for test batches so we don't
    #     overwrite the full 76-fire master CSV) ---
    if manifest and not ONLY_FIRES:
        with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
            w.writeheader()
            w.writerows(manifest)
        print(f"\nWrote availability table ({len(manifest)} fires): {MANIFEST_CSV}")

    if MANIFEST_ONLY:
        print("MANIFEST_ONLY is True -- no images exported. "
              "Review the CSV, then set MANIFEST_ONLY = False to export GeoTIFFs.")
    elif EXPORT_TARGET == "onedrive":
        print(f"\nDone. GeoTIFFs saved under {ONEDRIVE_BASE}\\<FIRE>_<year>\\ "
              "and syncing to OneDrive.")
    else:
        print("\nExports queued. Track progress in the Tasks tab at "
              "https://code.earthengine.google.com/tasks")


if __name__ == "__main__":
    main()
