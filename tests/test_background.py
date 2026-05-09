import numpy as np

from iri_analyzer.background import create_protect_mask, estimate_background_masked, flatfield_correct


def test_masked_background_is_finite_and_same_shape():
    gray = np.tile(np.linspace(80, 160, 80, dtype=np.uint8), (60, 1))
    gray[25:35, 35:45] = 240
    config = {
        "allow_clahe_for_protect_mask": False,
        "median_blur_ksize": 3,
        "protect_gradient_percentile": 88,
        "protect_dilation_px": 3,
        "clahe_clip_limit": 1.5,
        "clahe_tile_grid_size": [16, 16],
    }
    protect = create_protect_mask(gray, config)
    background = estimate_background_masked(gray, protect, sigma_px=10)
    corrected = flatfield_correct(gray, background)
    assert protect.shape == gray.shape
    assert background.shape == gray.shape
    assert corrected.shape == gray.shape
    assert np.isfinite(background).all()
    assert np.isfinite(corrected).all()


def test_background_handles_all_masked_pixels():
    gray = np.full((20, 20), 100, dtype=np.uint8)
    protect = np.ones_like(gray, dtype=bool)
    background = estimate_background_masked(gray, protect, sigma_px=5)
    assert np.isfinite(background).all()
    assert np.all(background >= 1)
