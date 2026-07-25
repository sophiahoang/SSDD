# NAIP Pre-/Post-Fire Imagery + Pre-Fire Footprints

Tooling to assemble, for each wildfire in a study:

- **A · Imagery** — high-resolution **NAIP aerial imagery** (60 cm where
  available) from *before* and *after* the fire, clipped to the fire perimeter.
- **B · Buildings** — **date-accurate pre-fire building footprints**, tagged with
  **CAL FIRE DINS** damage data (which structures were destroyed / damaged).

The building footprints are the hand-off to the **SSDD** analysis in the parent
folder (`../SSDD.ipynb`).

> **What worked vs. what we tried:** the footprint approach that panned out is
> **versioned pre-fire Overture** (`fetch_overture_prefire.py`). Earlier attempts
> — Microsoft footprints, a SAM hybrid, and deep-learning extraction — are kept
> for reference in [`archive/`](archive/README.md) with a note on why each was
> set aside. You don't need them.

---

### Which scripts do I actually run?

You don't run all of them — pick the goal:

| I want… | Run (in order) |
|---------|----------------|
| **Imagery for a fire** | `naip_prepost_fire.py` → `make_fire_aois.py` → *(download tiles from EarthExplorer by hand)* → `check_tiles.py` → `clip_fire_raster.py` |
| **Damage points per fire** | `split_dins.py` |
| **See which fires have good footprint data** | `assess_footprint_readiness.py` |
| **Pre-fire footprints for a fire** | `fetch_overture_prefire.py` → `join_dins_to_footprints.py` |

---

## Part A — NAIP imagery

The imagery itself is downloaded by hand from **USGS EarthExplorer** (that's
where the full-quality original tiles live). The scripts do everything around
that: figure out *which* NAIP years each fire needs, hand you a ready-to-upload
search area per fire, and — once you've downloaded the tiles — mosaic,
reproject, and clip them to the perimeter automatically.

```
                                             ┌── you do this by hand ──┐
 fire perimeters        availability CSV      EarthExplorer download      clipped rasters
 (shapefile)   ──▶  +   AOI zips per fire ──▶ (upload AOI, enter dates, ──▶ per fire, pre & post
                        (the scripts)          bulk-download tiles)         (the script)
```

### Why the dates matter

NAIP is flown roughly **every 2 years**, in summer only, so "pre" and "post"
are the nearest flights, not the days around the fire. Also, **60 cm imagery
only exists for recent years** — in California ~2018 onward is 60 cm, earlier
years are 1 m, and the oldest (≈2009 and before) can be 1–2 m. The availability
CSV reports the exact year/date chosen so you know what resolution to expect.

### Step 1 — Build the availability table

> **Already done — you can skip this step.** The results live in the **"NAIP
> Availability"** spreadsheet in the **SSDD SharePoint**. Only re-run if you add
> new fires.

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\naip_prepost_fire.py"
```

With `MANIFEST_ONLY = True` this writes `NAIP_fire_availability.csv` (one row per
fire) — it does **not** download imagery. Columns:

| Field | Meaning |
|-------|---------|
| `NAIP_PreFire_Available` / `NAIP_PostFire_Available` | yes / no |
| `NAIP_PreFire_Year` / `NAIP_PostFire_Year` | the NAIP campaign year to download |
| `NAIP_PreFire_DateRange` / `NAIP_PostFire_DateRange` | acquisition-date **span** of that year's tiles |
| `Pre_to_Post_Year_Gap` | years between the pre and post flights |

Set EarthExplorer to the **whole year**; the `DateRange` is just so you know when
the imagery was captured, not a search window to narrow to.

### Step 2 — Make the per-fire AOIs

> **Already done — you can skip this step.** The zips live in the **NAIP folder
> in the SSDD SharePoint**. Only re-run if you add new fires.

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
5. **Results** → add **every** returned tile to **Bulk Download** (the 📦 icon),
   then run the **Bulk Download** — download **all** tiles. A large fire needs
   many DOQQ tiles; a partial set gives a partial clip.

> Tip: to know exactly how many tiles a fire needs, query Earth Engine —
> `USDA/NAIP/DOQQ` filtered to the perimeter and year returns the precise tile
> list, so your download is never short a tile.

### Step 4 — Organize the tiles

One folder per fire+period under `Downloads\NAIP_TILES\`, named
`<FIRE>_<year>_pre` / `<FIRE>_<year>_post` (the `<FIRE>_<year>` part must match
the AOI zip name so the script finds the perimeter):

```
NAIP_TILES\
    ZOGG_2020_pre\    <- the 2020 tiles for Zogg
    ZOGG_2020_post\   <- the 2022 tiles for Zogg
    BOBCAT_2020_post\ ...
```

The `.tif`/`.jp2` files must sit **directly** in the folder — not inside a `.ZIP`.
To unzip a folder of EarthExplorer archives:

```powershell
$f = "C:\Users\shoang12\Downloads\NAIP_TILES\ZOGG_2020_post"
Get-ChildItem $f -Filter *.zip | ForEach-Object { Expand-Archive $_.FullName $f -Force; Remove-Item $_.FullName }
```

### Step 4.5 — Verify the folders are complete (recommended)

Partial downloads are the #1 cause of a bad clip. Check every folder against what
Earth Engine says the fire needs:

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\check_tiles.py"
```

It prints `have / need` per folder, lists any **missing** tile IDs, flags
**extra** tiles, and writes `Downloads\NAIP_tile_check.csv`. Fix `MISSING`
folders before clipping.

### Step 5 — Merge + clip

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\clip_fire_raster.py"
```

Outputs land in `OneDrive - Cal Poly\SSDD\NAIP_clipped\<FIRE>_<year>_pre_clip.tif`
(and `_post_clip.tif`). Re-running skips fires already clipped.

For every `<FIRE>_<year>[_pre|_post]` subfolder, in a single `gdal.Warp` pass
(streamed to disk, so file size isn't limited by RAM), it **matches the
perimeter**, **mosaics** the tiles, **reprojects** to the fire's native
**NAD83 / UTM** zone at 0.6 m (so pre and post share an exact pixel grid for
change detection), and **clips** to the perimeter as a compressed BigTIFF. A
failing fire is reported and the batch continues.

| Config (top of file) | Meaning |
|---------|---------|
| `TILES_ROOT` | parent folder holding the per-fire tile subfolders |
| `PERIM_PATH` | the fire-perimeter shapefile (buffered perimeters) |
| `OUT_DIR` | where the clipped GeoTIFFs are written |
| `OUT_RES` | output pixel size in metres (0.6 = native 60 cm) |
| `OVERWRITE` | `False` = resume (skip done); `True` = re-clip everything |

---

## Part B — Pre-fire footprints + DINS damage

Produces per-fire **building footprints tagged with DINS damage** — the input to
the SSDD analysis. Runs for fires that have DINS.

### Step 1 — Prep the DINS points (once)

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\split_dins.py"
```

Splits the CAL FIRE DINS layer into `Downloads\dins_by_fire\<FIRE>_<year>.geojson`.
The default `METHOD="hybrid"` gates points by incident **name** (with an alias map
for complex roll-ups like Hennessey/Walbridge → "LNU", Castle → "SQF") and then
clips by **geometry**, so a neighbouring same-year fire's points never bleed into
a fire that has no DINS of its own.

### Step 2 — Check which fires are ready

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\assess_footprint_readiness.py"
```

Scores every DINS fire and writes `Downloads\footprint_readiness_scorecard.csv`.
For each fire it reports what share of the damaged structures already have a
building footprint, and — crucially — **which source to use**, because that
depends on the fire's date:

| `recommended` | When | What it means |
|---------------|------|---------------|
| **`pre-fire`** | Fire is recent enough (~2024+) that a versioned Overture release lands within ~3 weeks before it | Use `fetch_overture_prefire.py` — genuinely date-accurate. |
| **`latest+NAIP`** | Fire is 2024+ but the only pre-fire release is stale (Overture archive has a 2024-03→2024-08 gap) | Current Overture is more complete; verify against NAIP. |
| **`latest / NSI+NAIP`** | Fire predates Overture (before ~2024-02) | No pre-fire Overture exists — filter current buildings by NSI year-built, or digitize from NAIP. |

The `recovered_delta` column (pre-fire % minus latest %) flags fires where
destruction dropped buildings from current data — e.g. **Palisades +8pts**, the
clearest case for using pre-fire data.

### Step 3 — Pull the pre-fire footprints

For the fires the scorecard marks **`pre-fire`**:

```powershell
# all eligible fires, or name specific ones:
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\fetch_overture_prefire.py"
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\fetch_overture_prefire.py" MOUNTAIN AIRPORT
```

For each fire it auto-picks the latest Overture release **before** the fire's
`ALARM_DATE`, pulls the buildings from the **Fused archive** on source.coop
(`data.source.coop/fused/overture/…` — which keeps the historical releases
Overture's own S3 purges), clips to the perimeter, and writes
`footprints_prefire\<FIRE>_<year>_prefire_footprints.gpkg`.

It queries with DuckDB filtered by the fire bbox and selects geometry only —
which sidesteps the two problems people hit going through Fused's UDF runtime:
no server-side **tiling** (so no half-perimeter), and no nested list/struct
columns (so no *"data type &lt;list&gt; not understood"*).

### Step 4 — Join DINS damage

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\join_dins_to_footprints.py"
```

Assigns each DINS point to the nearest footprint (≤ `TOLERANCE` m, most-severe
damage wins) and writes `buildings\<FIRE>_<year>_buildings.gpkg` (layer
`buildings_raw`) carrying `DAMAGE` / `STRUCTURETYPE`. Set `FOOT_DIR` to the
`footprints_prefire` folder from Step 3.

---

## Files

| File | Purpose |
|------|---------|
| `setup.ps1` | one-time environment setup (clone Python env, install packages, GEE auth) |
| `naip_prepost_fire.py` | build the NAIP availability CSV (which year per fire, pre & post) |
| `make_fire_aois.py` | split fires into per-fire AOI zips for EarthExplorer |
| `check_tiles.py` | **verify each tile folder is complete** (have vs. need) before clipping |
| `clip_fire_raster.py` | **mosaic + reproject-to-UTM + clip** the downloaded tiles |
| `split_dins.py` | split the CAL FIRE DINS points into one GeoJSON per fire |
| `assess_footprint_readiness.py` | **rank fires by footprint readiness** — tiered pre-fire vs. latest DINS match, so you know which fires are ready and which source to use |
| `fetch_overture_prefire.py` | **pull date-accurate pre-fire Overture footprints** from the Fused archive |
| `join_dins_to_footprints.py` | join DINS damage onto the footprints → per-fire buildings |
| [`archive/`](archive/README.md) | superseded footprint approaches (Microsoft, SAM hybrid, deep-learning) — kept for reference |

---

## One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Clones the ArcGIS Python into a user-writable env at
`C:\Users\shoang12\fire-naip-env`, installs `earthengine-api`, `geemap`,
`geedim`, `gdal`/`rasterio`, `duckdb`, and `overturemaps`, and runs Google Earth
Engine authentication. Put your Cloud project id in `EE_PROJECT` inside
`naip_prepost_fire.py`.

Run any script with that env's Python, using the **full path** to the script:

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" "C:\Users\shoang12\SSDD\naip-fire-imagery\<script>.py"
```

---

## Notes & gotchas

- **Download *all* tiles** for a fire — a partial folder produces a clip that
  only covers part of the perimeter.
- **Folder names must match** `<FIRE>_<year>` (the AOI/perimeter key) plus an
  optional `_pre`/`_post`, or the script reports "no matching perimeter."
- **Very large clips** may appear blank in QGIS until you **build
  pyramids/overviews**, or if the canvas is zoomed elsewhere (use *Zoom to
  Layer*).
- The output raster is 4-band **R, G, B, NIR**; view natural color as bands 1-2-3.
- **Pre-fire Overture only reaches back to ~2024-02** (the archive's earliest
  buildings release), so older fires have no pre-fire snapshot — the scorecard
  marks those `NSI+NAIP`.

## Requirements

- ArcGIS Pro Python (provides `geopandas`, `rasterio`, `gdal`) cloned to the
  `fire-naip` env by `setup.ps1`
- `earthengine-api`, `geemap`, `geedim` — for the imagery step
- `duckdb`, `overturemaps` — for the pre-fire footprint step
- A Google Earth Engine account with a registered Cloud project
- A USGS EarthExplorer (ERS) account for downloading the tiles
- CAL FIRE DINS point layer (public) for the damage join
