"""
Batch building-footprint extraction from pre-fire NAIP clips (ArcGIS Pro DL).

For each *_pre_clip.tif that has a matching per-fire DINS file, runs Esri's
"Building Footprint Extraction - USA" Mask R-CNN on the GPU, regularizes the
shapes, and writes <FIRE>_<year>_pre_footprints.shp.

IMPORTANT -- run with the BASE ArcGIS Python (arcpy), NOT the fire-naip clone,
and this script imports arcpy ONLY (importing gdal/rasterio/geopandas in the
same process breaks arcpy's native DLLs):

  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" extract_footprints.py
"""
import glob
import os

import arcpy

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CLIP_DIR  = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\NAIP_clipped"
DINS_DIR  = r"C:\Users\shoang12\Downloads\dins_by_fire"      # gate: only fires with DINS
MODEL     = r"C:\Users\shoang12\Downloads\usa_building_footprints.dlpk"
OUT_DIR   = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints"
ONLY      = None         # optional: limit to a list of keys e.g. ["ZOGG_2020"]; None = all DINS fires
THRESHOLD = 0.5          # detection confidence (lower = more buildings, more false positives)
TOLERANCE = 0.6          # regularize tolerance (m); ~1 NAIP pixel
OVERWRITE = False        # skip fires already extracted
# ---------------------------------------------------------------------------

arcpy.CheckOutExtension("ImageAnalyst")
try:
    arcpy.CheckOutExtension("3D")            # for RegularizeBuildingFootprint
    HAS_3D = True
except Exception:
    HAS_3D = False
arcpy.env.processorType = "GPU"
arcpy.env.gpuId = 0
arcpy.env.overwriteOutput = True


def fire_key(clip_name):
    """'BOBCAT_2020_pre_clip.tif' -> 'BOBCAT_2020'."""
    base = os.path.splitext(clip_name)[0]
    return base[:-len("_pre_clip")] if base.endswith("_pre_clip") else base


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    clips = sorted(glob.glob(os.path.join(CLIP_DIR, "*_pre_clip.tif")))
    print(f"Found {len(clips)} pre-fire clips\n")

    done = skipped = failed = 0
    for clip in clips:
        key = fire_key(os.path.basename(clip))

        if ONLY and key not in ONLY:
            continue
        if not os.path.exists(os.path.join(DINS_DIR, key + ".geojson")):
            print(f"[{key}] no DINS -- skipping")
            skipped += 1
            continue

        out = os.path.join(OUT_DIR, f"{key}_pre_footprints.shp")
        if os.path.exists(out) and not OVERWRITE:
            print(f"[{key}] already done -- skipping")
            skipped += 1
            continue

        try:
            raw = os.path.join(arcpy.env.scratchGDB, "raw_det")
            arcpy.ia.DetectObjectsUsingDeepLearning(
                clip, raw, MODEL,
                f"padding 64;threshold {THRESHOLD};batch_size 4;tile_size 512",
                "NMS", confidence_score_field="Confidence", max_overlap_ratio=0.1,
            )
            n = int(arcpy.management.GetCount(raw)[0])
            if HAS_3D:
                arcpy.ddd.RegularizeBuildingFootprint(raw, out, "RIGHT_ANGLES",
                                                      tolerance=TOLERANCE)
            else:
                arcpy.management.CopyFeatures(raw, out)
            print(f"[{key}] {n} buildings -> {os.path.basename(out)}")
            done += 1
        except Exception as e:
            print(f"[{key}] FAILED: {e}")
            failed += 1

    print(f"\nDone. extracted={done}  skipped={skipped}  failed={failed}")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
