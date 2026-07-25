"""
Step 1 of footprint fine-tuning: export NAIP image chips + building-mask labels
for training a Mask R-CNN.

For each (4-band NAIP clip, building-footprint labels) pair it runs
`Export Training Data For Deep Learning` in "RCNN Masks" format (instance
segmentation), writing 512-px chips to OUT_FOLDER. Because the input is the
4-band clip, chips include NIR -- the signal a fine-tuned model can use to
separate rooftops from vegetation (an advantage MS's RGB footprints lack).

LABELS: use the best building footprints you can get for the training areas --
LARIAC (LA fires, precise) is ideal; hand-digitized tiles also work; Microsoft
footprints work but cap the model near MS quality. Mix urban + rural areas so
the model generalizes.

Run with the BASE ArcGIS env (arcpy):
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" export_training_data.py
"""
import os
import arcpy

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
OUT_FOLDER = r"C:\Users\shoang12\Downloads\footprint_training\chips"
TILE   = 512
STRIDE = 256
# (4-band NAIP clip, building-label polygons). Add more fires for a stronger model.
TRAIN_PAIRS = [
    (r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\NAIP_clipped\BOBCAT_2020_pre_clip.tif",
     r"C:\Users\shoang12\OneDrive - Cal Poly\SSDD\footprints\BOBCAT_2020_pre_footprints.shp"),
]
# ---------------------------------------------------------------------------

arcpy.CheckOutExtension("ImageAnalyst")
arcpy.env.overwriteOutput = True


def main():
    os.makedirs(OUT_FOLDER, exist_ok=True)
    for i, (raster, labels) in enumerate(TRAIN_PAIRS):
        print(f"[{i+1}/{len(TRAIN_PAIRS)}] exporting chips from {os.path.basename(raster)} ...")
        arcpy.ia.ExportTrainingDataForDeepLearning(
            in_raster=raster,
            out_folder=OUT_FOLDER,
            in_class_data=labels,
            image_chip_format="TIFF",
            tile_size_x=TILE, tile_size_y=TILE,
            stride_x=STRIDE, stride_y=STRIDE,
            output_nofeature_tiles="ONLY_TILES_WITH_FEATURES",
            metadata_format="RCNN Masks",
            reference_system="MAP_SPACE",
            processing_mode="PROCESS_AS_MOSAICKED_IMAGE",
        )
    print(f"\nDone -> {OUT_FOLDER}  (feed this to train_footprint_model.py)")


if __name__ == "__main__":
    main()
