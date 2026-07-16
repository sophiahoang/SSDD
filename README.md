# SSDD — Structure Separation Distance & Density

This project measures **how densely packed and how separated buildings are** in a
neighborhood — a factor in how easily a wildfire can spread from structure to
structure. Given a set of **building footprints** (the outlines of buildings), it
gives every building a score describing its surroundings.

It has two halves:

1. **Get the building footprints** for a wildfire study area (with before/after
   aerial imagery and official damage data) — the `naip-fire-imagery/` pipeline.
2. **Score those footprints** with the SSDD metric — the `SSDD.ipynb` notebook.

---

## What the SSDD score means (plain English)

Each building gets a 0–1 score built from two ideas:

- **Structure Density (SD)** — *how much building is around me?* Counts nearby
  buildings and how much of the surrounding area is covered by rooftops.
- **Structure Separation (SS)** — *how close and similar are my neighbors?* Looks
  at the gap to nearby buildings and whether they face the same direction.

These blend into the final **SSDD** score. It's a research metric for studying
wildfire spread risk between structures — dense, tightly-spaced neighborhoods sit
at one end, spread-out rural ones at the other.

---

## What's in this repo

| Path | What it is |
|------|-----------|
| `SSDD.ipynb` | The analysis notebook — reads building footprints and computes the SSDD score per building. |
| `naip-fire-imagery/` | A pipeline that produces the building footprints (+ pre/post-fire NAIP imagery + CAL FIRE damage points) for wildfires. Has its own README. |
| `output/` | Example results — SSDD scores for a San Luis Obispo sample, at several settings. |

---

## How to use it

**If you already have building footprints and just want the SSDD score:**
open `SSDD.ipynb`, set `INPUT_PATH` (top cell) to your footprint file (Shapefile,
GeoPackage, or GeoJSON), and run the cells top to bottom. It writes scored
GeoPackages + a CSV to your `output/` folder.

**If you need building footprints for a wildfire first:**
start in **[`naip-fire-imagery/`](naip-fire-imagery/README.md)** — that pipeline
downloads the imagery, extracts footprints, and attaches damage data. Its output
(a footprint layer per fire) is exactly what `SSDD.ipynb` takes as input.

So the normal flow is: **`naip-fire-imagery/` → footprints → `SSDD.ipynb` → scores.**

---

## Requirements

- Python with `geopandas`, `numpy`, `pandas`, `matplotlib`, `shapely`, `tqdm`
  (for the notebook). The imagery pipeline has its own setup — see its README.
- Footprints are analyzed in **NAD83 / California Albers (EPSG:3310)**; the
  notebook reprojects for you.
