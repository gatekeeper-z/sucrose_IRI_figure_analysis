from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import cv2
import numpy as np


@dataclass
class Candidate:
    candidate_id: int
    center_x: float
    center_y: float
    approx_radius_px: float
    edge_touching: bool
    method: str
    score: float

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


def _edge_touching(x: float, y: float, r: float, shape: tuple[int, int]) -> bool:
    h, w = shape[:2]
    return x - r <= 0 or y - r <= 0 or x + r >= w - 1 or y + r >= h - 1


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
