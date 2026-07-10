# =====================================================================
# run_footprints.ps1 -- one command for the pre-fire footprint pipeline.
#
# Runs the two stages in the two environments they each require:
#   1. extract_footprints.py  -> ArcGIS deep learning (arcpy)  -> BASE env
#   2. join_dins_to_footprints.py -> geopandas               -> fire-naip env
#
#   powershell -ExecutionPolicy Bypass -File .\run_footprints.ps1
# =====================================================================

# Interpreters (edit if your paths differ)
$ARCPY_PY = "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"  # arcpy + torch
$GEO_PY   = "C:\Users\shoang12\fire-naip-env\python.exe"                            # geopandas
$here     = $PSScriptRoot

Write-Host "== 1/2: extracting building footprints (ArcGIS DL, base env) ==" -ForegroundColor Cyan
& $ARCPY_PY "$here\extract_footprints.py"
if ($LASTEXITCODE -ne 0) { Write-Host "extract step failed" -ForegroundColor Red; exit 1 }

Write-Host "`n== 2/2: joining DINS damage (fire-naip env) ==" -ForegroundColor Cyan
& $GEO_PY "$here\join_dins_to_footprints.py"
if ($LASTEXITCODE -ne 0) { Write-Host "join step failed" -ForegroundColor Red; exit 1 }

Write-Host "`nDone. Per-fire building GeoPackages (footprints + DINS damage) written." -ForegroundColor Green
