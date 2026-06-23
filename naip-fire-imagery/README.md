# NAIP Pre-/Post-Fire Imagery

Python tooling to pull **NAIP aerial imagery** before and after wildfires,
using a fire-perimeter shapefile and Google Earth Engine (GEE).

For each fire it finds the nearest NAIP acquisition *before* ignition
(pre-fire) and *after* containment (post-fire), records availability and
acquisition dates to a CSV, and (optionally) exports a GeoTIFF clipped to
each fire perimeter.

## Why the dates matter

NAIP is flown roughly **every 2 years**, in summer only. So "pre" and "post"
are the nearest available flights, not the days around the fire. The
availability table reports the exact acquisition date and the pre→post year
gap so you can judge how much regrowth each post-fire image may include.

## Files

| File | Purpose |
|------|---------|
| `naip_prepost_fire.py` | main script (build availability CSV + export GeoTIFFs) |
| `setup.ps1` | one-time env setup: clone ArcGIS Python, install packages, GEE auth |

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Then open `naip_prepost_fire.py` and set:
- `EE_PROJECT` — your Google Cloud / Earth Engine project id
- `INPUT_PATH` — path to your fire-perimeter shapefile
- `STATE_FILTER` — e.g. `["CA"]`, or `None` for all fires

## Run

```powershell
& "C:\Users\shoang12\fire-naip-env\python.exe" naip_prepost_fire.py
```

- `MANIFEST_ONLY = True` (default): writes the availability CSV only — fast.
- `MANIFEST_ONLY = False`: also queues clipped GeoTIFF exports to Google Drive.

## Output

`NAIP_fire_availability.csv` — one row per fire:

| Field | Meaning |
|-------|---------|
| `NAIP_PreFire_Available` / `NAIP_PostFire_Available` | yes / no |
| `NAIP_PreFire_Date` / `NAIP_PostFire_Date` | exact acquisition date |
| `NAIP_PreFire_Year` / `NAIP_PostFire_Year` | campaign year |
| `Pre_to_Post_Year_Gap` | years between the two flights |

## Requirements

- ArcGIS Pro Python (provides `geopandas`)
- `earthengine-api`, `geemap` (installed by `setup.ps1`)
- A Google Earth Engine account with a registered Cloud project
