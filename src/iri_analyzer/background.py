from __future__ import annotations

import cv2
import numpy as np

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
