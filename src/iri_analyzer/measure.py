from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from .contour_refine import RefinedInstance


@dataclass
class CrystalMeasurement:
    image_id: str
    id: int
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
    qc_flag: str

    def to_dict(self) -> dict:
        return asdict(self)


def measure_instances(image_id: str, instances: list[RefinedInstance], config: dict) -> list[CrystalMeasurement]:
    measurements: list[CrystalMeasurement] = []
    next_id = 1
    for inst in instances:
        if inst.skipped:
            continue
        cand = inst.candidate
        area_px2 = int(np.count_nonzero(inst.mask))
        if area_px2 <= 0:
            continue
        circle_area = math.pi * cand.approx_radius_px**2
        equivalent_diameter_px = math.sqrt(4.0 * area_px2 / math.pi)
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
        measurements.append(
            CrystalMeasurement(
                image_id=image_id,
                id=next_id,
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
                qc_flag=";".join(flags) if flags else "ok",
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
) -> dict:
    areas = np.array([m.actual_area_px2 for m in measurements], dtype=np.float64)
    diameters = np.array([m.equivalent_diameter_px for m in measurements], dtype=np.float64)
    pixel_size_um = config.get("pixel_size_um")
    total_px = float(areas.sum()) if areas.size else 0.0
    h, w = image_shape[:2]
    summary = {
        "image_id": image_id,
        "input_path": str(input_path),
        "n_candidates": int(n_candidates),
        "n_final_instances": int(len(measurements)),
        "n_edge_excluded": int(n_edge_excluded),
        "total_actual_area_px2": total_px,
        "total_actual_area_um2": float(total_px * pixel_size_um**2) if pixel_size_um is not None else None,
        "mean_actual_area_px2": float(np.mean(areas)) if areas.size else None,
        "median_actual_area_px2": float(np.median(areas)) if areas.size else None,
        "D10_equivalent_diameter_px": float(np.percentile(diameters, 10)) if diameters.size else None,
        "D50_equivalent_diameter_px": float(np.percentile(diameters, 50)) if diameters.size else None,
        "D90_equivalent_diameter_px": float(np.percentile(diameters, 90)) if diameters.size else None,
        "area_fraction": float(total_px / (h * w)) if h > 0 and w > 0 else None,
        "n_qc_warning": int(sum(m.qc_flag != "ok" for m in measurements)),
        "config": config,
        "error_list": error_list or [],
    }
    return summary
