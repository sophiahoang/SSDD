"""
Regularize footprints to clean right-angled building shapes (in place).

SAM-refined (hybrid) footprints trace rooftop pixels, so they come out jagged /
oblong. This squares them up with RegularizeBuildingFootprint (RIGHT_ANGLES) --
the same step the DL path uses -- so they look like the rectangular MS footprints
while keeping the SAM position/size.

Run with the BASE ArcGIS env (arcpy + 3D Analyst):
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" regularize_footprints.py
"""
import glob
import os
import arcpy

# ---------------------------------------------------------------------------
# CONFIG (FOOT_DIR overridable via env var, e.g. from run_hybrid.ps1)
# ---------------------------------------------------------------------------
FOOT_DIR  = os.environ.get("FOOT_DIR",
                           r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints_hybrid")
METHOD    = "RIGHT_ANGLES"   # keeps L-shapes but squares corners
TOLERANCE = 0.75             # metres
DENSIFY   = 0.75
# ---------------------------------------------------------------------------

arcpy.CheckOutExtension("3D")
arcpy.env.overwriteOutput = True


def main():
    shps = sorted(glob.glob(os.path.join(FOOT_DIR, "*_pre_footprints.shp")))
    print(f"regularizing {len(shps)} footprint layer(s) in {FOOT_DIR}")
    for shp in shps:
        tmp = os.path.join(arcpy.env.scratchGDB, "reg_tmp")
        arcpy.ddd.RegularizeBuildingFootprint(
            in_features=shp, out_feature_class=tmp, method=METHOD,
            tolerance=TOLERANCE, densification=DENSIFY,
        )
        arcpy.management.CopyFeatures(tmp, shp)   # overwrite in place
        print(f"  {os.path.basename(shp)}: {arcpy.management.GetCount(shp)[0]} regularized")
    print("done.")


if __name__ == "__main__":
    main()
