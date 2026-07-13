"""
Step 2 of footprint fine-tuning: train a Mask R-CNN on the exported NAIP chips,
starting from Esri's pretrained "Building Footprint Extraction - USA" weights.

Produces a .dlpk you then plug into extract_footprints.py (set MODEL) to run the
fine-tuned model across all fires -- automatically.

Run with the BASE ArcGIS env (arcgis.learn + torch + GPU):
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" train_footprint_model.py
"""
from arcgis.learn import prepare_data, MaskRCNN

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DATA_FOLDER = r"C:\Users\shoang12\Downloads\footprint_training\chips"   # from export step
PRETRAINED  = r"C:\Users\shoang12\Downloads\usa_building_footprints.dlpk"  # fine-tune FROM this
OUT_NAME    = "naip_footprint_ft"
CHIP        = 512
BATCH       = 4          # drop to 2 if the GPU runs out of memory
EPOCHS      = 20
VAL_SPLIT   = 0.15       # held-out validation fraction
# ---------------------------------------------------------------------------


def main():
    print("preparing data...")
    data = prepare_data(DATA_FOLDER, chip_size=CHIP, batch_size=BATCH,
                        val_split_pct=VAL_SPLIT, dataset_type="RCNN_Masks")
    print(data)

    # Fine-tune from Esri's pretrained weights (falls back to a fresh backbone
    # if the .dlpk can't be loaded as a starting point).
    try:
        model = MaskRCNN(data, pretrained_path=PRETRAINED)
        print("initialized from pretrained:", PRETRAINED)
    except Exception as e:
        print("pretrained init failed, training from backbone instead:", e)
        model = MaskRCNN(data)

    lr = model.lr_find()
    print("suggested lr:", lr)
    model.fit(EPOCHS, lr)

    try:
        print("validation average precision:", model.average_precision_score())
    except Exception as e:
        print("AP score skipped:", e)

    model.save(OUT_NAME, framework="PyTorch")
    print(f"\nSaved fine-tuned model '{OUT_NAME}' under {DATA_FOLDER}\\models\\")
    print("Point MODEL in extract_footprints.py at that .dlpk to run it on all fires.")


if __name__ == "__main__":
    main()
