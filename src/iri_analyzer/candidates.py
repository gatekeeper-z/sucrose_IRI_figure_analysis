from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import cv2
import numpy as np

from .preprocess import gradient_magnitude


@dataclass
class Candidate:
    candidate_id: int
    center_x: float
    center_y: float
    approx_radius_px: float
    edge_touching: bool
    method: str
    score: float
    ring_gradient_strength: float | None = None
    edge_coverage_fraction: float | None = None
    inside_outside_contrast: float | None = None
    local_noise_level: float | None = None
    accepted: bool = True
    reject_reason: str = ""
    shape_type: str = "round"
    candidate_method: str | None = None
    bbox_x: int | None = None
    bbox_y: int | None = None
    bbox_w: int | None = None
    bbox_h: int | None = None
    shape_score: float | None = None
    boundary_gradient_strength: float | None = None
    contour_closure_score: float | None = None
    solidity: float | None = None
    extent: float | None = None
    rectangularity: float | None = None
    circularity: float | None = None
    corner_count: int | None = None
    local_background_rejection_score: float | None = None

    def to_dict(self, image_id: str) -> dict:
        row = asdict(self)
        row["image_id"] = image_id
        if row.get("candidate_method") is None:
            row["candidate_method"] = self.method
        return row


def detect_candidates(gray: np.ndarray, config: dict, include_square: bool | None = None) -> list[Candidate]:
    method = str(config.get("candidate_method", "hough")).lower()
    if method == "log":
        candidates = _detect_log(gray, config)
    elif method == "hough":
        candidates = _detect_hough(gray, config)
    elif method == "hybrid":
        candidates = _detect_hough(gray, config)
    else:
        raise ValueError(f"Unsupported candidate_method: {method}")
    square_requested = bool(config.get("_square_strategy_used", False)) if include_square is None else bool(include_square)
    if method == "hybrid" and include_square is None:
        square_requested = True
    if square_requested:
        candidates = candidates + detect_square_candidates(gray, config)
    candidates = nms_candidates(candidates, config)
    for idx, cand in enumerate(candidates, start=1):
        cand.candidate_id = idx
    return candidates


def run_square_preflight(gray: np.ndarray, round_candidates: list[Candidate], config: dict) -> tuple[list[Candidate], dict]:
    """Scan for square-like crystals and decide whether the square branch should run."""
    requested = str(config.get("square_strategy_enabled", "auto")).lower()
    if requested in {"false", "0", "no", "off"} or not bool(config.get("square_preflight_enabled", True)):
        return [], _square_gate_info(requested, False, 0.0, 0, 0.0, 0.0, "disabled")

    square_candidates = nms_candidates(detect_square_candidates(gray, config), config)
    for idx, cand in enumerate(square_candidates, start=1):
        cand.candidate_id = idx
    gate_candidates = [cand for cand in square_candidates if not _matches_round_candidate(cand, round_candidates, config)]
    image_area = max(1, int(gray.shape[0] * gray.shape[1]))
    square_area = float(sum(_candidate_bbox_area(c) for c in gate_candidates))
    n_square = len(gate_candidates)
    total_candidates = max(1, len(round_candidates) + len(square_candidates))
    candidate_fraction = float(n_square / total_candidates)
    area_fraction = float(square_area / image_area)
    if gate_candidates:
        score = float(np.mean([c.shape_score or 0.0 for c in gate_candidates]))
    else:
        score = 0.0

    if requested in {"true", "1", "yes", "on"}:
        used = True
        reason = "forced_true"
    elif requested == "auto":
        used = (
            n_square >= int(config.get("square_gate_min_candidates", 25))
            and (
                candidate_fraction >= float(config.get("square_gate_min_candidate_fraction", 0.12))
                or area_fraction >= float(config.get("square_gate_min_area_fraction", 0.015))
            )
            and score >= float(config.get("square_gate_min_score", 0.55))
        )
        reason = "auto_triggered" if used else "auto_not_triggered"
    else:
        used = False
        reason = f"unknown_mode_{requested}"
    info = _square_gate_info(requested, used, score, n_square, candidate_fraction, area_fraction, reason)
    info["n_square_like_preflight_candidates_total"] = int(len(square_candidates))
    info["n_square_like_preflight_candidates_matched_round"] = int(len(square_candidates) - n_square)
    return square_candidates, info


def _square_gate_info(
    requested: str,
    used: bool,
    score: float,
    n_square: int,
    candidate_fraction: float,
    area_fraction: float,
    reason: str,
) -> dict:
    return {
        "square_strategy_requested": requested,
        "square_strategy_used": bool(used),
        "square_gate_score": float(score),
        "n_square_like_preflight_candidates": int(n_square),
        "square_like_candidate_fraction": float(candidate_fraction),
        "square_like_area_fraction": float(area_fraction),
        "square_gate_reason": reason,
    }


def validate_candidates(gray: np.ndarray, candidates: list[Candidate], config: dict) -> tuple[list[Candidate], list[Candidate]]:
    """Validate raw localization candidates before contour refinement."""
    if not bool(config.get("candidate_validation_enabled", True)):
        for cand in candidates:
            cand.accepted = True
            cand.reject_reason = ""
        return candidates, []

    grad = gradient_magnitude(gray)
    accepted: list[Candidate] = []
    rejected: list[Candidate] = []
    for cand in candidates:
        if _is_square_like(cand):
            metrics = square_candidate_validation_metrics(gray, grad, cand, config)
            cand.boundary_gradient_strength = metrics["boundary_gradient_strength"]
            cand.contour_closure_score = metrics["contour_closure_score"]
            cand.solidity = metrics["solidity"]
            cand.extent = metrics["extent"]
            cand.rectangularity = metrics["rectangularity"]
            cand.circularity = metrics["circularity"]
            cand.corner_count = metrics["corner_count"]
            cand.local_noise_level = metrics["local_noise_level"]
            cand.local_background_rejection_score = metrics["local_background_rejection_score"]
            cand.shape_score = metrics["shape_score"]
            cand.edge_coverage_fraction = metrics["contour_closure_score"]
            cand.ring_gradient_strength = metrics["boundary_gradient_strength"]
            cand.inside_outside_contrast = metrics["inside_outside_contrast"]
        else:
            metrics = candidate_validation_metrics(gray, grad, cand, config)
            cand.ring_gradient_strength = metrics["ring_gradient_strength"]
            cand.edge_coverage_fraction = metrics["edge_coverage_fraction"]
            cand.inside_outside_contrast = metrics["inside_outside_contrast"]
            cand.local_noise_level = metrics["local_noise_level"]
        reasons: list[str] = []
        if cand.approx_radius_px < float(config["min_radius_px"]) or cand.approx_radius_px > float(config["max_radius_px"]):
            reasons.append("radius_out_of_range")
        if bool(config.get("exclude_edge_touching", True)) and cand.edge_touching:
            reasons.append("edge_touching")
        if _is_square_like(cand):
            noise = max(cand.local_noise_level or 0.0, 1e-6)
            if (cand.boundary_gradient_strength or 0.0) < noise * float(config.get("square_min_boundary_gradient_noise_ratio", 1.4)):
                reasons.append("weak_square_boundary")
            if (cand.contour_closure_score or 0.0) < float(config.get("square_min_contour_closure_score", 0.45)):
                reasons.append("low_square_closure")
            if (cand.shape_score or 0.0) < float(config.get("square_min_shape_score", 0.50)):
                reasons.append("low_square_shape_score")
        else:
            if cand.edge_coverage_fraction < float(config.get("min_edge_coverage_fraction", 0.45)):
                reasons.append("low_edge_coverage")
            noise = max(cand.local_noise_level, 1e-6)
            if cand.ring_gradient_strength < noise * float(config.get("ring_gradient_noise_ratio_min", 1.5)):
                reasons.append("weak_ring_gradient")
            contrast_min = config.get("inside_outside_contrast_min")
            if contrast_min is not None and cand.inside_outside_contrast < float(contrast_min):
                reasons.append("low_inside_outside_contrast")
        cand.accepted = not reasons
        cand.reject_reason = ";".join(reasons)
        if cand.accepted:
            accepted.append(cand)
        else:
            rejected.append(cand)
    return accepted, rejected


def candidate_validation_metrics(gray: np.ndarray, grad: np.ndarray, candidate: Candidate, config: dict) -> dict:
    n_angles = int(config.get("contour_n_angles", 72))
    approx_r = float(candidate.approx_radius_px)
    min_r = max(1.0, 0.65 * approx_r)
    max_r = 1.35 * approx_r + 3.0
    radii = np.linspace(min_r, max_r, max(8, int(math.ceil(max_r - min_r)) + 1), dtype=np.float32)
    angles = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    peak_values: list[float] = []
    edge_hits = 0
    noise = _local_noise_level(grad, candidate)
    threshold = max(noise * float(config.get("ring_gradient_noise_ratio_min", 1.5)), 1e-6)
    for theta in angles:
        xs = candidate.center_x + radii * math.cos(theta)
        ys = candidate.center_y + radii * math.sin(theta)
        values = sample_bilinear(grad, xs, ys)
        finite = np.isfinite(values)
        if not np.any(finite):
            continue
        peak = float(np.nanmax(values))
        peak_values.append(peak)
        if peak >= threshold:
            edge_hits += 1
    ring_strength = float(np.percentile(peak_values, 75)) if peak_values else 0.0
    coverage = float(edge_hits / n_angles) if n_angles > 0 else 0.0
    contrast = _inside_outside_contrast(gray, candidate)
    return {
        "ring_gradient_strength": ring_strength,
        "edge_coverage_fraction": coverage,
        "inside_outside_contrast": contrast,
        "local_noise_level": noise,
    }


def square_candidate_validation_metrics(gray: np.ndarray, grad: np.ndarray, candidate: Candidate, config: dict) -> dict:
    noise = _local_noise_level(grad, candidate)
    boundary = candidate.boundary_gradient_strength
    closure = candidate.contour_closure_score
    solidity = candidate.solidity
    extent = candidate.extent
    rectangularity = candidate.rectangularity
    circularity = candidate.circularity
    corner_count = candidate.corner_count
    if boundary is None or closure is None or solidity is None or extent is None or rectangularity is None or circularity is None or corner_count is None:
        recomputed = _square_metrics_from_bbox(gray, grad, candidate, config)
        boundary = recomputed["boundary_gradient_strength"]
        closure = recomputed["contour_closure_score"]
        solidity = recomputed["solidity"]
        extent = recomputed["extent"]
        rectangularity = recomputed["rectangularity"]
        circularity = recomputed["circularity"]
        corner_count = recomputed["corner_count"]
    ratio = float(boundary or 0.0) / max(float(noise), 1e-6)
    score = _score_square_metrics(
        boundary_noise_ratio=ratio,
        closure=float(closure or 0.0),
        solidity=float(solidity or 0.0),
        extent=float(extent or 0.0),
        rectangularity=float(rectangularity or 0.0),
        circularity=float(circularity or 0.0),
        corner_count=int(corner_count or 0),
        config=config,
    )
    contrast = _inside_outside_contrast(gray, candidate)
    return {
        "boundary_gradient_strength": float(boundary or 0.0),
        "contour_closure_score": float(closure or 0.0),
        "solidity": float(solidity or 0.0),
        "extent": float(extent or 0.0),
        "rectangularity": float(rectangularity or 0.0),
        "circularity": float(circularity or 0.0),
        "corner_count": int(corner_count or 0),
        "local_noise_level": float(noise),
        "local_background_rejection_score": float(ratio),
        "shape_score": float(score),
        "inside_outside_contrast": float(contrast),
    }


def _square_metrics_from_bbox(gray: np.ndarray, grad: np.ndarray, candidate: Candidate, config: dict) -> dict:
    h, w = gray.shape[:2]
    pad = int(config.get("square_refine_roi_padding_px", 6))
    x0, y0, x1, y1 = _candidate_roi(candidate, (h, w), pad)
    roi_grad = grad[y0:y1, x0:x1]
    if roi_grad.size == 0:
        return {
            "boundary_gradient_strength": 0.0,
            "contour_closure_score": 0.0,
            "solidity": 0.0,
            "extent": 0.0,
            "rectangularity": 0.0,
            "circularity": 1.0,
            "corner_count": 0,
        }
    finite = roi_grad[np.isfinite(roi_grad)]
    threshold = _positive_percentile(finite, float(config.get("square_candidate_gradient_percentile", 95))) if finite.size else 0.0
    edges = (roi_grad >= threshold).astype(np.uint8)
    close_px = int(config.get("square_candidate_close_px", 2))
    if close_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * close_px + 1, 2 * close_px + 1))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {
            "boundary_gradient_strength": float(np.percentile(finite, 75)) if finite.size else 0.0,
            "contour_closure_score": 0.0,
            "solidity": 0.0,
            "extent": 0.0,
            "rectangularity": 0.0,
            "circularity": 1.0,
            "corner_count": 0,
        }
    contour = max(contours, key=cv2.contourArea)
    metrics = _contour_shape_metrics(contour, roi_grad, config)
    return metrics


def sample_bilinear(image: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    inside = (xs >= 0) & (ys >= 0) & (xs <= w - 1) & (ys <= h - 1)
    map_x = xs.astype(np.float32).reshape(1, -1)
    map_y = ys.astype(np.float32).reshape(1, -1)
    sampled = cv2.remap(
        image.astype(np.float32),
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=np.nan,
    )
    out = sampled.reshape(-1)
    out[~inside] = np.nan
    return out


def _edge_touching(x: float, y: float, r: float, shape: tuple[int, int]) -> bool:
    h, w = shape[:2]
    return x - r <= 0 or y - r <= 0 or x + r >= w - 1 or y + r >= h - 1


def _bbox_edge_touching(x: int, y: int, w_box: int, h_box: int, shape: tuple[int, int]) -> bool:
    h, w = shape[:2]
    return x <= 0 or y <= 0 or x + w_box >= w - 1 or y + h_box >= h - 1


def _local_noise_level(grad: np.ndarray, candidate: Candidate) -> float:
    h, w = grad.shape[:2]
    r = float(candidate.approx_radius_px)
    pad = int(math.ceil(2.4 * r + 4))
    x0 = max(0, int(candidate.center_x) - pad)
    x1 = min(w, int(candidate.center_x) + pad + 1)
    y0 = max(0, int(candidate.center_y) - pad)
    y1 = min(h, int(candidate.center_y) + pad + 1)
    roi = grad[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - candidate.center_x, yy - candidate.center_y)
    noise_mask = (dist >= 1.55 * r) & (dist <= 2.30 * r)
    values = roi[noise_mask]
    if values.size < 16:
        values = roi.reshape(-1)
    return float(np.percentile(values, 75)) if values.size else 0.0


def _inside_outside_contrast(gray: np.ndarray, candidate: Candidate) -> float:
    h, w = gray.shape[:2]
    r = float(candidate.approx_radius_px)
    pad = int(math.ceil(1.7 * r + 4))
    x0 = max(0, int(candidate.center_x) - pad)
    x1 = min(w, int(candidate.center_x) + pad + 1)
    y0 = max(0, int(candidate.center_y) - pad)
    y1 = min(h, int(candidate.center_y) + pad + 1)
    roi = gray[y0:y1, x0:x1].astype(np.float32)
    if roi.size == 0:
        return 0.0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - candidate.center_x, yy - candidate.center_y)
    inside = roi[dist <= 0.65 * r]
    outside = roi[(dist >= 1.10 * r) & (dist <= 1.45 * r)]
    if inside.size == 0 or outside.size == 0:
        return 0.0
    return float(abs(np.mean(inside) - np.mean(outside)))


def _detect_hough(gray: np.ndarray, config: dict) -> list[Candidate]:
    img = cv2.medianBlur(gray, 3)
    circles = cv2.HoughCircles(
        img,
        cv2.HOUGH_GRADIENT,
        dp=float(config["hough_dp"]),
        minDist=float(config["hough_min_dist_px"]),
        param1=float(config["hough_param1"]),
        param2=float(config["hough_param2"]),
        minRadius=int(config["min_radius_px"]),
        maxRadius=int(config["max_radius_px"]),
    )
    if circles is None:
        return []
    out: list[Candidate] = []
    for x, y, r in np.squeeze(circles, axis=0):
        out.append(
            Candidate(
                candidate_id=0,
                center_x=float(x),
                center_y=float(y),
                approx_radius_px=float(r),
                edge_touching=_edge_touching(float(x), float(y), float(r), gray.shape),
                method="hough",
                score=float(r),
                shape_type="round",
                candidate_method="hough",
            )
        )
    return out


def _detect_log(gray: np.ndarray, config: dict) -> list[Candidate]:
    img = gray.astype(np.float32) / 255.0
    min_r = float(config["min_radius_px"])
    max_r = float(config["max_radius_px"])
    n_sigma = int(config.get("log_num_sigma", 8))
    sigmas = np.linspace(max(min_r / math.sqrt(2), 1.0), max_r / math.sqrt(2), n_sigma)
    responses: list[tuple[np.ndarray, float]] = []
    all_values = []
    for sigma in sigmas:
        blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=float(sigma), sigmaY=float(sigma))
        lap = cv2.Laplacian(blurred, cv2.CV_32F, ksize=3)
        response = np.abs(lap) * (sigma**2)
        responses.append((response, float(sigma)))
        all_values.append(response.reshape(-1))
    threshold = np.percentile(np.concatenate(all_values), float(config.get("log_threshold_percentile", 99.2)))
    candidates: list[Candidate] = []
    for response, sigma in responses:
        radius = math.sqrt(2) * sigma
        dilated = cv2.dilate(response, np.ones((3, 3), np.float32))
        peaks = (response == dilated) & (response >= threshold)
        ys, xs = np.where(peaks)
        for x, y in zip(xs, ys):
            candidates.append(
                Candidate(
                    candidate_id=0,
                    center_x=float(x),
                    center_y=float(y),
                    approx_radius_px=float(radius),
                    edge_touching=_edge_touching(float(x), float(y), float(radius), gray.shape),
                    method="log",
                    score=float(response[y, x]),
                    shape_type="round",
                    candidate_method="log",
                )
            )
    return candidates


def detect_square_candidates(gray: np.ndarray, config: dict) -> list[Candidate]:
    grad = gradient_magnitude(gray)
    finite = grad[np.isfinite(grad)]
    if finite.size == 0:
        return []
    threshold = _positive_percentile(finite, float(config.get("square_candidate_gradient_percentile", 95)))
    edges = (grad >= threshold).astype(np.uint8)
    close_px = int(config.get("square_candidate_close_px", 2))
    if close_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * close_px + 1, 2 * close_px + 1))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    dilation = int(config.get("square_candidate_dilation_px", 1))
    if dilation > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * dilation + 1, 2 * dilation + 1))
        edges = cv2.dilate(edges, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = float(config.get("square_candidate_min_area_px2", config.get("contour_candidate_min_area_px2", 40)))
    max_area = float(config.get("square_candidate_max_area_px2", config.get("contour_candidate_max_area_px2", 2500)))
    max_aspect = float(config.get("square_candidate_max_aspect_ratio", config.get("contour_candidate_max_aspect_ratio", 4.0)))
    min_extent = float(config.get("square_candidate_min_extent", 0.35))
    min_solidity = float(config.get("square_candidate_min_solidity", 0.45))
    min_rectangularity = float(config.get("square_candidate_min_rectangularity", 0.40))
    max_circularity = float(config.get("square_candidate_max_circularity", 0.88))
    min_corners = int(config.get("square_candidate_min_corners", 4))
    max_corners = int(config.get("square_candidate_max_corners", 10))
    min_r = float(config["min_radius_px"])
    max_r = float(config["max_radius_px"])
    out: list[Candidate] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w <= 1 or h <= 1:
            continue
        aspect = max(w / h, h / w)
        if aspect > max_aspect:
            continue
        metrics = _contour_shape_metrics(contour, grad, config)
        if metrics["extent"] < min_extent or metrics["solidity"] < min_solidity:
            continue
        if metrics["rectangularity"] < min_rectangularity:
            continue
        if metrics["circularity"] > max_circularity:
            continue
        if metrics["corner_count"] < min_corners or metrics["corner_count"] > max_corners:
            continue
        radius = max(0.5 * math.hypot(w, h), math.sqrt(max(area, 1.0) / math.pi))
        if radius < min_r or radius > max_r:
            continue
        moment = cv2.moments(contour)
        if moment["m00"]:
            cx = moment["m10"] / moment["m00"]
            cy = moment["m01"] / moment["m00"]
        else:
            cx = x + w / 2
            cy = y + h / 2
        shape_type = "square_like" if aspect <= 1.35 else "rectangular"
        noise_candidate = Candidate(
            candidate_id=0,
            center_x=float(cx),
            center_y=float(cy),
            approx_radius_px=float(radius),
            edge_touching=_bbox_edge_touching(x, y, w, h, gray.shape),
            method="contour_square",
            score=float(area),
            shape_type=shape_type,
            candidate_method="contour_square",
            bbox_x=int(x),
            bbox_y=int(y),
            bbox_w=int(w),
            bbox_h=int(h),
        )
        noise = _local_noise_level(grad, noise_candidate)
        ratio = metrics["boundary_gradient_strength"] / max(noise, 1e-6)
        shape_score = _score_square_metrics(
            boundary_noise_ratio=ratio,
            closure=metrics["contour_closure_score"],
            solidity=metrics["solidity"],
            extent=metrics["extent"],
            rectangularity=metrics["rectangularity"],
            circularity=metrics["circularity"],
            corner_count=metrics["corner_count"],
            config=config,
        )
        if shape_score < float(config.get("square_preflight_min_shape_score", 0.35)):
            continue
        out.append(
            Candidate(
                candidate_id=0,
                center_x=float(cx),
                center_y=float(cy),
                approx_radius_px=float(radius),
                edge_touching=_bbox_edge_touching(x, y, w, h, gray.shape),
                method="contour_square",
                score=float(area),
                shape_type=shape_type,
                candidate_method="contour_square",
                bbox_x=int(x),
                bbox_y=int(y),
                bbox_w=int(w),
                bbox_h=int(h),
                shape_score=float(shape_score),
                boundary_gradient_strength=float(metrics["boundary_gradient_strength"]),
                contour_closure_score=float(metrics["contour_closure_score"]),
                solidity=float(metrics["solidity"]),
                extent=float(metrics["extent"]),
                rectangularity=float(metrics["rectangularity"]),
                circularity=float(metrics["circularity"]),
                corner_count=int(metrics["corner_count"]),
                local_noise_level=float(noise),
                local_background_rejection_score=float(ratio),
            )
        )
    return out


def _contour_shape_metrics(contour: np.ndarray, grad: np.ndarray, config: dict) -> dict:
    area = float(cv2.contourArea(contour))
    x, y, w, h = cv2.boundingRect(contour)
    bbox_area = max(float(w * h), 1.0)
    extent = float(area / bbox_area)
    hull = cv2.convexHull(contour)
    hull_area = max(float(cv2.contourArea(hull)), 1.0)
    solidity = float(area / hull_area)
    rect = cv2.minAreaRect(contour)
    rect_w, rect_h = rect[1]
    rect_area = max(float(rect_w * rect_h), 1.0)
    rectangularity = float(min(area / rect_area, 1.0))
    peri = cv2.arcLength(contour, True)
    circularity = float((4.0 * math.pi * area / (peri * peri)) if peri > 0 else 1.0)
    epsilon = float(config.get("square_candidate_approx_epsilon_fraction", 0.04)) * peri
    approx = cv2.approxPolyDP(contour, epsilon, True)
    corner_count = int(len(approx))
    pts = contour.reshape(-1, 2)
    if pts.size and grad.size:
        xs = np.clip(pts[:, 0], 0, grad.shape[1] - 1)
        ys = np.clip(pts[:, 1], 0, grad.shape[0] - 1)
        boundary = float(np.percentile(grad[ys, xs], 75))
    else:
        boundary = 0.0
    closure = float(np.clip(min(extent / 0.55, solidity / 0.75, rectangularity / 0.65), 0.0, 1.0))
    return {
        "boundary_gradient_strength": boundary,
        "contour_closure_score": closure,
        "solidity": solidity,
        "extent": extent,
        "rectangularity": rectangularity,
        "circularity": circularity,
        "corner_count": corner_count,
    }


def _score_square_metrics(
    boundary_noise_ratio: float,
    closure: float,
    solidity: float,
    extent: float,
    rectangularity: float,
    circularity: float,
    corner_count: int,
    config: dict,
) -> float:
    boundary_score = float(np.clip(boundary_noise_ratio / max(float(config.get("square_min_boundary_gradient_noise_ratio", 1.4)), 1e-6), 0.0, 1.0))
    closure_score = float(np.clip(closure / max(float(config.get("square_min_contour_closure_score", 0.45)), 1e-6), 0.0, 1.0))
    solidity_score = float(np.clip(solidity / max(float(config.get("square_candidate_min_solidity", 0.45)), 1e-6), 0.0, 1.0))
    extent_score = float(np.clip(extent / max(float(config.get("square_candidate_min_extent", 0.35)), 1e-6), 0.0, 1.0))
    rectangularity_score = float(np.clip(rectangularity / max(float(config.get("square_candidate_min_rectangularity", 0.40)), 1e-6), 0.0, 1.0))
    circularity_score = float(np.clip((float(config.get("square_candidate_max_circularity", 0.88)) - circularity) / 0.25, 0.0, 1.0))
    corner_score = 1.0 if int(config.get("square_candidate_min_corners", 4)) <= corner_count <= int(config.get("square_candidate_max_corners", 10)) else 0.0
    return float(
        0.22 * boundary_score
        + 0.18 * closure_score
        + 0.13 * solidity_score
        + 0.13 * extent_score
        + 0.13 * rectangularity_score
        + 0.11 * circularity_score
        + 0.10 * corner_score
    )


def _positive_percentile(values: np.ndarray, percentile: float) -> float:
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]
    source = positive if positive.size else finite
    return float(np.percentile(source, percentile)) if source.size else 0.0


def _candidate_bbox_area(candidate: Candidate) -> int:
    if candidate.bbox_w is not None and candidate.bbox_h is not None:
        return int(candidate.bbox_w * candidate.bbox_h)
    return int(math.pi * candidate.approx_radius_px**2)


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


def nms_candidates(candidates: list[Candidate], config: dict) -> list[Candidate]:
    if not candidates:
        return []
    center_fraction = float(config.get("candidate_nms_center_fraction", 0.5))
    radius_fraction = float(config.get("candidate_nms_radius_fraction", 0.4))
    kept: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: (c.shape_score if c.shape_score is not None else 0.5, c.score), reverse=True):
        duplicate = False
        for other in kept:
            dist = math.hypot(cand.center_x - other.center_x, cand.center_y - other.center_y)
            center_limit = center_fraction * max(cand.approx_radius_px, other.approx_radius_px)
            radius_limit = radius_fraction * max(cand.approx_radius_px, other.approx_radius_px)
            bbox_overlap = _bbox_iou(cand, other)
            if (dist <= center_limit and abs(cand.approx_radius_px - other.approx_radius_px) <= radius_limit) or bbox_overlap >= 0.35:
                duplicate = True
                break
        if not duplicate:
            kept.append(cand)
    return kept


def _bbox_iou(a: Candidate, b: Candidate) -> float:
    ax0, ay0, ax1, ay1 = _candidate_bbox_for_nms(a)
    bx0, by0, bx1, by1 = _candidate_bbox_for_nms(b)
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = float((ix1 - ix0) * (iy1 - iy0))
    area_a = float((ax1 - ax0) * (ay1 - ay0))
    area_b = float((bx1 - bx0) * (by1 - by0))
    return inter / max(area_a + area_b - inter, 1.0)


def _matches_round_candidate(square_candidate: Candidate, round_candidates: list[Candidate], config: dict) -> bool:
    center_fraction = float(config.get("square_gate_round_match_center_fraction", 0.85))
    iou_threshold = float(config.get("square_gate_round_match_iou", 0.20))
    for other in round_candidates:
        if other.shape_type != "round":
            continue
        dist = math.hypot(square_candidate.center_x - other.center_x, square_candidate.center_y - other.center_y)
        if dist <= center_fraction * max(square_candidate.approx_radius_px, other.approx_radius_px):
            return True
        if _bbox_iou(square_candidate, other) >= iou_threshold:
            return True
    return False


def _candidate_bbox_for_nms(c: Candidate) -> tuple[float, float, float, float]:
    if c.bbox_x is not None and c.bbox_y is not None and c.bbox_w is not None and c.bbox_h is not None:
        return float(c.bbox_x), float(c.bbox_y), float(c.bbox_x + c.bbox_w), float(c.bbox_y + c.bbox_h)
    r = float(c.approx_radius_px)
    return c.center_x - r, c.center_y - r, c.center_x + r, c.center_y + r
