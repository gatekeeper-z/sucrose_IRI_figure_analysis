from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np

from .background import (
    background_visual,
    corrected_visual,
    create_candidate_protect_mask,
    create_protect_mask,
    estimate_background_masked,
    estimate_background_unmasked,
    flatfield_correct,
)
from .candidates import Candidate, detect_candidates, run_square_preflight, validate_candidates
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
    radial_points_overlay,
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
    "ring_gradient_strength",
    "edge_coverage_fraction",
    "inside_outside_contrast",
    "local_noise_level",
    "accepted",
    "reject_reason",
    "shape_type",
    "candidate_method",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "shape_score",
    "boundary_gradient_strength",
    "contour_closure_score",
    "solidity",
    "extent",
    "rectangularity",
    "circularity",
    "corner_count",
    "local_background_rejection_score",
]

CRYSTAL_COLUMNS = [
    "image_id",
    "id",
    "candidate_id",
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
    "reliable_ray_fraction",
    "edge_coverage_fraction",
    "ring_gradient_strength",
    "inside_outside_contrast",
    "local_noise_level",
    "shape_type",
    "refine_method",
    "boundary_gradient_strength",
    "contour_closure_score",
    "solidity",
    "extent",
    "rectangularity",
    "corner_count",
    "shape_score",
    "split_parent_id",
    "split_child_index",
    "cluster_split",
    "cluster_split_confidence",
    "qc_flag",
    "accepted",
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
    accepted_candidates: list[Candidate]
    rejected_candidates: list[Candidate]
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

    gradient_protect_mask = create_protect_mask(gray, config)
    rough_background = estimate_background_unmasked(gray, float(config["background_sigma_px"]))
    corrected_prelim = flatfield_correct(gray, rough_background)
    corrected_prelim_uint8 = corrected_visual(corrected_prelim)
    prelim_clahe = apply_clahe(corrected_prelim_uint8, float(config["clahe_clip_limit"]), config["clahe_tile_grid_size"])
    prelim_candidates = detect_candidates(prelim_clahe, config, include_square=False)
    square_preflight_candidates, square_gate = run_square_preflight(prelim_clahe, prelim_candidates, config)
    square_strategy_used = bool(square_gate["square_strategy_used"])
    adhesion_strategy_used = _decide_adhesion_strategy(square_gate, config)
    runtime_config = dict(config)
    runtime_config["_square_strategy_used"] = square_strategy_used
    runtime_config["_adhesion_strategy_used"] = adhesion_strategy_used
    protect_source_candidates = prelim_candidates + square_preflight_candidates if square_strategy_used else prelim_candidates
    protect_mask, protect_candidates, protect_fraction = create_candidate_protect_mask(protect_source_candidates, gray.shape, runtime_config)
    if protect_fraction > float(config.get("target_protect_mask_fraction_max", 0.45)):
        warnings.append(f"candidate_protect_mask_fraction={protect_fraction:.3f} exceeds target")

    if str(config.get("background_mode", "two_pass_candidate_protect")) == "two_pass_candidate_protect":
        background = estimate_background_masked(gray, protect_mask, float(runtime_config["background_sigma_px"]))
    else:
        background = estimate_background_masked(gray, gradient_protect_mask, float(runtime_config["background_sigma_px"]))
    corrected = flatfield_correct(gray, background)
    corrected_uint8 = corrected_visual(corrected)
    clahe = apply_clahe(corrected_uint8, float(runtime_config["clahe_clip_limit"]), runtime_config["clahe_tile_grid_size"])
    candidates = detect_candidates(clahe, runtime_config, include_square=square_strategy_used)
    accepted_candidates, rejected_candidates = validate_candidates(clahe, candidates, runtime_config)

    n_edge_excluded = 0
    refine_input = accepted_candidates
    if bool(runtime_config.get("exclude_edge_touching", True)):
        n_edge_excluded = sum(c.edge_touching for c in candidates)
    instances = refine_candidates(clahe, refine_input, runtime_config)
    crystals = measure_instances(image_id, instances, runtime_config)
    summary = summarize(
        image_id=image_id,
        input_path=str(path),
        image_shape=gray.shape,
        n_candidates=len(candidates),
        n_edge_excluded=n_edge_excluded,
        measurements=crystals,
        config=runtime_config,
        error_list=errors,
        n_accepted_candidates=len(accepted_candidates),
        n_rejected_candidates=len(rejected_candidates),
    )
    summary.update(square_gate)
    summary["adhesion_strategy_used"] = bool(adhesion_strategy_used)
    summary["candidate_protect_mask_fraction"] = protect_fraction
    summary["n_prelim_candidates"] = len(prelim_candidates)
    summary["n_square_preflight_candidates"] = len(square_preflight_candidates)
    summary["n_protect_candidates_used"] = len(protect_candidates)

    if output_dir is not None:
        save_outputs(
            Path(output_dir),
            image_id,
            original,
            gray,
            gradient_protect_mask,
            square_preflight_candidates,
            protect_mask,
            background,
            corrected,
            clahe,
            candidates,
            accepted_candidates,
            rejected_candidates,
            instances,
            crystals,
            summary,
            runtime_config,
            str(path),
        )
    return ImageResult(
        image_id=image_id,
        input_path=str(path),
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        rejected_candidates=rejected_candidates,
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
    gradient_protect_mask,
    square_preflight_candidates,
    protect_mask,
    background,
    corrected,
    clahe,
    candidates,
    accepted_candidates,
    rejected_candidates,
    instances,
    crystals,
    summary,
    config,
    input_path: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    save_intermediate = bool(config.get("save_intermediate", True))
    labels = label_mask(instances, gray.shape, crystals)
    square_instances = [inst for inst in instances if inst.refine_method == "contour_square" and not inst.skipped]
    cluster_parent_instances = [inst for inst in instances if "cluster_unsplit" in inst.refine_method or inst.skip_reason == "cluster_unsplit"]
    cluster_split_instances = [inst for inst in instances if inst.cluster_split]
    if save_intermediate:
        save_image(output_dir / "00_original.png", original)
        save_image(output_dir / "01_gray.png", gray)
        save_image(output_dir / "02a_gradient_protect_mask_debug.png", gradient_protect_mask)
        save_image(output_dir / "02b_candidate_protect_mask.png", protect_mask)
        save_image(output_dir / "02c_square_preflight_overlay.png", candidate_overlay(gray, square_preflight_candidates, color_override=(255, 128, 0)))
        save_image(output_dir / "02_protect_mask.png", protect_mask)
        save_image(output_dir / "03_background_estimate.png", background_visual(background))
        save_image(output_dir / "04_flatfield_corrected.png", corrected_visual(corrected))
        save_image(output_dir / "05_bg_corrected_clahe.png", clahe)
        save_image(output_dir / "06a_candidate_raw_overlay.png", candidate_overlay(gray, candidates))
        save_image(output_dir / "06b_candidate_accepted_overlay.png", candidate_overlay(gray, accepted_candidates, color_override=(0, 255, 0)))
        save_image(output_dir / "06c_candidate_rejected_overlay.png", candidate_overlay(gray, rejected_candidates, color_override=(0, 0, 255)))
        save_image(output_dir / "06d_square_candidate_overlay.png", candidate_overlay(gray, [c for c in candidates if c.method == "contour_square"], color_override=(255, 128, 0)))
        save_image(output_dir / "06e_shape_accepted_overlay.png", candidate_overlay(gray, accepted_candidates, color_override=(0, 255, 0)))
        save_image(output_dir / "06f_shape_rejected_overlay.png", candidate_overlay(gray, rejected_candidates, color_override=(0, 0, 255)))
        save_image(output_dir / "06_candidate_localization_overlay.png", candidate_overlay(gray, accepted_candidates))
        save_image(output_dir / "07a_radial_reliable_points_overlay.png", radial_points_overlay(gray, instances, "reliable"))
        save_image(output_dir / "07b_radial_rejected_points_overlay.png", radial_points_overlay(gray, instances, "rejected"))
        save_image(output_dir / "07c_contour_refined_overlay.png", contour_points_overlay(gray, [inst for inst in instances if not inst.skipped]))
        save_image(output_dir / "07d_square_contour_refined_overlay.png", contour_points_overlay(gray, square_instances))
        save_image(output_dir / "07e_square_instance_masks.png", colorize_labels(label_mask(square_instances, gray.shape, crystals)))
        save_image(output_dir / "07f_cluster_parent_overlay.png", contour_points_overlay(gray, cluster_parent_instances))
        save_image(output_dir / "07g_cluster_split_overlay.png", contour_points_overlay(gray, cluster_split_instances))
        save_image(output_dir / "07_contour_points_overlay.png", contour_points_overlay(gray, instances))
        save_image(output_dir / "08_instance_masks.png", colorize_labels(labels))
        save_image(output_dir / "09_final_mask.png", labels > 0)
        save_image(output_dir / "10_final_overlay.png", final_overlay(gray, instances, crystals))
        save_image(output_dir / "11_label_overlay.png", label_overlay(gray, labels))
        save_area_histogram(output_dir / "12_area_histogram.png", [c for c in crystals if c.accepted])
    write_csv(output_dir / "square_preflight_candidates.csv", [c.to_dict(image_id) for c in square_preflight_candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "candidates_raw.csv", [c.to_dict(image_id) for c in candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "candidates_accepted.csv", [c.to_dict(image_id) for c in accepted_candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "candidates_rejected.csv", [c.to_dict(image_id) for c in rejected_candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "candidates.csv", [c.to_dict(image_id) for c in accepted_candidates], CANDIDATE_COLUMNS)
    write_csv(output_dir / "crystals.csv", [c.to_dict() for c in crystals], CRYSTAL_COLUMNS)
    write_csv(output_dir / "clusters.csv", [c.to_dict() for c in crystals if c.cluster_split or "cluster" in c.refine_method or c.shape_type == "cluster"], CRYSTAL_COLUMNS)
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


def _decide_adhesion_strategy(square_gate: dict, config: dict) -> bool:
    mode = str(config.get("adhesion_strategy_enabled", config.get("adhesion_split_enabled", "auto"))).lower()
    if mode in {"true", "1", "yes", "on"}:
        return True
    if mode in {"false", "0", "no", "off"}:
        return False
    return (
        bool(square_gate.get("square_strategy_used", False))
        and (
            int(square_gate.get("n_square_like_preflight_candidates", 0)) >= int(config.get("adhesion_gate_min_candidates", 8))
            or float(square_gate.get("square_like_area_fraction", 0.0)) >= float(config.get("adhesion_gate_min_area_fraction", 0.01))
        )
    )


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
