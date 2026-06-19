# =====================================================================
# setup.ps1 -- one-time environment setup for naip_prepost_fire.py
#
# Clones the ArcGIS Pro conda env, installs the packages the script
# needs, then kicks off Earth Engine authentication.
#
# Run this ONCE. In a PowerShell window:
#     cd C:\Users\shoang12
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
# =====================================================================

$ErrorActionPreference = "Stop"

$conda   = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe"
$envName = "fire-naip"
$envPath = "C:\Program Files\ArcGIS\Pro\bin\Python\envs\$envName"
$py      = "$envPath\python.exe"
$pip     = "$envPath\Scripts\pip.exe"

Write-Host "`n=== Step 1/3: clone the ArcGIS Python environment ===" -ForegroundColor Cyan
if (Test-Path $py) {
    Write-Host "Env '$envName' already exists -- skipping clone." -ForegroundColor Yellow
} else {
    & $conda create --clone arcgispro-py3 --name $envName --yes
}

Write-Host "`n=== Step 2/3: install earthengine-api + geemap ===" -ForegroundColor Cyan
& $pip install --upgrade earthengine-api geemap

Write-Host "`n=== Step 3/3: authenticate with Google Earth Engine ===" -ForegroundColor Cyan
Write-Host "A browser window will open. Log in with the Google account"
Write-Host "that has Earth Engine access, then paste the token back here."
& $py -c "import ee; ee.Authenticate()"

Write-Host "`nDONE." -ForegroundColor Green
Write-Host "Interpreter to select in VS Code:" -ForegroundColor Green
Write-Host "    $py"
Write-Host "Next: put your Cloud project id in EE_PROJECT inside naip_prepost_fire.py,"
Write-Host "then run it."
