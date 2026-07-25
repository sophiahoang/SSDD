# Archived — footprint approaches we tried and set aside

These scripts are **not part of the current pipeline.** They're earlier attempts
at getting pre-fire building footprints, kept for reference and reproducibility.
The production path is now **`fetch_overture_prefire.py`** (pre-fire Overture from
the Fused archive) in the parent folder — see the main
[README](../README.md). Here's what each of these was and why we moved on.

## The short version

We were trying to get **accurate, date-accurate pre-fire footprints** for the
fires that have CAL FIRE DINS damage data. We tried three things before landing
on versioned Overture:

| Approach | Scripts | Result | Why archived |
|----------|---------|--------|--------------|
| **Deep-learning extraction** on pre-fire NAIP | `extract_footprints.py`, `export_training_data.py`, `train_footprint_model.py` | ~47% DINS match on rural fires, jagged output | Generic Esri model isn't tuned to NAIP; only a fine-tune on real labels (LARIAC) would beat Microsoft, a heavy investment we didn't need. |
| **Microsoft Global ML footprints** | `fetch_ms_buildings.py` | ~74% (Zogg) / 47% (Bobcat) DINS match | Solid and fast, but **not date-accurate** — MS footprints have no fire-relative date, so they can include post-fire or miss pre-fire structures. Superseded by versioned Overture, which *is* dated. |
| **Hybrid: MS footprints refined with SAM on NAIP** | `hybrid_footprints.py`, `regularize_footprints.py`, `run_hybrid.ps1` | Discrete + tighter boundaries, recall capped at MS's | Recall can't exceed the MS footprints it starts from, and it needs a separate GPU `sam-env`. Lots of moving parts for a marginal gain. |

`run_footprints.ps1` is the old orchestrator that ran the deep-learning
extractor + DINS join; it's here because it drives archived scripts.

## Why versioned Overture won

The core problem with all of the above is **date accuracy**: DINS tells us which
structures burned, and to line those up we need footprints *as they existed
just before the fire*. Microsoft and a fresh ML extraction give you *a* set of
buildings, but not a **dated** one. Overture publishes **versioned** releases, so
we can pull the snapshot from right before each fire — and Fused archives the
historical releases that Overture's own S3 purges. See
[`fetch_overture_prefire.py`](../fetch_overture_prefire.py) and the readiness
scorecard [`assess_footprint_readiness.py`](../assess_footprint_readiness.py),
which quantifies, per fire, how much better (or worse) the true pre-fire snapshot
is than current data.

## Can I still run these?

Yes — they're unchanged and still work if you set up the environments they need
(the deep-learning scripts need the ArcGIS **base** `arcgispro-py3` env with the
deep-learning libraries + a CUDA GPU; the hybrid needs a separate `sam-env`).
But for pre-fire footprints, start with the production Overture path instead.
