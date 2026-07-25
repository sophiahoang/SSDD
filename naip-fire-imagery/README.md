# NAIP Pre-/Post-Fire Imagery

Tooling to assemble high-resolution **NAIP aerial imagery** (60 cm where
available) from *before* and *after* each wildfire in a study, clipped to the
fire perimeter.

The imagery itself is downloaded by hand from **USGS EarthExplorer** (that's
where the full-quality original tiles live). The scripts here do everything
around that: figure out *which* NAIP years each fire needs, hand you a ready-to-
upload search area for each fire, and — once you've downloaded the tiles —
mosaic, reproject, and clip them to the perimeter automatically.

## Start here — what this folder does

Two things, for a set of wildfires:

- **A · Imagery** — assemble before/after **NAIP aerial photos** for each fire,
  clipped to the fire outline.
- **B · Buildings** — get **building footprints** for each fire and tag them with
  **CAL FIRE damage** data (which structures were destroyed / damaged).

The building footprints are the hand-off to the **SSDD** analysis in the parent
folder (`../SSDD.ipynb`).

### Which scripts do I actually run?

You don't run all of them — pick the goal:

| I want… | Run (in order) |
|---------|----------------|
| **Imagery for a fire** | `naip_prepost_fire.py` → `make_fire_aois.py` → *(download tiles from EarthExplorer by hand)* → `check_tiles.py` → `clip_fire_raster.py` |
| **Building footprints** *(recommended)* | `fetch_ms_buildings.py` → `join_dins_to_footprints.py` |
| **Sharper footprints** *(optional)* | `run_hybrid.ps1` (refines the MS footprints against NAIP with AI, then squares them up) |
| **Damage points per fire** | `split_dins.py` |

**Experimental — safe to ignore:** `extract_footprints.py`,
`export_training_data.py`, `train_footprint_model.py` are a deep-learning
footprint approach we tested. Microsoft footprints worked better, so these are
kept only for reference.

Detailed step-by-step for each is below.

## The big picture

```
                                             ┌── you do this by hand ──┐
 fire perimeters        availability CSV      EarthExplorer download      clipped rasters
 (shapefile)   ──▶  +   AOI zips per fire ──▶ (upload AOI, enter dates, ──▶ per fire, pre & post
                        (the scripts)          bulk-download tiles)         (the script)
```

1. **`naip_prepost_fire.py`** → builds `NAIP_fire_availability.csv`: for every
   fire, which NAIP year to use for pre and post, plus acquisition date ranges.
   *This has already been run — the results are the **"NAIP Availability"**
   spreadsheet in the **SSDD SharePoint**, so you normally start at step 2/3.*
2. **`make_fire_aois.py`** → writes one small zipped shapefile per fire
   (`CA_fire_AOIs/<FIRE>_<year>.zip`) to upload to EarthExplorer as the search
   area. *Also already run — the zips are in the **NAIP folder in SSDD
   SharePoint** alongside the availability spreadsheet.*
3. **You** download the NAIP tiles from EarthExplorer (see workflow below).
4. **`clip_fire_raster.py`** → mosaics each fire's tiles, reprojects them to the
   fire's native UTM zone, and clips to the perimeter.

## Why the dates matter

NAIP is flown roughly **every 2 years**, in summer only, so "pre" and "post"
are the nearest flights, not the days around the fire. Also, **60 cm imagery
only exists for recent years** — in California ~2018 onward is 60 cm, earlier
years are 1 m, and the oldest (≈2009 and before) can be 1–2 m. The availability
CSV reports the exact year/date chosen so you know what resolution to expect.

---

## Files

| File | Purpose |
|------|---------|
| `setup.ps1` | one-time environment setup (clone Python env, install packages, GEE auth) |
| `naip_prepost_fire.py` | build the availability CSV (which NAIP year per fire, pre & post) |
| `make_fire_aois.py` | split fires into per-fire AOI zips for EarthExplorer |
| `check_tiles.py` | **verify each tile folder is complete** (have vs. need) before clipping |
| `clip_fire_raster.py` | **mosaic + reproject-to-UTM + clip** the downloaded tiles |
| `split_dins.py` | split the CAL FIRE DINS points into one GeoJSON per fire |
| `fetch_ms_buildings.py` | **Microsoft building footprints** per fire (recommended source) |
| `hybrid_footprints.py` | refine MS footprints with SAM box-prompts on NAIP (sam-env) |
| `regularize_footprints.py` | square footprints to clean rectangles (arcpy) |
| `run_hybrid.ps1` | one command: MS -> SAM refine -> regularize -> DINS join |
| `extract_footprints.py` | deep-learning building footprints from pre-fire clips (arcpy) |
| `export_training_data.py` | export NAIP+label chips for fine-tuning (arcpy) |
| `train_footprint_model.py` | fine-tune a NAIP-specific Mask R-CNN (arcgis.learn) |
| `join_dins_to_footprints.py` | join DINS damage onto the footprints → per-fire buildings |
| `fetch_overture_prefire.py` | **pull true pre-fire Overture footprints** from the Fused archive (date-accurate snapshots Overture's own S3 no longer keeps) |
| `assess_footprint_readiness.py` | **rank fires by footprint readiness** — tiered pre-fire vs. latest DINS match per fire, so you know which need the least manual work (uses `fetch_overture_prefire.py`) |
| `run_footprints.ps1` | one command that runs extract + join across both envs |

## One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

This clones the ArcGIS Python into a user-writable env at
`C:\Users\shoang12\fire-naip-env`, installs `earthengine-api`, `geemap`,
`geedim`, and `gdal`/`rasterio`, and runs Google Earth Engine authentication.
Afterwards, put your Cloud project id in `EE_PROJECT` inside
`naip_prepost_fire.py`.

Run any script with that env's Python, using the **full path** to the script
(so it works no matter which folder your PowerShell is in):

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\<script>.py"
```

---

## Step-by-step workflow

### Step 1 — Build the availability table

> **Already done — you can skip this step.** The availability table has already
> been generated for this study. The results live in the **"NAIP Availability"**
> spreadsheet in the **SSDD SharePoint**, which lists, for every fire, the pre-
> and post-fire NAIP year and acquisition date range — everything you need to
> pull the tiles from EarthExplorer (Step 3). Only re-run the command below if
> you add new fires or want to regenerate the table.

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\naip_prepost_fire.py"
```

With `MANIFEST_ONLY = True` this only writes `NAIP_fire_availability.csv` (one
row per fire) — it does **not** download imagery. Columns:

| Field | Meaning |
|-------|---------|
| `NAIP_PreFire_Available` / `NAIP_PostFire_Available` | yes / no |
| `NAIP_PreFire_Year` / `NAIP_PostFire_Year` | the NAIP campaign year to download |
| `NAIP_PreFire_DateRange` / `NAIP_PostFire_DateRange` | acquisition-date **span** of that year's tiles |
| `Pre_to_Post_Year_Gap` | years between the pre and post flights |

This spreadsheet is your reference for **which years to enter in EarthExplorer**.
The `DateRange` is the span across which the fire's tiles were flown (NAIP
covers a region over many days) — it's *not* a search window to narrow to. Set
EarthExplorer to the **whole year**; the range is just so you know when the
imagery was captured.

### Step 2 — Make the per-fire AOIs

> **Already done — you can skip this step.** The per-fire AOI zips have already
> been generated and live in the **NAIP folder in the SSDD SharePoint**. Just
> grab the `<FIRE>_<year>.zip` you need and upload it to EarthExplorer in
> Step 3. Only re-run the command below if you add new fires.

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\make_fire_aois.py"
```

Writes `Downloads\CA_fire_AOIs\<FIRE>_<year>.zip` — one zipped, upload-ready
shapefile per fire (named with the fire's **ignition year**, so the two
`CREEK`/`VALLEY` fires stay distinct).

### Step 3 — Download the NAIP tiles from EarthExplorer (manual)

For **each fire**, and **once for pre + once for post**:

1. Go to **https://earthexplorer.usgs.gov** and log in.
2. **Search Criteria → Shapefile tab → upload** `CA_fire_AOIs\<FIRE>_<year>.zip`.
3. **Date Range** → set it to that fire's year from the availability CSV
   (e.g. pre = `01/01/2020`–`12/31/2020`, then post = `01/01/2022`–`12/31/2022`).
4. **Data Sets → Aerial Imagery → NAIP**.
5. **Results** → add **every** returned tile to **Bulk Download**
   (the 📦 icon), then run the **Bulk Download** — download **all** tiles.
   A large fire needs many DOQQ tiles; a partial set gives a partial clip.

> Tip: to know exactly how many tiles a fire needs (and their IDs), query Earth
> Engine for the fire — `USDA/NAIP/DOQQ` filtered to the perimeter and year
> returns the precise tile list, so your download is never short a tile.

### Step 4 — Organize the tiles

Create one folder per fire+period under `Downloads\NAIP_TILES\`, named
`<FIRE>_<year>_pre` / `<FIRE>_<year>_post` (the `<FIRE>_<year>` part must match
the AOI zip name so the script finds the perimeter):

```
NAIP_TILES\
    ZOGG_2020_pre\    <- the 2020 tiles for Zogg
    ZOGG_2020_post\   <- the 2022 tiles for Zogg
    BOBCAT_2020_post\ ...
```

The actual `.tif`/`.jp2` files must sit **directly** in the folder — not still
inside a `.ZIP`. To unzip a folder of EarthExplorer archives:

```powershell
$f = "C:\Users\shoang12\Downloads\NAIP_TILES\ZOGG_2020_post"
Get-ChildItem $f -Filter *.zip | ForEach-Object { Expand-Archive $_.FullName $f -Force; Remove-Item $_.FullName }
```

### Step 4.5 — Verify the folders are complete (recommended)

Partial downloads are the #1 cause of a bad clip (a folder short a few tiles
produces a mostly-empty raster). Check every folder against what Earth Engine
says the fire needs:

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\check_tiles.py"
```

It prints `have / need` per folder, lists any **missing** tile IDs to download,
flags **extra** tiles that aren't part of the fire, and writes
`Downloads\NAIP_tile_check.csv`. Fix any `MISSING` folders before clipping.

### Step 5 — Merge + clip

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\clip_fire_raster.py"
```

Outputs land in `OneDrive - Cal Poly\SSDD\NAIP_clipped\<FIRE>_<year>_pre_clip.tif`
(and `_post_clip.tif`). Re-running skips fires already clipped, so you can add
fires and re-run freely.

---

## How `clip_fire_raster.py` works

For every `<FIRE>_<year>[_pre|_post]` subfolder of `NAIP_TILES`, in a single
`gdal.Warp` pass (streamed to disk, so file size isn't limited by RAM):

1. **Match the perimeter** — the folder's `<FIRE>_<year>` key is matched to the
   fire in the perimeter shapefile (a `_pre`/`_post` suffix still matches).
2. **Mosaic** all the tiles in the folder.
3. **Reproject** to the fire's native **NAD83 / UTM** zone (derived from the
   perimeter centroid), at 0.6 m. Tiles already in that UTM zone are copied
   nearest-neighbor (no resampling/blur); off-projection tiles (e.g. NAIP
   JPEG2000 delivered in Web Mercator) are cubic-resampled. This guarantees the
   pre and post rasters share the same CRS, resolution, and pixel grid — so they
   overlay exactly for change detection.
4. **Clip** to the perimeter (`cropToCutline`), writing a compressed BigTIFF.

Fires already clipped are skipped unless `OVERWRITE = True`; a failing fire is
reported and the batch continues; partial outputs are removed on failure.

### Config (top of the file)

| Setting | Meaning |
|---------|---------|
| `TILES_ROOT` | parent folder holding the per-fire tile subfolders |
| `PERIM_PATH` | the fire-perimeter shapefile (buffered perimeters) |
| `OUT_DIR` | where the clipped GeoTIFFs are written |
| `OUT_RES` | output pixel size in metres (0.6 = native 60 cm) |
| `OVERWRITE` | `False` = resume (skip done); `True` = re-clip everything |

---

## Building footprints + DINS damage

Produces per-fire **building footprints tagged with DINS damage** — the input to
the SSDD analysis. Runs only for fires that have DINS.

### Two footprint sources

| Source | Script | Notes |
|--------|--------|-------|
| **Microsoft Building Footprints** (recommended) | `fetch_ms_buildings.py` | free vector footprints, no GPU, ~1–2 min/fire |
| Deep learning on pre-fire NAIP | `extract_footprints.py` | Esri Mask R-CNN; only where existing footprints are absent |

On a rural test fire (Zogg) MS matched **74%** of DINS structures with cleaner
geometry, vs **47%** for the generic DL model — and ~30× faster. Prefer MS
unless you need footprints at the exact pre-fire date somewhere MS doesn't cover
(then DL, ideally fine-tuned on LARIAC). Both write
`footprints\<FIRE>_<year>_pre_footprints.shp`, then the same join runs.

### Microsoft footprints (recommended)

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\fetch_ms_buildings.py"
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\join_dins_to_footprints.py"
```

`fetch_ms_buildings.py` finds the level-9 quadkeys covering each fire, downloads
Microsoft's tiles (cached in `Downloads\ms_buildings_cache`), clips to the
perimeter, and reprojects to the fire's UTM zone. Both steps run in the
`fire-naip` env — no arcpy, no GPU.

### Hybrid: refine Microsoft footprints with SAM on NAIP

Takes the discrete MS footprints and re-traces each boundary to the
**date-accurate NAIP** rooftop using SAM, prompted by **one box per MS building**
— so it keeps MS's one-polygon-per-building discreteness (no merging /
over-segmentation) while sharpening boundaries. Needs the `sam-env` (built via
`pip install segment-geospatial` + CUDA torch in a **separate** env from
`fire-naip`).

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\shoang12\SSDD\naip-fire-imagery\run_hybrid.ps1"
```

Runs: MS fetch → `hybrid_footprints.py` (tiles the clip, SAM-refines each MS
footprint on GPU) → `regularize_footprints.py` (squares the jagged SAM masks to
clean right-angled rectangles, like MS) → DINS join → `buildings_hybrid\`. On
Zogg it matched MS's 749 discrete buildings with slightly higher DINS recall
(75% vs 74%); after regularizing, footprint rectangularity matches MS (~0.86).
Proving it *beats* MS needs LARIAC ground truth (see below).

### Fine-tuning a NAIP-specific model (to beat Microsoft)

The generic Esri model underperforms MS on rural NAIP (~47% vs ~74% DINS match)
because it isn't tuned to NAIP and ignores the **NIR band**. A model **fine-tuned
on NAIP** can exceed MS: NIR cleanly separates rooftops from vegetation (MS is
RGB-only), and NAIP is date-accurate to the pre-fire flight. Run in the **base**
env:

```powershell
# 1. export image+label chips (needs building labels: LARIAC / hand-digitized / MS)
& "...\arcgispro-py3\python.exe" "...\naip-fire-imagery\export_training_data.py"
# 2. fine-tune Mask R-CNN from Esri's pretrained weights (GPU, hours)
& "...\arcgispro-py3\python.exe" "...\naip-fire-imagery\train_footprint_model.py"
```

Then point `MODEL` in `extract_footprints.py` at the saved `.dlpk` and run it on
all fires. **Labels matter:** to *beat* MS you need better-than-MS labels
(LARIAC for LA fires, or a modest hand-digitized set spanning urban + rural);
training on MS footprints only reaches ~MS quality. This is a one-time,
GPU-heavy training investment that then runs automatically.

### Deep-learning alternative — two environments (important)

`arcpy` and `geopandas`/`gdal` **cannot share one process** — importing GDAL-based
libraries breaks arcpy's native DLLs. So the two stages use two interpreters:

| Stage | Script | Interpreter |
|-------|--------|-------------|
| Deep-learning footprints | `extract_footprints.py` | **base** `arcgispro-py3` (arcpy + torch) |
| DINS damage join | `join_dins_to_footprints.py` | **`fire-naip`** (geopandas) |

### One-time model download

Download Esri's **"Building Footprint Extraction – USA"** deep learning package
(`.dlpk`) from ArcGIS Living Atlas and point `MODEL` (in `extract_footprints.py`)
at it. It's a Mask R-CNN; its `.emd` sets `ExtractBands:[0,1,2]`, so it uses the
clip's **RGB** bands and ignores NIR automatically.

### Prep the DINS points (once)

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\split_dins.py"
```

Splits the CAL FIRE DINS layer into `Downloads\dins_by_fire\<FIRE>_<year>.geojson`.
The default `METHOD="hybrid"` gates points by incident **name** (with an alias map
for complex roll-ups like Hennessey/Walbridge → "LNU", Castle → "SQF") and then
clips by **geometry** — so a neighbouring same-year fire's points never bleed into
a fire that has no DINS of its own.

### Run the footprint pipeline

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\shoang12\SSDD\naip-fire-imagery\run_footprints.ps1"
```

This runs, in order:
1. **`extract_footprints.py`** — for each `*_pre_clip.tif` **that has DINS**, runs
   the model on the GPU (`Detect Objects Using Deep Learning`) and regularizes the
   shapes → `footprints\<FIRE>_<year>_pre_footprints.shp`.
2. **`join_dins_to_footprints.py`** — assigns each DINS point to the nearest
   footprint (≤ `TOLERANCE` m, most-severe damage wins) and writes
   `buildings\<FIRE>_<year>_buildings.gpkg` (layer `buildings_raw`) carrying
   `DAMAGE` / `STRUCTURETYPE`.

Fires already done are skipped, so you can extract in batches. **Heads-up:** DL
inference is heavy — small clips (~3 GB) take ~30–60 min on GPU, big ones
(8–11 GB) several hours; the full set is an overnight run.

### Accuracy note

The pretrained model is generic. For the accuracy ceiling, **fine-tune on
LARIAC** (the LA-County fires have both pre-fire NAIP and authoritative LARIAC
footprints — ideal training labels) and re-run. Tune `THRESHOLD` for the
precision/recall trade-off in the meantime.

---

## Notes & gotchas

- **Download *all* tiles** for a fire — a partial folder produces a clip that
  only covers part of the perimeter.
- **Folder names must match** `<FIRE>_<year>` (the AOI/perimeter key) plus an
  optional `_pre`/`_post`, or the script reports "no matching perimeter."
- **Very large clips** (multi-GB) may appear blank in QGIS until you **build
  pyramids/overviews**, or if the canvas is zoomed elsewhere (use *Zoom to
  Layer*).
- The output raster is 4-band **R, G, B, NIR**; view natural color as bands
  1-2-3.

## Requirements

- ArcGIS Pro Python (provides `geopandas`, `rasterio`, `gdal`)
- `earthengine-api`, `geemap`, `geedim` (installed by `setup.ps1`) in the `fire-naip` env
- A Google Earth Engine account with a registered Cloud project
- A USGS EarthExplorer (ERS) account for downloading the tiles
- For the footprint step: ArcGIS Pro with the **Image Analyst** (and 3D Analyst
  for regularize) extensions, the deep-learning libraries in the **base**
  `arcgispro-py3` env, a CUDA GPU, and the Building Footprint `.dlpk`
- CAL FIRE DINS point layer (public) for the damage join
