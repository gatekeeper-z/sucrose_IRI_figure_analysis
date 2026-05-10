from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from .candidates import Candidate, sample_bilinear
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
    reliable_ray_fraction: float = 0.0
    reliable_points: np.ndarray | None = None
    rejected_points: np.ndarray | None = None


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
    reliable = np.zeros(n_angles, dtype=bool)
    nearmax_fraction = float(config["radial_peak_nearmax_fraction"])
    noise = candidate.local_noise_level if candidate.local_noise_level is not None else _estimate_local_gradient_noise(gradient, candidate)
    ring_strength = candidate.ring_gradient_strength if candidate.ring_gradient_strength is not None else 0.0
    ray_threshold = max(float(noise) * 1.25, float(ring_strength) * 0.35, 1e-6)
    rejected_points: list[tuple[float, float]] = []
    for i, theta in enumerate(angles):
        xs = candidate.center_x + radii_samples * math.cos(theta)
        ys = candidate.center_y + radii_samples * math.sin(theta)
        values = sample_bilinear(gradient, xs, ys)
        finite = np.isfinite(values)
        if not np.any(finite):
            continue
        values = values.astype(np.float32)
        values[~finite] = 0
        max_val = float(values.max())
        peak_idx = int(np.argmax(values))
        if max_val < ray_threshold:
            rejected_points.append((float(xs[peak_idx]), float(ys[peak_idx])))
            continue
        eligible = np.where(values >= nearmax_fraction * max_val)[0]
        if eligible.size:
            if bool(config.get("prefer_outer_edge", True)):
                idx = int(eligible[-1])
            else:
                idx = int(eligible[np.argmin(np.abs(radii_samples[eligible] - approx_r))])
        else:
            idx = peak_idx
        found[i] = radii_samples[idx]
        reliable[i] = True
    reliable_ray_fraction = float(reliable.mean()) if reliable.size else 0.0
    if reliable_ray_fraction < float(config.get("min_reliable_ray_fraction", config.get("min_valid_radial_fraction", 0.60))):
        return RefinedInstance(
            candidate=candidate,
            mask=np.zeros(gradient.shape[:2], dtype=bool),
            contour_points=np.empty((0, 2), dtype=np.float32),
            radial_radii=found,
            valid_fraction=reliable_ray_fraction,
            overlap_trimmed_fraction=0.0,
            skipped=True,
            skip_reason="low_reliable_ray_fraction",
            reliable_ray_fraction=reliable_ray_fraction,
            reliable_points=_points_from_radii(candidate, angles, found, reliable),
            rejected_points=np.array(rejected_points, dtype=np.float32) if rejected_points else np.empty((0, 2), dtype=np.float32),
        )
    found = _fill_missing_circular(found)
    found = _limit_neighbor_jumps(found, approx_r, config)
    smoothed = _smooth_radii(found, float(config["radial_smoothing_sigma"]))
    smoothed = _limit_neighbor_jumps(smoothed, approx_r, config)
    points = np.column_stack(
        [
            candidate.center_x + smoothed * np.cos(angles),
            candidate.center_y + smoothed * np.sin(angles),
        ]
    ).astype(np.float32)
    mask = _polygon_to_mask(points, gradient.shape)
    return RefinedInstance(
        candidate=candidate,
        mask=mask,
        contour_points=points,
        radial_radii=smoothed.astype(np.float32),
        valid_fraction=reliable_ray_fraction,
        overlap_trimmed_fraction=0.0,
        skipped=False,
        skip_reason="",
        reliable_ray_fraction=reliable_ray_fraction,
        reliable_points=_points_from_radii(candidate, angles, found, reliable),
        rejected_points=np.array(rejected_points, dtype=np.float32) if rejected_points else np.empty((0, 2), dtype=np.float32),
    )


def _points_from_radii(candidate: Candidate, angles: np.ndarray, radii: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.empty((0, 2), dtype=np.float32)
    selected_angles = angles[mask]
    selected_radii = radii[mask]
    return np.column_stack(
        [
            candidate.center_x + selected_radii * np.cos(selected_angles),
            candidate.center_y + selected_radii * np.sin(selected_angles),
        ]
    ).astype(np.float32)


def _estimate_local_gradient_noise(gradient: np.ndarray, candidate: Candidate) -> float:
    h, w = gradient.shape[:2]
    r = float(candidate.approx_radius_px)
    pad = int(math.ceil(2.2 * r + 4))
    x0 = max(0, int(candidate.center_x) - pad)
    x1 = min(w, int(candidate.center_x) + pad + 1)
    y0 = max(0, int(candidate.center_y) - pad)
    y1 = min(h, int(candidate.center_y) + pad + 1)
    roi = gradient[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - candidate.center_x, yy - candidate.center_y)
    values = roi[(dist >= 1.55 * r) & (dist <= 2.25 * r)]
    if values.size < 16:
        values = roi.reshape(-1)
    return float(np.percentile(values, 75)) if values.size else 0.0


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


def _limit_neighbor_jumps(radii: np.ndarray, approx_radius: float, config: dict) -> np.ndarray:
    if radii.size < 3:
        return radii.astype(np.float32)
    out = radii.astype(np.float32).copy()
    max_jump = max(
        float(config.get("max_neighbor_radius_jump_px", 4)),
        float(config.get("max_neighbor_radius_jump_fraction", 0.18)) * float(approx_radius),
    )
    for _ in range(2):
        for i in range(1, out.size):
            delta = out[i] - out[i - 1]
            if abs(delta) > max_jump:
                out[i] = out[i - 1] + np.sign(delta) * max_jump
        for i in range(out.size - 2, -1, -1):
            delta = out[i] - out[i + 1]
            if abs(delta) > max_jump:
                out[i] = out[i + 1] + np.sign(delta) * max_jump
    return out.astype(np.float32)


def _polygon_to_mask(points: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape[:2]
    pts = np.round(points).astype(np.int32)
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(pts) >= 3:
        cv2.fillPoly(mask, [pts], 1)
    return mask.astype(bool)
