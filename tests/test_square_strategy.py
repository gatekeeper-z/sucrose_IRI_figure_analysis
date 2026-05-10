import cv2
import numpy as np

from iri_analyzer.candidates import Candidate, run_square_preflight
from iri_analyzer.contour_refine import RefinedInstance, _maybe_split_adhesion, refine_square_candidate


def _square_config(**overrides):
    config = {
        "min_radius_px": 3,
        "max_radius_px": 30,
        "square_strategy_enabled": "auto",
        "square_preflight_enabled": True,
        "square_gate_min_candidates": 2,
        "square_gate_min_candidate_fraction": 0.10,
        "square_gate_min_area_fraction": 0.001,
        "square_gate_min_score": 0.30,
        "square_candidate_gradient_percentile": 85,
        "square_candidate_close_px": 1,
        "square_candidate_dilation_px": 1,
        "square_candidate_min_area_px2": 20,
        "square_candidate_max_area_px2": 2000,
        "square_candidate_min_extent": 0.20,
        "square_candidate_min_solidity": 0.35,
        "square_candidate_min_rectangularity": 0.30,
        "square_candidate_max_aspect_ratio": 4.0,
        "square_candidate_min_corners": 4,
        "square_candidate_max_corners": 12,
        "square_preflight_min_shape_score": 0.20,
        "square_min_boundary_gradient_noise_ratio": 1.2,
        "square_min_contour_closure_score": 0.30,
        "square_refine_roi_padding_px": 4,
        "square_refine_gradient_percentile": 75,
        "square_refine_close_px": 1,
        "square_refine_min_boundary_support": 0.35,
        "square_refine_allow_convex_hull_fallback": True,
        "square_refine_hull_fallback_max_area_increase": 0.25,
        "max_overlap_skip_fraction": 0.55,
    }
    config.update(overrides)
    return config


def test_square_preflight_auto_triggers_on_square_like_image():
    image = np.zeros((100, 100), dtype=np.uint8)
    for x, y in [(8, 8), (38, 8), (8, 42)]:
        cv2.rectangle(image, (x, y), (x + 18, y + 18), 255, 1)
    square_candidates, gate = run_square_preflight(image, [], _square_config())
    assert gate["square_strategy_used"]
    assert len(square_candidates) >= 2


def test_square_preflight_does_not_trigger_when_disabled():
    image = np.zeros((80, 80), dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (40, 40), 255, 1)
    _, gate = run_square_preflight(image, [], _square_config(square_strategy_enabled="false"))
    assert not gate["square_strategy_used"]
    assert gate["square_gate_reason"] == "disabled"


def test_square_preflight_uses_unmatched_candidates_for_auto_gate():
    image = np.zeros((100, 100), dtype=np.uint8)
    centers = [(17, 17), (47, 17), (17, 51)]
    for cx, cy in centers:
        cv2.rectangle(image, (cx - 9, cy - 9), (cx + 9, cy + 9), 255, 1)
    round_candidates = [Candidate(i, cx, cy, 13, False, "hough", 1.0) for i, (cx, cy) in enumerate(centers, start=1)]
    _, gate = run_square_preflight(image, round_candidates, _square_config(square_gate_min_candidates=2))
    assert not gate["square_strategy_used"]
    assert gate["n_square_like_preflight_candidates_matched_round"] > 0


def test_square_refinement_uses_contour_mask_not_bbox_area():
    gradient = np.zeros((80, 80), dtype=np.float32)
    pts = np.array([[40, 18], [58, 40], [40, 60], [22, 40]], dtype=np.int32)
    cv2.polylines(gradient, [pts], True, 255, 2)
    candidate = Candidate(
        1,
        40,
        40,
        20,
        False,
        "contour_square",
        1.0,
        shape_type="polygonal",
        bbox_x=20,
        bbox_y=16,
        bbox_w=40,
        bbox_h=46,
        local_noise_level=1.0,
    )
    inst = refine_square_candidate(gradient, candidate, _square_config(min_area_px2=20))
    area = int(np.count_nonzero(inst.mask))
    assert area > 0
    assert area != candidate.bbox_w * candidate.bbox_h


def test_adhesion_split_separates_touching_mask_when_confident():
    mask = np.zeros((80, 80), dtype=bool)
    cv2.circle(mask.view(np.uint8), (32, 40), 14, 1, -1)
    cv2.circle(mask.view(np.uint8), (48, 40), 14, 1, -1)
    candidate = Candidate(1, 40, 40, 18, False, "contour_square", 1.0, shape_type="cluster")
    inst = RefinedInstance(
        candidate=candidate,
        mask=mask,
        contour_points=np.empty((0, 2), dtype=np.float32),
        radial_radii=np.array([18], dtype=np.float32),
        valid_fraction=1.0,
        overlap_trimmed_fraction=0.0,
        skipped=False,
        refine_method="contour_square",
    )
    children = _maybe_split_adhesion(
        inst,
        {
            "_adhesion_strategy_used": True,
            "adhesion_min_parent_area_px2": 100,
            "adhesion_max_parent_area_px2": 3000,
            "adhesion_min_distance_peaks": 2,
            "adhesion_max_distance_peaks": 4,
            "adhesion_min_split_confidence": 0.50,
            "adhesion_child_min_area_px2": 50,
            "adhesion_child_max_area_ratio": 0.90,
            "adhesion_peak_distance_fraction": 0.45,
        },
    )
    assert len(children) >= 2
    assert all(child.cluster_split for child in children)
