from __future__ import annotations

import cv2
import numpy as np

from .candidates import Candidate
from .preprocess import gradient_magnitude, median_blur, normalize_to_uint8


def create_protect_mask(gray: np.ndarray, config: dict) -> np.ndarray:
    """Create a coarse edge mask used only to protect objects during background estimation."""
    source = gray
    if config.get("allow_clahe_for_protect_mask", False):
        # Kept optional for difficult images; default is false by design.
        from .preprocess import apply_clahe

        source = apply_clahe(gray, config["clahe_clip_limit"], config["clahe_tile_grid_size"])
    blurred = median_blur(source, int(config["median_blur_ksize"]))
    grad = gradient_magnitude(blurred)
    finite = grad[np.isfinite(grad)]
    threshold = np.percentile(finite, float(config["protect_gradient_percentile"])) if finite.size else 0
    mask = grad >= threshold
    dilation = int(config["protect_dilation_px"])
    if dilation > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilation + 1, 2 * dilation + 1))
        mask = cv2.dilate(mask.astype(np.uint8), kernel) > 0
    return mask


def estimate_background_masked(gray: np.ndarray, protect_mask: np.ndarray, sigma_px: float, eps: float = 1e-3) -> np.ndarray:
    """Masked Gaussian normalized convolution background estimate."""
    gray_f = gray.astype(np.float32)
    valid = (~protect_mask).astype(np.float32)
    num = cv2.GaussianBlur(gray_f * valid, (0, 0), sigmaX=float(sigma_px), sigmaY=float(sigma_px))
    den = cv2.GaussianBlur(valid, (0, 0), sigmaX=float(sigma_px), sigmaY=float(sigma_px))
    valid_pixels = gray_f[~protect_mask]
    fallback = float(np.median(valid_pixels)) if valid_pixels.size else float(np.median(gray_f))
    background = num / np.maximum(den, eps)
    background[den < eps] = fallback
    background[~np.isfinite(background)] = fallback
    background = np.maximum(background, 1.0)
    return background.astype(np.float32)


def estimate_background_unmasked(gray: np.ndarray, sigma_px: float) -> np.ndarray:
    background = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), sigmaX=float(sigma_px), sigmaY=float(sigma_px))
    background = np.maximum(background, 1.0)
    return background.astype(np.float32)


def create_candidate_protect_mask(candidates: list[Candidate], shape: tuple[int, int], config: dict) -> tuple[np.ndarray, list[Candidate], float]:
    """Create a protect mask from candidate circles, capped by target mask fraction."""
    h, w = shape[:2]
    target_max = float(config.get("target_protect_mask_fraction_max", 0.45))
    radius_scale = float(config.get("candidate_protect_radius_scale", 1.3))
    radius_extra = float(config.get("candidate_protect_radius_extra_px", 3))
    mask = np.zeros((h, w), dtype=np.uint8)
    used: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        trial = mask.copy()
        radius = int(round(cand.approx_radius_px * radius_scale + radius_extra))
        cv2.circle(trial, (int(round(cand.center_x)), int(round(cand.center_y))), max(radius, 1), 1, -1)
        frac = float(np.mean(trial > 0))
        if frac > target_max and used:
            continue
        mask = trial
        used.append(cand)
        if float(np.mean(mask > 0)) >= target_max:
            break
    return mask.astype(bool), used, float(np.mean(mask > 0))


def flatfield_correct(gray: np.ndarray, background: np.ndarray) -> np.ndarray:
    gray_f = gray.astype(np.float32)
    bg = np.maximum(background.astype(np.float32), 1.0)
    scale = float(np.median(bg[np.isfinite(bg)]))
    corrected = gray_f / bg * scale
    corrected[~np.isfinite(corrected)] = 0
    return corrected.astype(np.float32)


def background_visual(background: np.ndarray) -> np.ndarray:
    return normalize_to_uint8(background, percentile_clip=(1, 99))


def corrected_visual(corrected: np.ndarray) -> np.ndarray:
    return normalize_to_uint8(corrected, percentile_clip=(0.5, 99.5))
