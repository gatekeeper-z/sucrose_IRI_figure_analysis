import numpy as np

from iri_analyzer.candidates import Candidate
from iri_analyzer.contour_refine import RefinedInstance
from iri_analyzer.measure import measure_instances, summarize


def test_actual_area_comes_from_instance_mask_not_circle():
    mask = np.zeros((30, 30), dtype=bool)
    mask[5:15, 7:20] = True
    candidate = Candidate(1, 12, 10, 8, False, "hough", 1.0)
    inst = RefinedInstance(
        candidate=candidate,
        mask=mask,
        contour_points=np.empty((0, 2), dtype=np.float32),
        radial_radii=np.array([6, 7, 8, 9], dtype=np.float32),
        valid_fraction=1.0,
        overlap_trimmed_fraction=0.0,
        skipped=False,
    )
    config = {
        "pixel_size_um": 0.5,
        "max_overlap_qc_fraction": 0.30,
        "min_area_px2": 20,
        "max_area_px2": None,
    }
    measured = measure_instances("img", [inst], config)[0]
    assert measured.actual_area_px2 == int(np.count_nonzero(mask))
    assert measured.actual_area_px2 != round(measured.circle_area_px2)
    assert measured.actual_area_um2 == measured.actual_area_px2 * 0.25


def test_summary_total_is_sum_of_actual_mask_areas():
    mask1 = np.zeros((20, 20), dtype=bool)
    mask2 = np.zeros((20, 20), dtype=bool)
    mask1[1:4, 1:4] = True
    mask2[5:10, 5:11] = True
    config = {
        "pixel_size_um": None,
        "max_overlap_qc_fraction": 0.30,
        "min_area_px2": 1,
        "max_area_px2": None,
    }
    instances = []
    for idx, mask in enumerate([mask1, mask2], start=1):
        instances.append(
            RefinedInstance(
                candidate=Candidate(idx, 5, 5, 4, False, "hough", 1.0),
                mask=mask,
                contour_points=np.empty((0, 2), dtype=np.float32),
                radial_radii=np.array([4, 4, 4], dtype=np.float32),
                valid_fraction=1.0,
                overlap_trimmed_fraction=0.0,
                skipped=False,
            )
        )
    measurements = measure_instances("img", instances, config)
    summary = summarize("img", "input.bmp", (20, 20), 2, 0, measurements, config)
    assert summary["raw_total_actual_area_px2"] == sum(np.count_nonzero(m.mask) for m in instances)
    assert summary["accepted_total_actual_area_px2"] == sum(m.actual_area_px2 for m in measurements if m.accepted)
    assert summary["total_actual_area_px2"] == summary["accepted_total_actual_area_px2"]


def test_qc_warning_is_excluded_from_accepted_summary():
    mask = np.zeros((20, 20), dtype=bool)
    mask[1:4, 1:4] = True
    config = {
        "pixel_size_um": None,
        "max_overlap_qc_fraction": 0.30,
        "min_area_px2": 1,
        "max_area_px2": None,
        "exclude_qc_warning_from_accepted": True,
    }
    inst = RefinedInstance(
        candidate=Candidate(1, 5, 5, 4, False, "hough", 1.0),
        mask=mask,
        contour_points=np.empty((0, 2), dtype=np.float32),
        radial_radii=np.array([4, 4, 4], dtype=np.float32),
        valid_fraction=1.0,
        overlap_trimmed_fraction=0.0,
        skipped=False,
    )
    measurements = measure_instances("img", [inst], config)
    summary = summarize("img", "input.bmp", (20, 20), 1, 0, measurements, config)
    assert measurements[0].qc_flag != "ok"
    assert not measurements[0].accepted
    assert summary["raw_total_actual_area_px2"] == 9
    assert summary["accepted_total_actual_area_px2"] == 0
