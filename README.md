# IRI Image Analyzer

Python tool for estimating ice-crystal actual contour area from sucrose IRI microscopy images.

## Important Notes

- CLAHE is not applied before background estimation by default.
- The default order is `gray -> protect mask -> background estimate from raw gray -> flat-field correction -> CLAHE -> segmentation`.
- HoughCircles and LoG are localization tools only; they do not define crystal area.
- `actual_area_px2` is measured from each final instance mask.
- `accepted_total_actual_area_px2` is the default summary value for downstream scientific analysis.
- `circle_area_px2` is only a reference field and is not used for total area.
- Without `pixel_size_um`, the tool reports area only in `px²`.
- The default round workflow is intended for mostly round, separated ice crystals with reasonably sharp boundaries.
- A gated square-like strategy can add contour candidates for square, rectangular, or polygonal crystals.
- Slight adhesion can be split by a conservative distance-transform branch; severe adhesion still requires manual QC or a learned segmentation route such as Cellpose.
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

## Web UI

Build the local frontend once:

```bash
cd web
npm install
npm run build
cd ..
```

Start the no-code local app:

```bash
python -m iri_analyzer.web
```

Open:

```text
http://127.0.0.1:8000
```

The Web UI supports batch image upload, preset selection, key parameter controls, processing history, full intermediate-image review, single-file download, per-image ZIP download, and whole-run ZIP download. Web runs are written under:

```text
results/web_runs/
```

## Pipeline

1. Read bmp/png/jpg/tif image and save `00_original.png`.
2. Convert to grayscale and save `01_gray.png`.
3. Save `02a_gradient_protect_mask_debug.png` as a debug view of the old gradient-style protect mask.
4. Run a first-pass unmasked large-scale background correction, then detect coarse candidate crystals.
5. Build `02b_candidate_protect_mask.png` from candidate circles only. This candidate protect mask is used for final background estimation and should normally stay below the configured cap.
6. Estimate background from raw gray using masked Gaussian normalized convolution:

```text
valid = 1 - protect_mask
background = GaussianBlur(gray * valid) / GaussianBlur(valid)
```

7. Apply flat-field correction:

```text
corrected = gray / background * median(background)
```

8. Save `03_background_estimate.png` and `04_flatfield_corrected.png`.
9. Apply light CLAHE after background correction and save `05_bg_corrected_clahe.png`.
10. Run square preflight. If enough square-like contour candidates are not already covered by round candidates, enable the square branch.
11. Detect raw candidate crystals with HoughCircles by default, or LoG if configured. When square strategy is enabled, add square-like contour candidates.
12. Validate candidates with shape-aware rules: round candidates use ring/radial metrics; square-like candidates use boundary strength, closure, solidity, extent, rectangularity, corner count, and local noise rejection.
13. Refine accepted candidates. Round candidates use reliable radial rays; square-like candidates use contour-mask refinement instead of radial fitting.
14. Optionally split high-confidence, slightly adhered parent masks with distance-transform seeds.
15. Measure actual area from final instance masks and write raw plus accepted statistics.

CLAHE is not recommended before background estimation because it can amplify shadows, noise, and ice-crystal edges, causing pseudo-structure to leak into the background model.

## Output Files

Per image folder:

```text
00_original.png
01_gray.png
02a_gradient_protect_mask_debug.png
02b_candidate_protect_mask.png
02c_square_preflight_overlay.png
02_protect_mask.png
03_background_estimate.png
04_flatfield_corrected.png
05_bg_corrected_clahe.png
06a_candidate_raw_overlay.png
06b_candidate_accepted_overlay.png
06c_candidate_rejected_overlay.png
06d_square_candidate_overlay.png
06e_shape_accepted_overlay.png
06f_shape_rejected_overlay.png
06_candidate_localization_overlay.png
07a_radial_reliable_points_overlay.png
07b_radial_rejected_points_overlay.png
07c_contour_refined_overlay.png
07d_square_contour_refined_overlay.png
07e_square_instance_masks.png
07f_cluster_parent_overlay.png
07g_cluster_split_overlay.png
07_contour_points_overlay.png
08_instance_masks.png
09_final_mask.png
10_final_overlay.png
11_label_overlay.png
12_area_histogram.png
candidates_raw.csv
candidates_accepted.csv
candidates_rejected.csv
candidates.csv
square_preflight_candidates.csv
crystals.csv
clusters.csv
summary.json
config_used.yaml
qc_report.txt
```

`candidates_raw.csv` contains every raw localization candidate. `candidates_accepted.csv` contains candidates that pass validation. `candidates_rejected.csv` records rejected candidates and reject reasons. The compatibility `candidates.csv` mirrors accepted candidates. Candidate radii are not area measurements.

`crystals.csv` contains refined raw instances and an `accepted` field. The primary per-instance area is `actual_area_px2`, measured as the nonzero pixel count in the final instance mask. If `pixel_size_um` is provided, `actual_area_um2` and `equivalent_diameter_um` are also written.

`summary.json` includes raw and accepted candidate counts, raw and accepted instance counts, raw and accepted total actual area, accepted equivalent diameter percentiles, accepted area fraction, QC warning count, the full config, and errors. Use `accepted_total_actual_area_px2` as the default scientific summary value.

`sensitivity.csv` is written in sensitivity mode and contains:

```text
background_sigma_px,hough_param2,radial_search_scale_max,
n_candidates,n_final_instances,total_actual_area_px2,
median_actual_area_px2,n_qc_warning
```

## Key Parameters

- `background_sigma_px`: scale of large-shadow background estimation. It should be larger than typical crystal diameter.
- `background_mode`: default `two_pass_candidate_protect`.
- `candidate_protect_radius_scale`, `candidate_protect_radius_extra_px`: protect radius used around preliminary candidates.
- `target_protect_mask_fraction_max`: cap for candidate-protect mask fraction.
- `protect_gradient_percentile`: percentile threshold for coarse edge protection.
- `protect_dilation_px`: dilation radius for the protect mask.
- `clahe_clip_limit`, `clahe_tile_grid_size`: light post-correction contrast enhancement.
- `candidate_method`: `hough` or `log`.
- `min_radius_px`, `max_radius_px`: candidate radius bounds.
- `candidate_validation_enabled`: validate raw Hough/LoG candidates before contour refinement.
- `min_edge_coverage_fraction`: minimum fraction of radial directions with a boundary peak.
- `ring_gradient_noise_ratio_min`: minimum ring gradient strength relative to local noise.
- `square_strategy_enabled`: `auto`, `true`, or `false`. `auto` enables square-like contour candidates only when preflight finds enough unmatched square-like objects.
- `square_gate_min_candidates`, `square_gate_min_candidate_fraction`, `square_gate_min_area_fraction`: image-level gate thresholds for square strategy.
- `square_gate_round_match_center_fraction`, `square_gate_round_match_iou`: suppress square preflight objects already covered by round candidates.
- `square_candidate_*`: contour-shape filters for square-like candidate detection.
- `square_refine_*`: local contour-mask refinement settings for square-like candidates.
- `adhesion_strategy_enabled`, `adhesion_split_enabled`: `auto`, `true`, or `false` controls for slight-adhesion splitting.
- `adhesion_*`: distance-transform seed and child-mask acceptance thresholds for cluster splitting.
- `contour_n_angles`: number of radial search directions.
- `radial_search_min_scale`, `radial_search_max_scale`, `radial_search_extra_px`: radial boundary search window.
- `radial_peak_nearmax_fraction`: accepts a near-maximum gradient peak, lightly preferring the approximate candidate radius.
- `max_overlap_skip_fraction`: skip an instance if too much of its mask overlaps earlier instances.
- `max_overlap_qc_fraction`: flag a kept instance if trimmed overlap is large.
- `exclude_edge_touching`: exclude edge-touching candidates from final statistics.
- `exclude_qc_warning_from_accepted`: exclude QC-warning instances from accepted summary statistics.
- `pixel_size_um`: micrometers per pixel. If omitted, physical units are not reported.

## QC Guidance

Review these files before trusting quantitative output:

- `02b_candidate_protect_mask.png`: should protect crystal neighborhoods without covering most shadow edges.
- `03_background_estimate.png`: should mainly show large-scale illumination/shadow.
- `04_flatfield_corrected.png`: should reduce irregular background.
- `06_candidate_localization_overlay.png`: candidates should cover visible crystals.
- `10_final_overlay.png`: final contours should follow crystal boundaries.
- `11_label_overlay.png`: labels should match `crystals.csv`.
- `06c_candidate_rejected_overlay.png`: rejected candidates should mostly be weak-edge, noisy, edge-touching, or suspicious objects.
- `02c_square_preflight_overlay.png`: confirms whether square-like candidates are present before enabling square strategy.
- `07d_square_contour_refined_overlay.png`: square/rectangular contours should follow actual crystal edges.
- `07g_cluster_split_overlay.png`: split children should correspond to real lightly adhered crystals, not texture fragments.
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
