"""
Batch: merge NAIP tiles per fire, reproject to the fire's native UTM zone, and
clip to its perimeter -- all in one disk-based gdal.Warp pass per fire.

Expected layout -- one subfolder of tiles per fire, named <FIRE>_<year> (the AOI
convention), optionally with a _pre / _post suffix so both periods coexist:

    TILES_ROOT/
        ZOGG_2020_pre/   m_4012243_se_..jp2, ...   (Web Mercator or UTM ok)
        ZOGG_2020_post/  m_4012243_se_..tif, ...
        DIXIE_2021/      ...

Each output is written to OUT_DIR/<folder>_clip.tif in NAD83/UTM at 0.6 m, so
pre and post align regardless of the source tile projection. Fires already
clipped are skipped (set OVERWRITE=True to redo). One fire failing doesn't stop
the batch.

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" clip_fire_raster.py
"""
import glob
import os
import tempfile

import geopandas as gpd
from osgeo import gdal, osr

gdal.UseExceptions()

# ---------------------------------------------------------------------------
# CONFIG -- edit these
# ---------------------------------------------------------------------------
TILES_ROOT = r"C:\Users\shoang12\Downloads\NAIP_TILES"   # parent; one subfolder per fire
TILE_EXTS  = ("*.tif", "*.tiff", "*.jp2")

PERIM_PATH  = r"C:\Users\shoang12\Downloads\AllFires_1kmBuffer\AllFires_1kmBuffer.shp"
PERIM_LAYER = None            # set a layer name if PERIM_PATH is a .gdb
NAME_FIELD  = "FIRE_NAME"
DATE_FIELD  = "ALARM_DATE"    # used to build the <FIRE>_<year> key

OUT_RES   = 0.6               # output pixel size (m); 0.6 = native 60 cm NAIP
OUT_DIR   = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\NAIP_clipped"
OVERWRITE = False            # False = skip fires already clipped (resume a batch)
# ---------------------------------------------------------------------------


def fire_key(name, year):
    safe = "".join(c if c.isalnum() else "_" for c in str(name)).strip("_")
    return f"{safe}_{year}"


def load_perimeters():
    gdf = gpd.read_file(PERIM_PATH, layer=PERIM_LAYER)
    gdf["__key"] = [fire_key(n, str(d)[:4])
                    for n, d in zip(gdf[NAME_FIELD], gdf[DATE_FIELD])]
    return gdf


def find_tiles(folder):
    tiles = []
    for pat in TILE_EXTS:
        tiles += glob.glob(os.path.join(folder, pat))
    return sorted(tiles)


def nad83_utm_epsg(perim_wgs84):
    """NAD83 / UTM zone EPSG (269zz) from the perimeter centroid longitude."""
    lon = perim_wgs84.geometry.union_all().centroid.x
    return 26900 + int((lon + 180) // 6) + 1


def src_epsg(tile):
    sr = osr.SpatialReference(wkt=gdal.Open(tile).GetProjection())
    return sr.GetAuthorityCode(None)


def warp_clip(tiles, perim_subset, out_path, target_epsg):
    # Cutline in WGS84 (gdal reprojects it to the target as needed).
    perim_wgs84 = perim_subset.to_crs("EPSG:4326")
    tmp_cut = os.path.join(tempfile.gettempdir(), "cutline_tmp.geojson")
    if os.path.exists(tmp_cut):
        os.remove(tmp_cut)
    perim_wgs84.to_file(tmp_cut, driver="GeoJSON")

    # Tiles already in the target CRS are copied (nearest, no blur); only
    # off-projection tiles (e.g. Web Mercator pre tiles) get resampled.
    reproject = str(src_epsg(tiles[0])) != str(target_epsg)
    resample = "cubic" if reproject else "near"

    opts = gdal.WarpOptions(
        format="GTiff",
        dstSRS=f"EPSG:{target_epsg}",
        xRes=OUT_RES, yRes=OUT_RES, targetAlignedPixels=True,
        cutlineDSName=tmp_cut, cropToCutline=True,
        dstNodata=0, resampleAlg=resample, multithread=True,
        creationOptions=["COMPRESS=DEFLATE", "BIGTIFF=YES", "TILED=YES"],
    )
    gdal.Warp(out_path, tiles, options=opts)
    os.remove(tmp_cut)

    ds = gdal.Open(out_path)
    return ds.RasterXSize, ds.RasterYSize, resample


def main():
    perims = load_perimeters()
    os.makedirs(OUT_DIR, exist_ok=True)

    fire_dirs = [d for d in sorted(glob.glob(os.path.join(TILES_ROOT, "*")))
                 if os.path.isdir(d)]
    if not fire_dirs:
        raise SystemExit(f"No per-fire subfolders found in {TILES_ROOT}")
    print(f"Found {len(fire_dirs)} fire folder(s) in {TILES_ROOT}\n")

    done = skipped = failed = 0
    for d in fire_dirs:
        key = os.path.basename(d)
        out_path = os.path.join(OUT_DIR, f"{key}_clip.tif")

        if os.path.exists(out_path) and not OVERWRITE:
            print(f"[{key}] already done -- skipping")
            skipped += 1
            continue

        tiles = find_tiles(d)
        if not tiles:
            print(f"[{key}] no tiles found -- skipping")
            skipped += 1
            continue

        # Match the perimeter whose <FIRE>_<year> key equals the folder name or
        # is a prefix of it (so ZOGG_2020_pre / _post both map to ZOGG_2020).
        cand = [k for k in perims["__key"].unique()
                if key == k or key.startswith(k + "_")]
        subset = perims[perims["__key"] == max(cand, key=len)] if cand \
            else perims.iloc[0:0]
        if subset.empty:
            print(f"[{key}] no matching perimeter -- skipping")
            failed += 1
            continue

        try:
            epsg = nad83_utm_epsg(subset.to_crs("EPSG:4326"))
            w, h, alg = warp_clip(tiles, subset, out_path, epsg)
            print(f"[{key}] {len(tiles)} tiles -> EPSG:{epsg} {alg} "
                  f"-> clip {w} x {h} px")
            done += 1
        except Exception as e:
            if os.path.exists(out_path):     # don't leave a partial/corrupt file
                os.remove(out_path)
            print(f"[{key}] FAILED: {e}")
            failed += 1

    print(f"\nDone. clipped={done}  skipped={skipped}  failed={failed}")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
