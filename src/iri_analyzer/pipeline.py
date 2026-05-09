from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np

from .background import background_visual, corrected_visual, create_protect_mask, estimate_background_masked, flatfield_correct
from .candidates import Candidate, detect_candidates
from .contour_refine import RefinedInstance, refine_candidates
from .io import (
    collect_images,
    prepare_image_output_dir,
    read_image,
    safe_image_id,
    write_csv,
    write_dataframe,
    write_json,
    write_yaml,
)
from .measure import CrystalMeasurement, measure_instances, summarize
from .preprocess import apply_clahe, to_gray
from .qc import build_qc_report, write_qc_report
from .visualize import (
    candidate_overlay,
    colorize_labels,
    contour_points_overlay,
    final_overlay,
    label_mask,
    label_overlay,
    save_area_histogram,
    save_image,
)


CANDIDATE_COLUMNS = [
    "image_id",
    "candidate_id",
    "center_x",
    "center_y",
    "approx_radius_px",
    "edge_touching",
    "method",
    "score",
]

CRYSTAL_COLUMNS = [
    "image_id",
    "id",
    "center_x",
    "center_y",
    "approx_radius_px",
    "actual_area_px2",
    "actual_area_um2",
    "equivalent_diameter_px",
    "equivalent_diameter_um",
    "circle_area_px2",
    "area_over_circle",
    "median_radial_radius_px",
    "min_radial_radius_px",
    "max_radial_radius_px",
    "radial_radius_range_px",
    "edge_touching",
    "overlap_trimmed_fraction",
    "qc_flag",
]

SENSITIVITY_COLUMNS = [
    "background_sigma_px",
    "hough_param2",
    "radial_search_scale_max",
    "n_candidates",
    "n_final_instances",
    "total_actual_area_px2",
    "median_actual_area_px2",
    "n_qc_warning",
]


@dataclass
class ImageResult:
    image_id: str
    input_path: str
    candidates: list[Candidate]
    instances: list[RefinedInstance]
    crystals: list[CrystalMeasurement]
    summary: dict
    warnings: list[str]
    errors: list[dict]


def process_image(image_path: str | Path, config: dict, output_dir: str | Path | None = None) -> ImageResult:
    path = Path(image_path)
    image_id = safe_image_id(path)
    errors: list[dict] = []
    warnings: list[str] = []

    original = read_image(path)
    gray = to_gray(original)
    protect_mask = create_protect_mask(gray, config)
    background = estimate_background_masked(gray, protect_mask, float(config["background_sigma_px"]))
    corrected = flatfield_correct(gray, background)
    corrected_uint8 = corrected_visual(corrected)
    clahe = apply_clahe(corrected_uint8, float(config["clahe_clip_limit"]), config["clahe_tile_grid_size"])
    candidates = detect_candidates(clahe, config)

    n_edge_excluded = 0
    refine_input = candidates
    if bool(config.get("exclude_edge_touching", True)):
        n_edge_excluded = sum(c.edge_touching for c in candidates)
        refine_input = [c for c in candidates if not c.edge_touching]
    instances = refine_candidates(clahe, refine_input, config)
    crystals = measure_instances(image_id, instances, config)
    summary = summarize(
        image_id=image_id,
        input_path=str(path),
        image_shape=gray.shape,
        n_candidates=len(candidates),
        n_edge_excluded=n_edge_excluded,
        measurements=crystals,
        config=config,
        error_list=errors,
    )

    if output_dir is not None:
        save_outputs(
            Path(output_dir),
            image_id,
            original,
            gray,
            protect_mask,
            background,
            corrected,
            clahe,
            candidates,
            instances,
            crystals,
            summary,
            config,
            str(path),
        )
    return ImageResult(
        image_id=image_id,
        input_path=str(path),
        candidates=candidates,
        instances=instances,
        crystals=crystals,
        summary=summary,
        warnings=warnings,
        errors=errors,
    )


def save_outputs(
    output_dir: Path,
    image_id: str,
    original,
    gray,
    protect_mask,
    background,
    corrected,
    clahe,
    candidates,
    instances,
    crystals,
    summary,
    config,
    input_path: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    save_intermediate = bool(config.get("save_intermediate", True))
    labels = label_mask(instances, gray.shape)
    if save_intermediate:
        save_image(output_dir / "00_original.png", original)
        save_image(output_dir / "01_gray.png", gray)
        save_image(output_dir / "02_protect_mask.png", protect_mask)
        save_image(output_dir / "03_background_estimate.png", background_visual(background))
        save_image(output_dir / "04_flatfield_corrected.png", corrected_visual(corrected))
        save_image(output_dir / "05_bg_corrected_clahe.png", clahe)
        save_image(output_dir / "06_candidate_localization_overlay.png", candidate_overlay(gray, candidates))
        save_image(output_dir / "07_contour_points_overlay.png", contour_points_overlay(gray, instances))
        save_image(output_dir / "08_instance_masks.png", colorize_labels(labels))
        save_image(output_dir / "09_final_mask.png", labels > 0)
        save_image(output_dir / "10_final_overlay.png", final_overlay(gray, instances, crystals))
        save_image(output_dir / "11_label_overlay.png", label_overlay(gray, labels))
        save_area_histogram(output_dir / "12_area_histogram.png", crystals)
    write_csv(output_dir / "candidates.csv", [c.to_dict(image_id) for c in candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "crystals.csv", [c.to_dict() for c in crystals], CRYSTAL_COLUMNS)
    write_json(output_dir / "summary.json", summary)
    write_yaml(output_dir / "config_used.yaml", config)
    write_qc_report(output_dir / "qc_report.txt", build_qc_report(image_id, input_path, candidates, instances, crystals, summary))


def run_qc(input_path: str | Path, output_root: str | Path, config: dict, overwrite: bool = False) -> list[ImageResult]:
    images = collect_images(input_path)
    if not images:
        raise ValueError(f"No supported images found in {input_path}")
    results: list[ImageResult] = []
    for path in images:
        image_id = safe_image_id(path)
        out_dir = prepare_image_output_dir(output_root, image_id, overwrite=overwrite)
        results.append(process_image(path, config, out_dir))
    return results


def run_batch(input_path: str | Path, output_root: str | Path, config: dict, overwrite: bool = False) -> list[ImageResult]:
    images = collect_images(input_path)
    if not images:
        raise ValueError(f"No supported images found in {input_path}")
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[ImageResult] = []
    failures: list[dict] = []
    for path in images:
        image_id = safe_image_id(path)
        try:
            out_dir = prepare_image_output_dir(output_root, image_id, overwrite=overwrite)
            results.append(process_image(path, config, out_dir))
        except Exception as exc:  # batch must isolate per-image failures
            failures.append({"image_id": image_id, "input_path": str(path), "error_code": exc.__class__.__name__, "message": str(exc)})
    write_json(
        output_root / "batch_summary.json",
        {
            "n_input_images": len(images),
            "n_success": len(results),
            "n_failed": len(failures),
            "failures": failures,
            "image_summaries": [r.summary for r in results],
        },
    )
    return results


def run_sensitivity(input_path: str | Path, output_root: str | Path, config: dict, overwrite: bool = False) -> list[dict]:
    images = collect_images(input_path)
    if len(images) != 1:
        raise ValueError("sensitivity mode expects exactly one image input")
    image_id = safe_image_id(images[0])
    out_dir = prepare_image_output_dir(output_root, image_id, overwrite=overwrite)
    rows: list[dict] = []
    for background_sigma_px, hough_param2, radial_search_scale_max in product([60, 80, 100], [35, 40, 45, 50], [1.35, 1.45, 1.60]):
        cfg = dict(config)
        cfg.update(
            {
                "background_sigma_px": background_sigma_px,
                "hough_param2": hough_param2,
                "radial_search_scale_max": radial_search_scale_max,
                "save_intermediate": False,
            }
        )
        result = process_image(images[0], cfg, output_dir=None)
        rows.append(
            {
                "background_sigma_px": background_sigma_px,
                "hough_param2": hough_param2,
                "radial_search_scale_max": radial_search_scale_max,
                "n_candidates": result.summary["n_candidates"],
                "n_final_instances": result.summary["n_final_instances"],
                "total_actual_area_px2": result.summary["total_actual_area_px2"],
                "median_actual_area_px2": result.summary["median_actual_area_px2"],
                "n_qc_warning": result.summary["n_qc_warning"],
            }
        )
    write_dataframe(out_dir / "sensitivity.csv", rows, SENSITIVITY_COLUMNS)
    write_yaml(out_dir / "config_used.yaml", config)
    return rows
