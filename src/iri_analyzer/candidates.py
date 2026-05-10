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

    def to_dict(self, image_id: str) -> dict:
        row = asdict(self)
        row["image_id"] = image_id
        return row


def detect_candidates(gray: np.ndarray, config: dict) -> list[Candidate]:
    method = str(config.get("candidate_method", "hough")).lower()
    if method == "log":
        candidates = _detect_log(gray, config)
    elif method == "hough":
        candidates = _detect_hough(gray, config)
    else:
        raise ValueError(f"Unsupported candidate_method: {method}")
    candidates = _nms(candidates, config)
    for idx, cand in enumerate(candidates, start=1):
        cand.candidate_id = idx
    return candidates


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
                )
            )
    return candidates


def _nms(candidates: list[Candidate], config: dict) -> list[Candidate]:
    if not candidates:
        return []
    center_fraction = float(config.get("candidate_nms_center_fraction", 0.5))
    radius_fraction = float(config.get("candidate_nms_radius_fraction", 0.4))
    kept: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        duplicate = False
        for other in kept:
            dist = math.hypot(cand.center_x - other.center_x, cand.center_y - other.center_y)
            center_limit = center_fraction * max(cand.approx_radius_px, other.approx_radius_px)
            radius_limit = radius_fraction * max(cand.approx_radius_px, other.approx_radius_px)
            if dist <= center_limit and abs(cand.approx_radius_px - other.approx_radius_px) <= radius_limit:
                duplicate = True
                break
        if not duplicate:
            kept.append(cand)
    return kept
