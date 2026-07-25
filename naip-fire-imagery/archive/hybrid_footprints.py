"""
Hybrid footprints: refine Microsoft footprints with SAM box-prompts on the
pre-fire NAIP, per fire. Keeps MS's one-polygon-per-building discreteness while
re-tracing each boundary to the date-accurate NAIP rooftop.

Tiles the clip (SAM can't encode a whole fire at once): each MS footprint is
assigned to the tile holding its centroid, refined with a box prompt, and the
resulting polygon is written back in map coordinates. Output layout matches the
other footprint sources so join_dins_to_footprints.py runs on it unchanged.

Run with sam-env (segment_anything + geopandas + rasterio):
  & "C:/Users/shoang12/sam-env/python.exe" hybrid_footprints.py
"""
import glob
import os
from collections import defaultdict

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.windows import Window
from rasterio.features import shapes as rio_shapes
from shapely.geometry import shape as shp_shape
from segment_anything import sam_model_registry, SamPredictor

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CKPT     = r"C:\Users\shoang12\.cache\torch\hub\checkpoints\sam_vit_h_4b8939.pth"
CLIP_DIR = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\NAIP_clipped"
MS_DIR   = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints"      # MS footprints = prompts
OUT_DIR  = r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints_hybrid"
DEVICE   = "cuda"          # "cuda" (GPU) or "cpu"
TILE     = 896             # core tile; +2*MARGIN stays <=1024 so SAM doesn't downsample
MARGIN   = 64
ONLY     = None            # optional: limit to a list of keys e.g. ["ZOGG_2020"]
OVERWRITE = False
# ---------------------------------------------------------------------------


def largest_polygon(mask, transform):
    best, best_area = None, 0
    for gj, val in rio_shapes(mask.astype("uint8"), mask=mask, transform=transform):
        g = shp_shape(gj)
        if g.area > best_area:
            best, best_area = g, g.area
    return best


def refine_fire(clip_path, ms_path, out_path, predictor):
    src = rasterio.open(clip_path)
    ms = gpd.read_file(ms_path).to_crs(src.crs).reset_index(drop=True)
    H, W = src.height, src.width

    # assign each MS footprint to the tile containing its centroid
    tiles = defaultdict(list)
    for i, c in enumerate(ms.geometry.centroid):
        r, cc = src.index(c.x, c.y)
        tiles[(r // TILE, cc // TILE)].append(i)

    out_geoms = []
    for (tr, tc), members in tiles.items():
        r0, c0 = tr * TILE, tc * TILE
        rr0, cc0 = max(r0 - MARGIN, 0), max(c0 - MARGIN, 0)
        rr1, cc1 = min(r0 + TILE + MARGIN, H), min(c0 + TILE + MARGIN, W)
        win = Window(cc0, rr0, cc1 - cc0, rr1 - rr0)
        arr = src.read([1, 2, 3], window=win).transpose(1, 2, 0).astype("uint8")
        if arr.max() == 0:                     # all nodata -> skip
            continue
        wt = src.window_transform(win)
        predictor.set_image(arr)
        for i in members:
            minx, miny, maxx, maxy = ms.geometry.iloc[i].bounds
            gr0, gc0 = src.index(minx, maxy)
            gr1, gc1 = src.index(maxx, miny)
            box = np.array([gc0 - cc0, gr0 - rr0, gc1 - cc0, gr1 - rr0])
            masks, _, _ = predictor.predict(box=box, multimask_output=False)
            poly = largest_polygon(masks[0], wt)
            if poly is not None:
                out_geoms.append(poly)

    if out_geoms:
        gpd.GeoDataFrame(geometry=out_geoms, crs=src.crs).to_file(out_path)
    return len(out_geoms)


def fire_key(clip_name):
    base = os.path.splitext(clip_name)[0]
    return base[:-len("_pre_clip")] if base.endswith("_pre_clip") else base


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"loading SAM on {DEVICE}...")
    sam = sam_model_registry["vit_h"](checkpoint=CKPT).to(DEVICE)
    predictor = SamPredictor(sam)

    clips = sorted(glob.glob(os.path.join(CLIP_DIR, "*_pre_clip.tif")))
    done = skipped = 0
    for clip in clips:
        key = fire_key(os.path.basename(clip))
        if ONLY and key not in ONLY:
            continue
        ms_path = os.path.join(MS_DIR, key + "_pre_footprints.shp")
        if not os.path.exists(ms_path):
            print(f"[{key}] no MS footprints -- skipping"); skipped += 1; continue
        out_path = os.path.join(OUT_DIR, key + "_pre_footprints.shp")
        if os.path.exists(out_path) and not OVERWRITE:
            print(f"[{key}] already done -- skipping"); skipped += 1; continue
        n = refine_fire(clip, ms_path, out_path, predictor)
        print(f"[{key}] refined {n} buildings -> {os.path.basename(out_path)}")
        done += 1

    print(f"\nDone. refined={done}  skipped={skipped}\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
