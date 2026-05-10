import numpy as np

from iri_analyzer.candidates import Candidate, validate_candidates


def test_candidate_validation_rejects_weak_blank_candidate():
    gray = np.full((80, 80), 120, dtype=np.uint8)
    candidates = [Candidate(1, 40, 40, 12, False, "hough", 1.0)]
    config = {
        "candidate_validation_enabled": True,
        "contour_n_angles": 72,
        "min_radius_px": 5,
        "max_radius_px": 30,
        "exclude_edge_touching": True,
        "min_edge_coverage_fraction": 0.45,
        "ring_gradient_noise_ratio_min": 1.5,
        "inside_outside_contrast_min": None,
    }
    accepted, rejected = validate_candidates(gray, candidates, config)
    assert not accepted
    assert len(rejected) == 1
    assert "low_edge_coverage" in rejected[0].reject_reason
