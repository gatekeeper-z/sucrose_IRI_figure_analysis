from __future__ import annotations

from dataclasses import dataclass, replace
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
    refine_method: str = "radial"
    split_parent_id: int | None = None
    split_child_index: int | None = None
    cluster_split: bool = False
    cluster_split_confidence: float | None = None


def refine_candidates(image_for_edges: np.ndarray, candidates: list[Candidate], config: dict) -> list[RefinedInstance]:
    grad = gradient_magnitude(image_for_edges)
    occupied = np.zeros(image_for_edges.shape[:2], dtype=bool)
    instances: list[RefinedInstance] = []
    for cand in candidates:
        refined = refine_candidate(grad, cand, config)
        for item in _maybe_split_adhesion(refined, config):
            _append_with_overlap(item, occupied, instances, config)
    return instances


def _append_with_overlap(refined: RefinedInstance, occupied: np.ndarray, instances: list[RefinedInstance], config: dict) -> None:
    original_area = int(np.count_nonzero(refined.mask))
    if original_area == 0:
        refined.skipped = True
        refined.skip_reason = "empty_mask"
        instances.append(refined)
        return
    overlap = refined.mask & occupied
    overlap_fraction = float(np.count_nonzero(overlap) / original_area)
    if overlap_fraction > float(config["max_overlap_skip_fraction"]):
        refined.skipped = True
        refined.skip_reason = "overlap_skip"
        refined.overlap_trimmed_fraction = overlap_fraction
        instances.append(refined)
        return
    if overlap_fraction > 0:
        refined.mask = refined.mask & ~occupied
        refined.overlap_trimmed_fraction = overlap_fraction
    occupied |= refined.mask
    instances.append(refined)


def refine_candidate(gradient: np.ndarray, candidate: Candidate, config: dict) -> RefinedInstance:
    if _is_square_like(candidate) and bool(config.get("square_refine_enabled", True)):
        return refine_square_candidate(gradient, candidate, config)
    return refine_radial_candidate(gradient, candidate, config)


def refine_radial_candidate(gradient: np.ndarray, candidate: Candidate, config: dict) -> RefinedInstance:
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
            refine_method="radial",
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
        refine_method="radial",
    )


def refine_square_candidate(gradient: np.ndarray, candidate: Candidate, config: dict) -> RefinedInstance:
    h, w = gradient.shape[:2]
    pad = int(config.get("square_refine_roi_padding_px", 6))
    x0, y0, x1, y1 = _candidate_roi(candidate, (h, w), pad)
    roi = gradient[y0:y1, x0:x1]
    empty = RefinedInstance(
        candidate=candidate,
        mask=np.zeros((h, w), dtype=bool),
        contour_points=np.empty((0, 2), dtype=np.float32),
        radial_radii=np.array([], dtype=np.float32),
        valid_fraction=0.0,
        overlap_trimmed_fraction=0.0,
        skipped=True,
        skip_reason="square_contour_not_found",
        reliable_ray_fraction=0.0,
        refine_method="contour_square",
    )
    if roi.size == 0:
        return empty
    finite = roi[np.isfinite(roi)]
    if finite.size == 0:
        return empty
    threshold = _positive_percentile(finite, float(config.get("square_refine_gradient_percentile", 88)))
    if candidate.local_noise_level is not None:
        threshold = max(float(threshold), float(candidate.local_noise_level) * 1.05)
    edges = (roi >= threshold).astype(np.uint8)
    local_center = np.array([candidate.center_x - x0, candidate.center_y - y0], dtype=np.float32)
    close_px = int(config.get("square_refine_close_px", 2))
    if close_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * close_px + 1, 2 * close_px + 1))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    barrier_dilation = int(config.get("square_refine_barrier_dilation_px", 1))
    barrier = edges
    if barrier_dilation > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * barrier_dilation + 1, 2 * barrier_dilation + 1))
        barrier = cv2.dilate(barrier, kernel)
    closed_region = _closed_boundary_region(barrier, local_center, candidate, config)
    if closed_region is not None:
        contours, _ = cv2.findContours(closed_region.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            selected = max(contours, key=cv2.contourArea)
            support = _boundary_support(roi, selected, threshold)
            if support >= float(config.get("square_refine_min_boundary_support", 0.45)):
                full_contour = selected.astype(np.float32).copy()
                full_contour[:, 0, 0] += x0
                full_contour[:, 0, 1] += y0
                points = full_contour.reshape(-1, 2).astype(np.float32)
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
                return RefinedInstance(
                    candidate=candidate,
                    mask=mask.astype(bool),
                    contour_points=points,
                    radial_radii=np.array([candidate.approx_radius_px], dtype=np.float32),
                    valid_fraction=float(support),
                    overlap_trimmed_fraction=0.0,
                    skipped=False,
                    skip_reason="",
                    reliable_ray_fraction=float(support),
                    reliable_points=points.astype(np.float32),
                    rejected_points=np.empty((0, 2), dtype=np.float32),
                    refine_method="contour_square",
                )
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return empty

    best_contour: np.ndarray | None = None
    best_score = -1.0
    best_support = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < float(config.get("min_area_px2", 20)):
            continue
        pts = contour.reshape(-1, 2)
        if pts.size == 0:
            continue
        x, y, cw, ch = cv2.boundingRect(contour)
        bbox_center = np.array([x + cw / 2, y + ch / 2], dtype=np.float32)
        center_distance = float(np.linalg.norm(bbox_center - local_center))
        center_score = 1.0 / (1.0 + center_distance / max(candidate.approx_radius_px, 1.0))
        inside = cv2.pointPolygonTest(contour, (float(local_center[0]), float(local_center[1])), False) >= 0
        support = _boundary_support(roi, contour, threshold)
        score = support + center_score + (0.5 if inside else 0.0) + min(area / max(float(candidate.approx_radius_px**2), 1.0), 2.0) * 0.15
        if score > best_score:
            best_score = score
            best_contour = contour
            best_support = support
    if best_contour is None:
        return empty

    selected = best_contour
    selected_area = max(float(cv2.contourArea(selected)), 1.0)
    if bool(config.get("square_refine_allow_convex_hull_fallback", True)):
        hull = cv2.convexHull(selected)
        hull_area = float(cv2.contourArea(hull))
        max_increase = float(config.get("square_refine_hull_fallback_max_area_increase", 0.25))
        if best_support < float(config.get("square_refine_min_boundary_support", 0.45)) and hull_area > selected_area:
            if (hull_area - selected_area) / selected_area <= max_increase:
                selected = hull
                best_support = max(best_support, _boundary_support(roi, selected, threshold))

    if best_support < float(config.get("square_refine_min_boundary_support", 0.45)):
        empty.skip_reason = "low_square_boundary_support"
        empty.reliable_ray_fraction = float(best_support)
        empty.valid_fraction = float(best_support)
        return empty

    full_contour = selected.astype(np.float32).copy()
    full_contour[:, 0, 0] += x0
    full_contour[:, 0, 1] += y0
    points = full_contour.reshape(-1, 2).astype(np.float32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
    return RefinedInstance(
        candidate=candidate,
        mask=mask.astype(bool),
        contour_points=points,
        radial_radii=np.array([candidate.approx_radius_px], dtype=np.float32),
        valid_fraction=float(best_support),
        overlap_trimmed_fraction=0.0,
        skipped=False,
        skip_reason="",
        reliable_ray_fraction=float(best_support),
        reliable_points=points.astype(np.float32),
        rejected_points=np.empty((0, 2), dtype=np.float32),
        refine_method="contour_square",
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


def _is_square_like(candidate: Candidate) -> bool:
    return candidate.shape_type in {"square_like", "rectangular", "polygonal", "cluster"} or candidate.method == "contour_square"


def _candidate_roi(candidate: Candidate, shape: tuple[int, int], pad: int) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    if candidate.bbox_x is not None and candidate.bbox_y is not None and candidate.bbox_w is not None and candidate.bbox_h is not None:
        x0 = max(0, int(candidate.bbox_x) - pad)
        y0 = max(0, int(candidate.bbox_y) - pad)
        x1 = min(w, int(candidate.bbox_x + candidate.bbox_w) + pad)
        y1 = min(h, int(candidate.bbox_y + candidate.bbox_h) + pad)
    else:
        r = int(math.ceil(candidate.approx_radius_px + pad))
        x0 = max(0, int(round(candidate.center_x)) - r)
        y0 = max(0, int(round(candidate.center_y)) - r)
        x1 = min(w, int(round(candidate.center_x)) + r + 1)
        y1 = min(h, int(round(candidate.center_y)) + r + 1)
    return x0, y0, x1, y1


def _boundary_support(gradient_roi: np.ndarray, contour: np.ndarray, threshold: float) -> float:
    pts = contour.reshape(-1, 2)
    if pts.size == 0:
        return 0.0
    xs = np.clip(pts[:, 0], 0, gradient_roi.shape[1] - 1)
    ys = np.clip(pts[:, 1], 0, gradient_roi.shape[0] - 1)
    values = gradient_roi[ys, xs]
    if values.size == 0:
        return 0.0
    return float(np.mean(values >= threshold))


def _closed_boundary_region(barrier: np.ndarray, local_center: np.ndarray, candidate: Candidate, config: dict) -> np.ndarray | None:
    free = barrier == 0
    if not np.any(free):
        return None
    n_labels, labels = cv2.connectedComponents(free.astype(np.uint8))
    if n_labels <= 1:
        return None
    border_labels = set(labels[0, :].tolist())
    border_labels.update(labels[-1, :].tolist())
    border_labels.update(labels[:, 0].tolist())
    border_labels.update(labels[:, -1].tolist())
    candidate_labels = [label for label in range(1, n_labels) if label not in border_labels]
    if not candidate_labels:
        return None
    bbox_area = None
    if candidate.bbox_w is not None and candidate.bbox_h is not None:
        bbox_area = max(int(candidate.bbox_w) * int(candidate.bbox_h), 1)
    min_area = float(config.get("square_refine_closed_region_min_area_px2", config.get("min_area_px2", 20)))
    min_bbox_fraction = float(config.get("square_refine_closed_region_min_bbox_fraction", 0.18))
    best_label = None
    best_score = -1.0
    for label in candidate_labels:
        component = labels == label
        area = int(np.count_nonzero(component))
        if area < min_area:
            continue
        if bbox_area is not None and area / bbox_area < min_bbox_fraction:
            continue
        ys, xs = np.where(component)
        if xs.size == 0:
            continue
        center_distance = float(np.hypot(np.mean(xs) - local_center[0], np.mean(ys) - local_center[1]))
        contains_center = 0 <= int(round(local_center[1])) < component.shape[0] and 0 <= int(round(local_center[0])) < component.shape[1] and component[int(round(local_center[1])), int(round(local_center[0]))]
        score = area / (1.0 + center_distance) + (area if contains_center else 0.0)
        if score > best_score:
            best_score = score
            best_label = label
    if best_label is None:
        return None
    region = labels == best_label
    close_px = int(config.get("square_refine_region_close_px", 1))
    if close_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * close_px + 1, 2 * close_px + 1))
        region = cv2.morphologyEx(region.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    return region


def _adhesion_enabled(config: dict) -> bool:
    if "_adhesion_strategy_used" in config:
        return bool(config["_adhesion_strategy_used"])
    mode = str(config.get("adhesion_split_enabled", config.get("adhesion_strategy_enabled", "auto"))).lower()
    return mode not in {"false", "0", "no", "off"}


def _maybe_split_adhesion(instance: RefinedInstance, config: dict) -> list[RefinedInstance]:
    if instance.skipped or not _adhesion_enabled(config):
        return [instance]
    area = int(np.count_nonzero(instance.mask))
    if area < int(config.get("adhesion_min_parent_area_px2", 120)) or area > int(config.get("adhesion_max_parent_area_px2", 5000)):
        return [instance]
    if instance.refine_method == "contour_square":
        if not bool(config.get("adhesion_split_square_candidates", True)):
            return [instance]
        if area < int(config.get("adhesion_square_min_parent_area_px2", 700)):
            return [instance]
        if instance.candidate.solidity is not None and instance.candidate.solidity > float(config.get("adhesion_square_parent_max_solidity", 0.72)):
            return [instance]
        if instance.candidate.extent is not None and instance.candidate.extent > float(config.get("adhesion_square_parent_max_extent", 0.42)):
            return [instance]
    circle_area = math.pi * float(instance.candidate.approx_radius_px) ** 2
    if circle_area > 0 and area / circle_area < float(config.get("adhesion_min_parent_area_over_circle", 0.70)):
        return [instance]
    if instance.candidate.bbox_w is not None and instance.candidate.bbox_h is not None:
        bbox_area = max(int(instance.candidate.bbox_w) * int(instance.candidate.bbox_h), 1)
        if area / bbox_area < float(config.get("adhesion_min_parent_area_over_bbox", 0.40)):
            return [instance]
    children, confidence, peak_count = _split_instance_watershed(instance, config)
    min_peaks = int(config.get("adhesion_min_distance_peaks", 2))
    if children and confidence >= float(config.get("adhesion_min_split_confidence", 0.55)):
        return children
    if peak_count >= min_peaks and bool(config.get("adhesion_mark_unsplit_clusters", True)):
        instance.skipped = True
        instance.skip_reason = "cluster_unsplit"
        instance.cluster_split_confidence = float(confidence)
        instance.refine_method = f"{instance.refine_method}+cluster_unsplit"
    return [instance]


def _split_instance_watershed(instance: RefinedInstance, config: dict) -> tuple[list[RefinedInstance], float, int]:
    mask_u8 = instance.mask.astype(np.uint8)
    if np.count_nonzero(mask_u8) == 0:
        return [], 0.0, 0
    dist = cv2.distanceTransform(mask_u8, cv2.DIST_L2, 3)
    max_dist = float(dist.max())
    if max_dist <= 0:
        return [], 0.0, 0
    peak_threshold = max(2.0, max_dist * float(config.get("adhesion_peak_distance_fraction", 0.45)))
    dilated = cv2.dilate(dist, np.ones((3, 3), np.float32))
    peaks = (dist >= peak_threshold) & (dist >= dilated - 1e-6) & instance.mask
    merge_px = int(config.get("adhesion_peak_merge_px", 2))
    if merge_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * merge_px + 1, 2 * merge_px + 1))
        peaks = cv2.dilate(peaks.astype(np.uint8), kernel) > 0
        peaks &= instance.mask
    n_labels, peak_labels = cv2.connectedComponents(peaks.astype(np.uint8))
    peak_count = int(n_labels - 1)
    min_peaks = int(config.get("adhesion_min_distance_peaks", 2))
    max_peaks = int(config.get("adhesion_max_distance_peaks", 6))
    if peak_count < min_peaks or peak_count > max_peaks:
        return [], 0.0, peak_count

    centroids: list[tuple[float, float]] = []
    for idx in range(1, n_labels):
        ys, xs = np.where(peak_labels == idx)
        if xs.size:
            centroids.append((float(np.mean(xs)), float(np.mean(ys))))
    if len(centroids) < min_peaks:
        return [], 0.0, peak_count
    mask_ys, mask_xs = np.where(instance.mask)
    coords = np.column_stack([mask_xs, mask_ys]).astype(np.float32)
    centers = np.array(centroids, dtype=np.float32)
    distances = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    nearest = np.argmin(distances, axis=1)
    labels = np.zeros(mask_u8.shape, dtype=np.int32)
    labels[mask_ys, mask_xs] = nearest + 2
    child_masks: list[np.ndarray] = []
    child_areas: list[int] = []
    for label in range(2, len(centroids) + 2):
        child = (labels == label) & instance.mask
        child_area = int(np.count_nonzero(child))
        if child_area >= int(config.get("adhesion_child_min_area_px2", 30)):
            child_masks.append(child)
            child_areas.append(child_area)
    if len(child_masks) < min_peaks:
        return [], 0.0, peak_count
    parent_area = max(int(np.count_nonzero(instance.mask)), 1)
    max_child_ratio = max(child_areas) / parent_area
    if max_child_ratio > float(config.get("adhesion_child_max_area_ratio", 0.85)):
        return [], float(max(0.0, 1.0 - max_child_ratio)), peak_count
    confidence = float(np.clip(0.35 + 0.10 * len(child_masks) + 0.55 * (1.0 - max_child_ratio), 0.0, 1.0))
    children: list[RefinedInstance] = []
    parent_id = int(instance.candidate.candidate_id)
    for child_index, child in enumerate(child_masks, start=1):
        ys, xs = np.where(child)
        if xs.size == 0:
            continue
        area = int(np.count_nonzero(child))
        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        equiv_radius = math.sqrt(area / math.pi)
        x, y, cw, ch = cv2.boundingRect(child.astype(np.uint8))
        child_candidate = replace(
            instance.candidate,
            candidate_id=parent_id * 1000 + child_index,
            center_x=cx,
            center_y=cy,
            approx_radius_px=float(equiv_radius),
            bbox_x=int(x),
            bbox_y=int(y),
            bbox_w=int(cw),
            bbox_h=int(ch),
            shape_type="cluster",
            method="contour_cluster",
            candidate_method="contour_cluster",
        )
        contours, _ = cv2.findContours(child.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float32) if contours else np.empty((0, 2), dtype=np.float32)
        children.append(
            RefinedInstance(
                candidate=child_candidate,
                mask=child,
                contour_points=points,
                radial_radii=np.array([equiv_radius], dtype=np.float32),
                valid_fraction=1.0,
                overlap_trimmed_fraction=instance.overlap_trimmed_fraction,
                skipped=False,
                skip_reason="",
                reliable_ray_fraction=1.0,
                reliable_points=points,
                rejected_points=np.empty((0, 2), dtype=np.float32),
                refine_method="cluster_watershed",
                split_parent_id=parent_id,
                split_child_index=child_index,
                cluster_split=True,
                cluster_split_confidence=confidence,
            )
        )
    return children, confidence, peak_count


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


def _positive_percentile(values: np.ndarray, percentile: float) -> float:
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]
    source = positive if positive.size else finite
    return float(np.percentile(source, percentile)) if source.size else 0.0
