import cv2
import numpy as np

from iri_analyzer.candidates import Candidate
from iri_analyzer.contour_refine import refine_candidate, refine_candidates


def _ellipse_gradient(shape=(100, 100), center=(50, 50), axes=(24, 14)):
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, 1)
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.0)


def test_radial_refinement_returns_non_circular_mask_area():
    gradient = _ellipse_gradient()
    candidate = Candidate(1, 50, 50, 20, False, "hough", 1.0)
    config = {
        "contour_n_angles": 96,
        "radial_search_min_scale": 0.55,
        "radial_search_max_scale": 1.45,
        "radial_search_extra_px": 5,
        "radial_peak_nearmax_fraction": 0.78,
        "radial_smoothing_sigma": 1.0,
        "min_valid_radial_fraction": 0.60,
    }
    inst = refine_candidate(gradient, candidate, config)
    area = int(np.count_nonzero(inst.mask))
    circle_area = np.pi * candidate.approx_radius_px**2
    assert area > 0
    assert abs(area - circle_area) > 100
    assert inst.contour_points.shape == (96, 2)


def test_overlap_skip_marks_second_instance():
    image = _ellipse_gradient()
    candidates = [
        Candidate(1, 50, 50, 20, False, "hough", 2.0),
        Candidate(2, 51, 50, 20, False, "hough", 1.0),
    ]
    config = {
        "contour_n_angles": 72,
        "radial_search_min_scale": 0.55,
        "radial_search_max_scale": 1.45,
        "radial_search_extra_px": 5,
        "radial_peak_nearmax_fraction": 0.78,
        "radial_smoothing_sigma": 1.0,
        "max_overlap_skip_fraction": 0.55,
        "min_valid_radial_fraction": 0.60,
    }
    instances = refine_candidates(image.astype(np.uint8), candidates, config)
    assert len(instances) == 2
    assert instances[1].skipped
    assert instances[1].skip_reason == "overlap_skip"
