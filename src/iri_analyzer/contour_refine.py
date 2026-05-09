from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from .candidates import Candidate
from .preprocess import gradient_magnitude


@dataclass
class RefinedInstance:
    candidate: Candidate
    mask: np.ndarray
    contour_points: np.ndarray
    radial_radii: np.ndarray
    valid_fraction: float
    overlap_trimmed_fraction: float
    skipped: bool
    skip_reason: str = ""


def refine_candidates(image_for_edges: np.ndarray, candidates: list[Candidate], config: dict) -> list[RefinedInstance]:
    grad = gradient_magnitude(image_for_edges)
    occupied = np.zeros(image_for_edges.shape[:2], dtype=bool)
    instances: list[RefinedInstance] = []
    for cand in candidates:
        refined = refine_candidate(grad, cand, config)
        original_area = int(np.count_nonzero(refined.mask))
        if original_area == 0:
            refined.skipped = True
            refined.skip_reason = "empty_mask"
            instances.append(refined)
            continue
        overlap = refined.mask & occupied
        overlap_fraction = float(np.count_nonzero(overlap) / original_area)
        if overlap_fraction > float(config["max_overlap_skip_fraction"]):
            refined.skipped = True
            refined.skip_reason = "overlap_skip"
            refined.overlap_trimmed_fraction = overlap_fraction
            instances.append(refined)
            continue
        if overlap_fraction > 0:
            refined.mask = refined.mask & ~occupied
            refined.overlap_trimmed_fraction = overlap_fraction
        occupied |= refined.mask
        instances.append(refined)
    return instances


def refine_candidate(gradient: np.ndarray, candidate: Candidate, config: dict) -> RefinedInstance:
    n_angles = int(config["contour_n_angles"])
    angles = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    approx_r = float(candidate.approx_radius_px)
    r_min = max(1.0, float(config["radial_search_min_scale"]) * approx_r)
    r_max = float(config["radial_search_max_scale"]) * approx_r + float(config["radial_search_extra_px"])
    radii_samples = np.linspace(r_min, r_max, max(8, int(math.ceil(r_max - r_min)) + 1), dtype=np.float32)
    found = np.full(n_angles, np.nan, dtype=np.float32)
    valid = np.zeros(n_angles, dtype=bool)
    nearmax_fraction = float(config["radial_peak_nearmax_fraction"])
    for i, theta in enumerate(angles):
        xs = candidate.center_x + radii_samples * math.cos(theta)
        ys = candidate.center_y + radii_samples * math.sin(theta)
        values = _sample_bilinear(gradient, xs, ys)
        finite = np.isfinite(values)
        if not np.any(finite):
            continue
        values = values.astype(np.float32)
        values[~finite] = 0
        max_val = float(values.max())
        if max_val <= 0:
            continue
        eligible = np.where(values >= nearmax_fraction * max_val)[0]
        if eligible.size:
            idx = int(eligible[np.argmin(np.abs(radii_samples[eligible] - approx_r))])
        else:
            idx = int(np.argmax(values))
        found[i] = radii_samples[idx]
        valid[i] = True
    valid_fraction = float(valid.mean()) if valid.size else 0.0
    if not np.any(valid):
        found[:] = approx_r
    else:
        found = _fill_missing_circular(found)
    smoothed = _smooth_radii(found, float(config["radial_smoothing_sigma"]))
    points = np.column_stack(
        [
            candidate.center_x + smoothed * np.cos(angles),
            candidate.center_y + smoothed * np.sin(angles),
        ]
    ).astype(np.float32)
    mask = _polygon_to_mask(points, gradient.shape)
    skipped = valid_fraction < float(config.get("min_valid_radial_fraction", 0.60))
    return RefinedInstance(
        candidate=candidate,
        mask=mask,
        contour_points=points,
        radial_radii=smoothed.astype(np.float32),
        valid_fraction=valid_fraction,
        overlap_trimmed_fraction=0.0,
        skipped=skipped,
        skip_reason="low_valid_radial_fraction" if skipped else "",
    )


def _sample_bilinear(image: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    inside = (xs >= 0) & (ys >= 0) & (xs <= w - 1) & (ys <= h - 1)
    map_x = xs.astype(np.float32).reshape(1, -1)
    map_y = ys.astype(np.float32).reshape(1, -1)
    sampled = cv2.remap(image.astype(np.float32), map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan)
    out = sampled.reshape(-1)
    out[~inside] = np.nan
    return out


def _fill_missing_circular(radii: np.ndarray) -> np.ndarray:
    out = radii.astype(np.float32).copy()
    n = out.size
    valid = np.isfinite(out)
    if valid.all():
        return out
    idx = np.arange(n)
    valid_idx = idx[valid]
    valid_vals = out[valid]
    extended_idx = np.concatenate([valid_idx - n, valid_idx, valid_idx + n])
    extended_vals = np.concatenate([valid_vals, valid_vals, valid_vals])
    out[~valid] = np.interp(idx[~valid], extended_idx, extended_vals)
    return out


def _smooth_radii(radii: np.ndarray, sigma: float) -> np.ndarray:
    if radii.size < 3:
        return radii
    padded = np.concatenate([radii[-2:], radii, radii[:2]])
    medianed = np.array([np.median(padded[i : i + 5]) for i in range(radii.size)], dtype=np.float32)
    if sigma <= 0:
        return medianed
    radius = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    wrapped = np.concatenate([medianed[-radius:], medianed, medianed[:radius]])
    return np.convolve(wrapped, kernel, mode="valid").astype(np.float32)


def _polygon_to_mask(points: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape[:2]
    pts = np.round(points).astype(np.int32)
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(pts) >= 3:
        cv2.fillPoly(mask, [pts], 1)
    return mask.astype(bool)
