# IRI Image Analyzer

Python tool for estimating ice-crystal actual contour area from sucrose IRI microscopy images.

## Important Notes

- CLAHE is not applied before background estimation by default.
- The default order is `gray -> protect mask -> background estimate from raw gray -> flat-field correction -> CLAHE -> segmentation`.
- HoughCircles and LoG are localization tools only; they do not define crystal area.
- `actual_area_px2` is measured from each final instance mask.
- `circle_area_px2` is only a reference field and is not used for total area.
- Without `pixel_size_um`, the tool reports area only in `px²`.
- The default method is intended for mostly round, separated ice crystals with reasonably sharp boundaries.
- Strongly touching, blurred, or highly non-circular crystals require manual QC or a learned segmentation route such as Cellpose.
- Inspect representative `10_final_overlay.png` and `11_label_overlay.png` files for every batch.

Do not treat automatic output as a final scientific conclusion. Reported areas are segmentation-derived estimates and must be checked against overlays.

## Installation

```bash
pip install -e .
```

## CLI Usage

```bash
python -m iri_analyzer.cli --input path/to/image.bmp --output output_dir --mode qc
python -m iri_analyzer.cli --input image_folder --output output_dir --mode batch
python -m iri_analyzer.cli --input image.bmp --output output_dir --mode sensitivity
```

Optional arguments:

```bash
python -m iri_analyzer.cli \
  --input image.bmp \
  --output output_dir \
  --mode qc \
  --config config.yaml \
  --pixel-size-um 0.5 \
  --exclude-edge-touching true \
  --overwrite
```

Each image gets its own folder under the output directory. Existing non-empty per-image folders are not overwritten unless `--overwrite` is supplied.

## Pipeline

1. Read bmp/png/jpg/tif image and save `00_original.png`.
2. Convert to grayscale and save `01_gray.png`.
3. Build a coarse edge protect mask from raw gray using median blur, Scharr gradient, percentile thresholding, and dilation. Save `02_protect_mask.png`.
4. Estimate background from raw gray using masked Gaussian normalized convolution:

```text
valid = 1 - protect_mask
background = GaussianBlur(gray * valid) / GaussianBlur(valid)
```

5. Apply flat-field correction:

```text
corrected = gray / background * median(background)
```

6. Save `03_background_estimate.png` and `04_flatfield_corrected.png`.
7. Apply light CLAHE after background correction and save `05_bg_corrected_clahe.png`.
8. Detect candidate crystals with HoughCircles by default, or LoG if configured. Save `06_candidate_localization_overlay.png` and `candidates.csv`.
9. For every candidate, perform radial contour refinement around the candidate center/radius, fill the polygon into an instance mask, handle overlaps, and save contour/mask overlays.
10. Measure actual area from the final instance mask and write `crystals.csv`, `summary.json`, and `qc_report.txt`.

CLAHE is not recommended before background estimation because it can amplify shadows, noise, and ice-crystal edges, causing pseudo-structure to leak into the background model.

## Output Files

Per image folder:

```text
00_original.png
01_gray.png
02_protect_mask.png
03_background_estimate.png
04_flatfield_corrected.png
05_bg_corrected_clahe.png
06_candidate_localization_overlay.png
07_contour_points_overlay.png
08_instance_masks.png
09_final_mask.png
10_final_overlay.png
11_label_overlay.png
12_area_histogram.png
candidates.csv
crystals.csv
summary.json
config_used.yaml
qc_report.txt
```

`candidates.csv` contains candidate centers and approximate radii only. These values are not area measurements.

`crystals.csv` contains one final instance per row. The primary result is `actual_area_px2`, measured as the nonzero pixel count in the final instance mask. If `pixel_size_um` is provided, `actual_area_um2` and `equivalent_diameter_um` are also written.

`summary.json` includes candidate counts, final instance counts, total actual area, equivalent diameter percentiles, area fraction, QC warning count, the full config, and errors.

`sensitivity.csv` is written in sensitivity mode and contains:

```text
background_sigma_px,hough_param2,radial_search_scale_max,
n_candidates,n_final_instances,total_actual_area_px2,
median_actual_area_px2,n_qc_warning
```

## Key Parameters

- `background_sigma_px`: scale of large-shadow background estimation. It should be larger than typical crystal diameter.
- `protect_gradient_percentile`: percentile threshold for coarse edge protection.
- `protect_dilation_px`: dilation radius for the protect mask.
- `clahe_clip_limit`, `clahe_tile_grid_size`: light post-correction contrast enhancement.
- `candidate_method`: `hough` or `log`.
- `min_radius_px`, `max_radius_px`: candidate radius bounds.
- `contour_n_angles`: number of radial search directions.
- `radial_search_min_scale`, `radial_search_max_scale`, `radial_search_extra_px`: radial boundary search window.
- `radial_peak_nearmax_fraction`: accepts a near-maximum gradient peak, lightly preferring the approximate candidate radius.
- `max_overlap_skip_fraction`: skip an instance if too much of its mask overlaps earlier instances.
- `max_overlap_qc_fraction`: flag a kept instance if trimmed overlap is large.
- `exclude_edge_touching`: exclude edge-touching candidates from final statistics.
- `pixel_size_um`: micrometers per pixel. If omitted, physical units are not reported.

## QC Guidance

Review these files before trusting quantitative output:

- `03_background_estimate.png`: should mainly show large-scale illumination/shadow.
- `04_flatfield_corrected.png`: should reduce irregular background.
- `06_candidate_localization_overlay.png`: candidates should cover visible crystals.
- `10_final_overlay.png`: final contours should follow crystal boundaries.
- `11_label_overlay.png`: labels should match `crystals.csv`.
- `qc_report.txt`: lists suspicious objects and skipped candidates.

Automatic QC flags include abnormal `area_over_circle`, large radial radius range, large overlap trimming, edge touching, too-small area, too-large area, and failed/low-quality radial contours.

## Validation

Run:

```bash
pytest
```

For a supplied test image, run:

```bash
python -m iri_analyzer.cli --input path/to/test_image.bmp --output output_dir --mode qc --overwrite
```

Then inspect the background, flat-field corrected image, candidate overlay, final overlay, `crystals.csv`, `summary.json`, and `qc_report.txt`.
