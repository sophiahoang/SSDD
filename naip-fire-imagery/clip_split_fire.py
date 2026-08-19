"""
Clip oversized fires ONE PORTION AT A TIME, for every split fire, so you get
separate manageable clips instead of one giant mosaic per fire.

Some fires are too large to download/clip in one piece (August Complex, Dixie,
the lightning complexes...). Split each into portions first (which writes the
per-fire AOI zips for EarthExplorer plus a <prefix>_quadrants.gpkg cutline file),
download each portion, then run this to clip every portion to its own boundary.

For each fire in FIRES it reads that fire's cutline file and, for each portion in
it, clips the matching tile folder to that portion's slice of the perimeter.

Setup: put each portion's downloaded tiles in its own folder under TILES_ROOT,
named  <prefix>_<portion>_pre  (and/or _post). The <portion> labels are whatever
that fire was split into -- SW/NW/SE/NE for a 4-way split, S/N or W/E for a 2-way
split (see the `portion` field in the gpkg). Example for Dixie:

    NAIP_TILES\
        DIXIE_2021_SW_pre\
        DIXIE_2021_NW_pre\
        DIXIE_2021_SE_pre\
        DIXIE_2021_NE_pre\

Run with the fire-naip env:
  & "C:/Users/shoang12/fire-naip-env/python.exe" clip_split_fire.py

Output: OUT_DIR\<prefix>_<portion>_<pre|post>_clip.tif -- one per portion folder,
each clipped to its slice of the fire and reprojected to NAD83/UTM, so a fire's
portions tile back together seamlessly. (For normal-sized fires use
clip_fire_raster.py instead -- this script is only for the split ones.)
"""
import os
os.environ.setdefault("GDAL_MEM_ENABLE_OPEN", "YES")
import glob
import geopandas as gpd
from osgeo import gdal
gdal.UseExceptions()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TILES_ROOT   = r"C:\Users\shoang12\Downloads\NAIP_TILES"
CUTLINES_DIR = r"C:\Users\shoang12\Downloads\CA_fire_AOIs"           # holds <prefix>_quadrants.gpkg
OUT_DIR      = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\NAIP_clipped"
OUT_RES      = 0.6            # metres
OVERWRITE    = False          # True = re-clip even if the output already exists
TILE_EXTS    = ("*.tif", "*.tiff", "*.jp2")

# fire prefixes to process -- each needs a <prefix>_quadrants.gpkg in CUTLINES_DIR
FIRES = [
    "AUGUST_COMPLEX_2020",
    "DIXIE_2021",
    "SCU_LIGHTNING_COMPLEX_2020",
    "NORTH_COMPLEX_2020",
    "CZU_LIGHTNING_COMPLEX_2020",
]
# ---------------------------------------------------------------------------


def nad83_utm_epsg(lon, lat):
    return 26900 + int((lon + 180) / 6) + 1        # NAD83 UTM North zones = 269zz


def clip_folder(folder, piece, epsg, out_path):
    tiles = []
    for pat in TILE_EXTS:
        tiles += glob.glob(os.path.join(folder, pat))
    if not tiles:
        print(f"    {os.path.basename(folder)}: no tiles — skipped")
        return
    cut = out_path + ".cutline.geojson"
    gpd.GeoDataFrame(geometry=[piece], crs="EPSG:4326").to_file(cut, driver="GeoJSON")
    opts = gdal.WarpOptions(
        format="GTiff", dstSRS=f"EPSG:{epsg}", xRes=OUT_RES, yRes=OUT_RES,
        targetAlignedPixels=True, cutlineDSName=cut, cropToCutline=True,
        dstNodata=0, resampleAlg="near", multithread=True,
        creationOptions=["COMPRESS=DEFLATE", "BIGTIFF=YES", "TILED=YES"],
    )
    print(f"    clipping {os.path.basename(folder)} ({len(tiles)} tiles) -> {os.path.basename(out_path)}")
    gdal.Warp(out_path, tiles, options=opts)
    if os.path.exists(cut):
        os.remove(cut)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for prefix in FIRES:
        cutfile = os.path.join(CUTLINES_DIR, f"{prefix}_quadrants.gpkg")
        if not os.path.exists(cutfile):
            print(f"{prefix}: no cutline file ({os.path.basename(cutfile)}) — skipped")
            continue
        print(f"\n=== {prefix} ===")
        quads = gpd.read_file(cutfile).to_crs("EPSG:4326")
        for _, row in quads.iterrows():
            q = row["portion"]
            piece = row.geometry
            c = piece.centroid
            epsg = nad83_utm_epsg(c.x, c.y)
            for period in ("pre", "post"):
                folder = os.path.join(TILES_ROOT, f"{prefix}_{q}_{period}")
                if not os.path.isdir(folder):
                    continue
                out_path = os.path.join(OUT_DIR, f"{prefix}_{q}_{period}_clip.tif")
                if os.path.exists(out_path) and not OVERWRITE:
                    print(f"    {os.path.basename(out_path)} exists — skipping")
                    continue
                clip_folder(folder, piece, epsg, out_path)
    print("\ndone")


if __name__ == "__main__":
    main()
