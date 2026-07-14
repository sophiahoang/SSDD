# =====================================================================
# run_hybrid.ps1 -- hybrid footprint pipeline (Microsoft -> SAM refine -> DINS).
#
# Refines Microsoft footprints against the pre-fire NAIP with SAM box-prompts
# (discrete, date-accurate boundaries), then joins DINS damage.
#
#   powershell -ExecutionPolicy Bypass -File .\run_hybrid.ps1
# =====================================================================

$SAM   = "C:\Users\shoang12\sam-env\python.exe"                                   # SAM
$GEO   = "C:\Users\shoang12\fire-naip-env\python.exe"                             # geopandas
$ARCPY = "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"   # arcpy (regularize)
$here  = $PSScriptRoot
$env:FOOT_DIR = "C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints_hybrid"
$env:OUT_DIR  = "C:\Users\shoang12\OneDrive - Cal Poly\SSDD\buildings_hybrid"

Write-Host "== 1/4: Microsoft footprints (SAM prompts) ==" -ForegroundColor Cyan
& $GEO "$here\fetch_ms_buildings.py"          # skip if footprints/ already populated
if ($LASTEXITCODE -ne 0) { Write-Host "MS fetch failed" -ForegroundColor Red; exit 1 }

Write-Host "`n== 2/4: SAM box-prompt refinement on NAIP (GPU) ==" -ForegroundColor Cyan
& $SAM "$here\hybrid_footprints.py"
if ($LASTEXITCODE -ne 0) { Write-Host "SAM refine failed" -ForegroundColor Red; exit 1 }

Write-Host "`n== 3/4: regularize to clean rectangular footprints ==" -ForegroundColor Cyan
& $ARCPY "$here\regularize_footprints.py"     # squares SAM's jagged edges to right angles
if ($LASTEXITCODE -ne 0) { Write-Host "regularize failed" -ForegroundColor Red; exit 1 }

Write-Host "`n== 4/4: join DINS damage onto refined footprints ==" -ForegroundColor Cyan
& $GEO "$here\join_dins_to_footprints.py"
if ($LASTEXITCODE -ne 0) { Write-Host "DINS join failed" -ForegroundColor Red; exit 1 }

Write-Host "`nDone. Hybrid buildings (refined footprints + DINS) in buildings_hybrid\." -ForegroundColor Green
