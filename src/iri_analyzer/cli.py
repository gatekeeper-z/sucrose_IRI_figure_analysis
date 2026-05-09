from __future__ import annotations

import argparse
import sys

import numpy as np

from .io import load_config, validate_config
from .pipeline import run_batch, run_qc, run_sensitivity


def parse_bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze actual contour area of ice crystals in sucrose IRI microscopy images.")
    parser.add_argument("--input", required=True, help="Input image or image folder.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--mode", required=True, choices=["qc", "batch", "sensitivity"], help="Run mode.")
    parser.add_argument("--config", default=None, help="Optional YAML config path.")
    parser.add_argument("--pixel-size-um", type=float, default=None, help="Microscope calibration in micrometers per pixel.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing per-image output folders.")
    parser.add_argument("--exclude-edge-touching", type=parse_bool, default=None, help="true/false; exclude edge-touching candidates from final statistics.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.pixel_size_um is not None:
        config["pixel_size_um"] = args.pixel_size_um
    if args.exclude_edge_touching is not None:
        config["exclude_edge_touching"] = args.exclude_edge_touching
    validate_config(config)
    np.random.seed(int(config.get("seed", 0)))
    if args.mode == "qc":
        run_qc(args.input, args.output, config, overwrite=args.overwrite)
    elif args.mode == "batch":
        run_batch(args.input, args.output, config, overwrite=args.overwrite)
    elif args.mode == "sensitivity":
        run_sensitivity(args.input, args.output, config, overwrite=args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
