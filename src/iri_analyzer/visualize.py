from __future__ import annotations

from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np

from .candidates import Candidate
from .contour_refine import RefinedInstance
from .measure import CrystalMeasurement
from .preprocess import normalize_to_uint8


def save_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = image
    if img.dtype == bool:
        img = img.astype(np.uint8) * 255
    elif img.dtype != np.uint8:
        img = normalize_to_uint8(img, percentile_clip=(0.5, 99.5))
    cv2.imwrite(str(path), img)


def ensure_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(normalize_to_uint8(image), cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image.copy()


def candidate_overlay(base: np.ndarray, candidates: list[Candidate], color_override: tuple[int, int, int] | None = None) -> np.ndarray:
    out = ensure_bgr(base)
    for cand in candidates:
        color = color_override if color_override is not None else ((0, 165, 255) if cand.edge_touching else (0, 255, 0))
        center = (int(round(cand.center_x)), int(round(cand.center_y)))
        radius = int(round(cand.approx_radius_px))
        if cand.bbox_x is not None and cand.bbox_y is not None and cand.bbox_w is not None and cand.bbox_h is not None:
            cv2.rectangle(
                out,
                (int(cand.bbox_x), int(cand.bbox_y)),
                (int(cand.bbox_x + cand.bbox_w), int(cand.bbox_y + cand.bbox_h)),
                color,
                1,
                lineType=cv2.LINE_AA,
            )
        else:
            cv2.circle(out, center, radius, color, 1, lineType=cv2.LINE_AA)
        cv2.circle(out, center, 2, (0, 0, 255), -1, lineType=cv2.LINE_AA)
        cv2.putText(out, str(cand.candidate_id), (center[0] + 3, center[1] - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    return out


def contour_points_overlay(base: np.ndarray, instances: list[RefinedInstance]) -> np.ndarray:
    out = ensure_bgr(base)
    for inst in instances:
        if inst.contour_points.size == 0:
            continue
        color = (0, 0, 255) if inst.skipped else (255, 0, 255)
        pts = np.round(inst.contour_points).astype(np.int32)
        cv2.polylines(out, [pts], True, color, 1, lineType=cv2.LINE_AA)
        for p in pts[:: max(1, len(pts) // 24)]:
            cv2.circle(out, tuple(p), 1, color, -1)
    return out


def radial_points_overlay(base: np.ndarray, instances: list[RefinedInstance], point_kind: str) -> np.ndarray:
    out = ensure_bgr(base)
    color = (0, 255, 0) if point_kind == "reliable" else (0, 0, 255)
    for inst in instances:
        pts = inst.reliable_points if point_kind == "reliable" else inst.rejected_points
        if pts is None or pts.size == 0:
            continue
        pts_i = np.round(pts).astype(np.int32)
        for p in pts_i:
            cv2.circle(out, tuple(p), 1, color, -1, lineType=cv2.LINE_AA)
    return out


def label_mask(instances: list[RefinedInstance], shape: tuple[int, int], measurements: list[CrystalMeasurement] | None = None) -> np.ndarray:
    labels = np.zeros(shape[:2], dtype=np.uint16)
    by_candidate_id = {m.candidate_id: m for m in measurements or []}
    for inst in instances:
        if inst.skipped:
            continue
        measurement = by_candidate_id.get(inst.candidate.candidate_id)
        if measurement is not None:
            if not measurement.accepted:
                continue
            labels[inst.mask] = int(measurement.id)
        elif measurements is None:
            labels[inst.mask] = int(labels.max()) + 1
    return labels


def colorize_labels(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((*labels.shape, 3), dtype=np.uint8)
    for label in np.unique(labels):
        if label == 0:
            continue
        label_i = int(label)
        color = np.array([(37 * label_i) % 255, (97 * label_i) % 255, (173 * label_i) % 255], dtype=np.uint8)
        out[labels == label] = color
    return out


def final_overlay(base: np.ndarray, instances: list[RefinedInstance], measurements: list[CrystalMeasurement]) -> np.ndarray:
    out = ensure_bgr(base)
    by_candidate_id = {m.candidate_id: m for m in measurements}
    for inst in instances:
        if inst.skipped:
            continue
        measurement = by_candidate_id.get(inst.candidate.candidate_id)
        if measurement is not None and not measurement.accepted:
            continue
        contours, _ = cv2.findContours(inst.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (0, 255, 255), 1, lineType=cv2.LINE_AA)
        if measurement is not None:
            c = inst.candidate
            cv2.putText(out, str(measurement.id), (int(c.center_x) + 3, int(c.center_y) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    return out


def label_overlay(base: np.ndarray, labels: np.ndarray) -> np.ndarray:
    base_bgr = ensure_bgr(base)
    colors = colorize_labels(labels)
    blended = cv2.addWeighted(base_bgr, 0.70, colors, 0.30, 0)
    for label in np.unique(labels):
        if label == 0:
            continue
        ys, xs = np.where(labels == label)
        if xs.size:
            cv2.putText(blended, str(int(label)), (int(np.mean(xs)), int(np.mean(ys))), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return blended


def save_area_histogram(path: Path, measurements: list[CrystalMeasurement]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    areas = [m.actual_area_px2 for m in measurements]
    plt.figure(figsize=(5, 3.5))
    if areas:
        plt.hist(areas, bins=min(20, max(5, len(areas))))
    else:
        plt.text(0.5, 0.5, "No final instances", ha="center", va="center")
        plt.xlim(0, 1)
        plt.ylim(0, 1)
    plt.xlabel("actual_area_px2")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
