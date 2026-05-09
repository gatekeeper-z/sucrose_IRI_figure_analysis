from __future__ import annotations

from pathlib import Path

from .candidates import Candidate
from .contour_refine import RefinedInstance
from .measure import CrystalMeasurement


def build_qc_report(
    image_id: str,
    input_path: str,
    candidates: list[Candidate],
    instances: list[RefinedInstance],
    measurements: list[CrystalMeasurement],
    summary: dict,
) -> str:
    lines = [
        f"IRI analyzer QC report",
        f"image_id: {image_id}",
        f"input_path: {input_path}",
        "",
        "Counts",
        f"- candidates: {len(candidates)}",
        f"- final_instances: {len(measurements)}",
        f"- edge_excluded: {summary.get('n_edge_excluded')}",
        f"- qc_warnings: {summary.get('n_qc_warning')}",
        "",
        "Manual QC checklist",
        "- Check 03_background_estimate.png: should contain large-scale shadow, not clear ice-crystal edges.",
        "- Check 04_flatfield_corrected.png: irregular background should be reduced.",
        "- Check 06_candidate_localization_overlay.png: visible crystals should be covered by candidates.",
        "- Check 10_final_overlay.png: contours should follow actual crystal boundaries.",
        "- Check 11_label_overlay.png: labels should match crystals.csv ids.",
        "- Treat automatic areas as segmentation estimates, not final scientific conclusions.",
        "",
        "Object warnings",
    ]
    warned = [m for m in measurements if m.qc_flag != "ok"]
    if warned:
        for m in warned:
            lines.append(f"- id={m.id}: {m.qc_flag}, area_px2={m.actual_area_px2:.0f}, center=({m.center_x:.1f},{m.center_y:.1f})")
    else:
        lines.append("- none")
    skipped = [inst for inst in instances if inst.skipped]
    lines.extend(["", "Skipped candidates"])
    if skipped:
        for inst in skipped:
            c = inst.candidate
            lines.append(f"- candidate_id={c.candidate_id}: {inst.skip_reason}, center=({c.center_x:.1f},{c.center_y:.1f}), r={c.approx_radius_px:.1f}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Important method notes",
            "- Hough/LoG candidates are used only for localization.",
            "- actual_area_px2 is measured from the final instance mask.",
            "- circle_area_px2 is a reference field only.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_qc_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
