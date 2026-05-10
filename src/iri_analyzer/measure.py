from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from .contour_refine import RefinedInstance


@dataclass
class CrystalMeasurement:
    image_id: str
    id: int
    candidate_id: int
    center_x: float
    center_y: float
    approx_radius_px: float
    actual_area_px2: int
    actual_area_um2: float | None
    equivalent_diameter_px: float
    equivalent_diameter_um: float | None
    circle_area_px2: float
    area_over_circle: float
    median_radial_radius_px: float
    min_radial_radius_px: float
    max_radial_radius_px: float
    radial_radius_range_px: float
    edge_touching: bool
    overlap_trimmed_fraction: float
    reliable_ray_fraction: float
    edge_coverage_fraction: float | None
    ring_gradient_strength: float | None
    inside_outside_contrast: float | None
    local_noise_level: float | None
    qc_flag: str
    accepted: bool

    def to_dict(self) -> dict:
        return asdict(self)


def measure_instances(image_id: str, instances: list[RefinedInstance], config: dict) -> list[CrystalMeasurement]:
    measurements: list[CrystalMeasurement] = []
    next_id = 1
    for inst in instances:
        cand = inst.candidate
        area_px2 = int(np.count_nonzero(inst.mask))
        circle_area = math.pi * cand.approx_radius_px**2
        equivalent_diameter_px = math.sqrt(4.0 * area_px2 / math.pi) if area_px2 > 0 else 0.0
        pixel_size_um = config.get("pixel_size_um")
        actual_area_um2 = float(area_px2 * pixel_size_um**2) if pixel_size_um is not None else None
        equivalent_diameter_um = float(equivalent_diameter_px * pixel_size_um) if pixel_size_um is not None else None
        radii = inst.radial_radii[np.isfinite(inst.radial_radii)]
        if radii.size == 0:
            radii = np.array([cand.approx_radius_px], dtype=np.float32)
        median_r = float(np.median(radii))
        min_r = float(np.min(radii))
        max_r = float(np.max(radii))
        flags = qc_flags(
            area_px2=area_px2,
            area_over_circle=float(area_px2 / circle_area) if circle_area > 0 else float("nan"),
            radial_range=max_r - min_r,
            approx_radius=cand.approx_radius_px,
            edge_touching=cand.edge_touching,
            overlap_trimmed_fraction=inst.overlap_trimmed_fraction,
            config=config,
        )
        if inst.skipped:
            flags.append(inst.skip_reason or "contour_rejected")
        qc_flag = ";".join(flags) if flags else "ok"
        accepted = (not inst.skipped) and (qc_flag == "ok" or not bool(config.get("exclude_qc_warning_from_accepted", True)))
        measurements.append(
            CrystalMeasurement(
                image_id=image_id,
                id=next_id,
                candidate_id=int(cand.candidate_id),
                center_x=float(cand.center_x),
                center_y=float(cand.center_y),
                approx_radius_px=float(cand.approx_radius_px),
                actual_area_px2=area_px2,
                actual_area_um2=actual_area_um2,
                equivalent_diameter_px=float(equivalent_diameter_px),
                equivalent_diameter_um=equivalent_diameter_um,
                circle_area_px2=float(circle_area),
                area_over_circle=float(area_px2 / circle_area) if circle_area > 0 else float("nan"),
                median_radial_radius_px=median_r,
                min_radial_radius_px=min_r,
                max_radial_radius_px=max_r,
                radial_radius_range_px=float(max_r - min_r),
                edge_touching=bool(cand.edge_touching),
                overlap_trimmed_fraction=float(inst.overlap_trimmed_fraction),
                reliable_ray_fraction=float(inst.reliable_ray_fraction),
                edge_coverage_fraction=cand.edge_coverage_fraction,
                ring_gradient_strength=cand.ring_gradient_strength,
                inside_outside_contrast=cand.inside_outside_contrast,
                local_noise_level=cand.local_noise_level,
                qc_flag=qc_flag,
                accepted=bool(accepted),
            )
        )
        next_id += 1
    return measurements


def qc_flags(
    area_px2: int,
    area_over_circle: float,
    radial_range: float,
    approx_radius: float,
    edge_touching: bool,
    overlap_trimmed_fraction: float,
    config: dict,
) -> list[str]:
    flags: list[str] = []
    if not np.isfinite(area_over_circle) or area_over_circle < 0.5 or area_over_circle > 1.8:
        flags.append("area_over_circle")
    if radial_range > 0.8 * approx_radius:
        flags.append("radial_radius_range")
    if overlap_trimmed_fraction > float(config["max_overlap_qc_fraction"]):
        flags.append("overlap_trimmed")
    if edge_touching:
        flags.append("edge_touching")
    if area_px2 < int(config["min_area_px2"]):
        flags.append("small_area")
    max_area = config.get("max_area_px2")
    if max_area is not None and area_px2 > int(max_area):
        flags.append("large_area")
    return flags


def summarize(
    image_id: str,
    input_path: str,
    image_shape: tuple[int, int],
    n_candidates: int,
    n_edge_excluded: int,
    measurements: list[CrystalMeasurement],
    config: dict,
    error_list: list[dict] | None = None,
    n_accepted_candidates: int | None = None,
    n_rejected_candidates: int | None = None,
) -> dict:
    areas = np.array([m.actual_area_px2 for m in measurements], dtype=np.float64)
    diameters = np.array([m.equivalent_diameter_px for m in measurements], dtype=np.float64)
    accepted_measurements = [m for m in measurements if m.accepted]
    rejected_measurements = [m for m in measurements if not m.accepted]
    accepted_areas = np.array([m.actual_area_px2 for m in accepted_measurements], dtype=np.float64)
    accepted_diameters = np.array([m.equivalent_diameter_px for m in accepted_measurements], dtype=np.float64)
    rejected_areas = np.array([m.actual_area_px2 for m in rejected_measurements], dtype=np.float64)
    pixel_size_um = config.get("pixel_size_um")
    raw_total_px = float(areas.sum()) if areas.size else 0.0
    accepted_total_px = float(accepted_areas.sum()) if accepted_areas.size else 0.0
    rejected_total_px = float(rejected_areas.sum()) if rejected_areas.size else 0.0
    h, w = image_shape[:2]
    summary = {
        "image_id": image_id,
        "input_path": str(input_path),
        "n_raw_candidates": int(n_candidates),
        "n_accepted_candidates": int(n_accepted_candidates if n_accepted_candidates is not None else n_candidates),
        "n_rejected_candidates": int(n_rejected_candidates if n_rejected_candidates is not None else 0),
        "n_raw_instances": int(len(measurements)),
        "n_accepted_instances": int(len(accepted_measurements)),
        "n_rejected_instances": int(len(rejected_measurements)),
        "n_edge_excluded": int(n_edge_excluded),
        "raw_total_actual_area_px2": raw_total_px,
        "accepted_total_actual_area_px2": accepted_total_px,
        "rejected_total_actual_area_px2": rejected_total_px,
        "raw_total_actual_area_um2": float(raw_total_px * pixel_size_um**2) if pixel_size_um is not None else None,
        "accepted_total_actual_area_um2": float(accepted_total_px * pixel_size_um**2) if pixel_size_um is not None else None,
        "raw_median_area_px2": float(np.median(areas)) if areas.size else None,
        "accepted_median_area_px2": float(np.median(accepted_areas)) if accepted_areas.size else None,
        "accepted_area_fraction": float(accepted_total_px / (h * w)) if h > 0 and w > 0 else None,
        "mean_actual_area_px2": float(np.mean(accepted_areas)) if accepted_areas.size else None,
        "median_actual_area_px2": float(np.median(accepted_areas)) if accepted_areas.size else None,
        "D10_equivalent_diameter_px": float(np.percentile(accepted_diameters, 10)) if accepted_diameters.size else None,
        "D50_equivalent_diameter_px": float(np.percentile(accepted_diameters, 50)) if accepted_diameters.size else None,
        "D90_equivalent_diameter_px": float(np.percentile(accepted_diameters, 90)) if accepted_diameters.size else None,
        "area_fraction": float(accepted_total_px / (h * w)) if h > 0 and w > 0 else None,
        "n_qc_warning": int(sum(m.qc_flag != "ok" for m in measurements)),
        "config": config,
        "error_list": error_list or [],
    }
    # Backward-compatible aliases now point to accepted scientific statistics.
    summary["n_candidates"] = summary["n_raw_candidates"]
    summary["n_final_instances"] = summary["n_accepted_instances"]
    summary["total_actual_area_px2"] = summary["accepted_total_actual_area_px2"]
    summary["total_actual_area_um2"] = summary["accepted_total_actual_area_um2"]
    return summary
