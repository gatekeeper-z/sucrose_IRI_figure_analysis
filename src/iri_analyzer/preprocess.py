from __future__ import annotations

import cv2
import numpy as np


def to_gray(image: np.ndarray) -> np.ndarray:
    """Convert an image to uint8 grayscale."""
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {image.shape}")
    return normalize_to_uint8(gray)


def normalize_to_uint8(image: np.ndarray, percentile_clip: tuple[float, float] | None = None) -> np.ndarray:
    arr = image.astype(np.float32, copy=False)
    if percentile_clip is not None:
        lo, hi = np.percentile(arr[np.isfinite(arr)], percentile_clip)
    else:
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    out = np.clip((arr - lo) / (hi - lo), 0, 1) * 255.0
    return out.astype(np.uint8)


def median_blur(gray: np.ndarray, ksize: int) -> np.ndarray:
    ksize = int(ksize)
    if ksize <= 1:
        return gray.copy()
    if ksize % 2 == 0:
        ksize += 1
    return cv2.medianBlur(gray, ksize)


def gradient_magnitude(gray: np.ndarray, method: str = "scharr") -> np.ndarray:
    gray_f = gray.astype(np.float32)
    if method == "scharr":
        gx = cv2.Scharr(gray_f, cv2.CV_32F, 1, 0)
        gy = cv2.Scharr(gray_f, cv2.CV_32F, 0, 1)
    else:
        gx = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def apply_clahe(gray: np.ndarray, clip_limit: float, tile_grid_size: list[int] | tuple[int, int]) -> np.ndarray:
    tile = tuple(int(v) for v in tile_grid_size)
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=tile)
    return clahe.apply(normalize_to_uint8(gray, percentile_clip=(0.5, 99.5)))
