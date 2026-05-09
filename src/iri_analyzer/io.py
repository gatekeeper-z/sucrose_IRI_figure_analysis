from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import shutil

import cv2
import pandas as pd
import yaml


SUPPORTED_EXTENSIONS = {".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(config_path: str | None = None) -> dict:
    default_path = project_root() / "config_default.yaml"
    with default_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if config_path:
        with Path(config_path).open("r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        config.update(user_config)
    return config


def validate_config(config: dict) -> None:
    positive = [
        "background_sigma_px",
        "hough_dp",
        "hough_min_dist_px",
        "min_radius_px",
        "max_radius_px",
        "contour_n_angles",
        "radial_search_min_scale",
        "radial_search_max_scale",
    ]
    for key in positive:
        if float(config[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if int(config["min_radius_px"]) >= int(config["max_radius_px"]):
        raise ValueError("min_radius_px must be smaller than max_radius_px")
    pixel_size = config.get("pixel_size_um")
    if pixel_size is not None and float(pixel_size) <= 0:
        raise ValueError("pixel_size_um must be positive when provided")
    config["pixel_size_um"] = float(pixel_size) if pixel_size is not None else None


def read_image(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Unable to read image: {path}")
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    if image.ndim == 3 and image.shape[2] == 4:
        return image
    if image.ndim == 2:
        return image
    raise ValueError(f"Unsupported image shape for {path}: {image.shape}")


def collect_images(input_path: str | Path) -> list[Path]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported input extension: {path.suffix}")
        return [path]
    images = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)
    return images


def safe_image_id(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem)


def prepare_image_output_dir(output_root: str | Path, image_id: str, overwrite: bool) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    out_dir = root / image_id
    if out_dir.exists():
        if not overwrite and any(out_dir.iterdir()):
            raise FileExistsError(f"Output folder already exists and is not empty: {out_dir}")
        if overwrite:
            shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def write_dataframe(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
