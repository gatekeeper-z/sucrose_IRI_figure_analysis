from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import uuid
import webbrowser
import zipfile

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .io import SUPPORTED_EXTENSIONS, load_config, project_root, safe_image_id, validate_config
from .pipeline import process_image


ROOT = project_root()
WEB_RUNS_DIR = ROOT / "results" / "web_runs"
FRONTEND_DIST = ROOT / "web" / "dist"

PRESETS = {
    "default": None,
    "pva_01_round": ROOT / "config_pva_0509_aggressive_v2.yaml",
    "pva_02_square": ROOT / "config_pva_02_hybrid_v2.yaml",
}

PARAMETER_KEYS = {
    "pixel_size_um",
    "exclude_edge_touching",
    "square_strategy_enabled",
    "adhesion_strategy_enabled",
    "adhesion_split_enabled",
    "background_sigma_px",
    "target_protect_mask_fraction_max",
    "hough_param2",
    "min_radius_px",
    "max_radius_px",
    "min_edge_coverage_fraction",
    "ring_gradient_noise_ratio_min",
    "min_reliable_ray_fraction",
    "radial_search_max_scale",
    "min_area_px2",
    "max_area_px2",
    "square_candidate_min_area_px2",
    "square_candidate_max_area_px2",
    "square_min_boundary_gradient_noise_ratio",
    "square_refine_min_boundary_support",
    "adhesion_min_split_confidence",
}

DOWNLOAD_EXTENSIONS = {".png", ".csv", ".json", ".yaml", ".yml", ".txt"}

app = FastAPI(title="IRI Analyzer Web", version="0.1.0")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_web_runs_dir() -> None:
    WEB_RUNS_DIR.mkdir(parents=True, exist_ok=True)


def job_dir(job_id: str) -> Path:
    if not job_id or any(ch in job_id for ch in "\\/.."):
        raise HTTPException(status_code=404, detail="Job not found")
    path = (WEB_RUNS_DIR / job_id).resolve()
    if WEB_RUNS_DIR.resolve() not in path.parents and path != WEB_RUNS_DIR.resolve():
        raise HTTPException(status_code=403, detail="Invalid path")
    return path


def image_dir_name(image_id: str) -> str:
    if not image_id or "/" in image_id or "\\" in image_id or ".." in image_id:
        raise HTTPException(status_code=403, detail="Invalid image id")
    return image_id


def read_job(job_id: str) -> dict:
    path = job_dir(job_id) / "job.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def write_job(path: Path, job: dict) -> None:
    job["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")


def load_preset_config(preset: str, overrides: dict) -> dict:
    if preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset}")
    config_path = PRESETS[preset]
    config = load_config(str(config_path) if config_path is not None else None)
    clean_overrides = {}
    for key, value in overrides.items():
        if key not in PARAMETER_KEYS or value == "":
            continue
        if value is None and key != "max_area_px2":
            continue
        clean_overrides[key] = value
    if "pixel_size_um" in clean_overrides and clean_overrides["pixel_size_um"] in {"", "null"}:
        clean_overrides["pixel_size_um"] = None
    if "adhesion_strategy_enabled" in clean_overrides and "adhesion_split_enabled" not in clean_overrides:
        clean_overrides["adhesion_split_enabled"] = clean_overrides["adhesion_strategy_enabled"]
    config.update(clean_overrides)
    validate_config(config)
    return config


def parse_parameters(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid parameters JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="parameters must be an object")
    return data


def image_file_url(job_id: str, image_id: str, filename: str) -> str:
    return f"/api/files/{job_id}/{image_id}/{filename}"


def job_summary_row(image_id: str, summary: dict) -> dict:
    return {
        "image_id": image_id,
        "square_strategy_used": summary.get("square_strategy_used"),
        "n_accepted_instances": summary.get("n_accepted_instances"),
        "accepted_total_actual_area_px2": summary.get("accepted_total_actual_area_px2"),
        "accepted_median_area_px2": summary.get("accepted_median_area_px2"),
        "n_qc_warning": summary.get("n_qc_warning"),
        "n_accepted_round_instances": summary.get("n_accepted_round_instances"),
        "n_accepted_square_instances": summary.get("n_accepted_square_instances"),
        "n_accepted_cluster_split_instances": summary.get("n_accepted_cluster_split_instances"),
    }


def write_run_summary(outputs_dir: Path, rows: list[dict]) -> None:
    fields = [
        "image_id",
        "square_strategy_used",
        "n_accepted_instances",
        "accepted_total_actual_area_px2",
        "accepted_median_area_px2",
        "n_qc_warning",
        "n_accepted_round_instances",
        "n_accepted_square_instances",
        "n_accepted_cluster_split_instances",
    ]
    with (outputs_dir.parent / "run_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def process_job(job_id: str) -> None:
    base = job_dir(job_id)
    job_path = base / "job.json"
    job = read_job(job_id)
    job["status"] = "running"
    job["started_at"] = now_iso()
    write_job(job_path, job)

    rows: list[dict] = []
    uploads = job.get("uploads", [])
    for idx, upload in enumerate(uploads, start=1):
        job = read_job(job_id)
        image_id = upload["image_id"]
        job["current_image"] = image_id
        job["processed_images"] = idx - 1
        image_record = next((item for item in job["images"] if item["image_id"] == image_id), None)
        if image_record is not None:
            image_record["status"] = "running"
        write_job(job_path, job)

        try:
            config = load_preset_config(job["preset"], job.get("parameters", {}))
            out_dir = base / "outputs" / image_id
            out_dir.mkdir(parents=True, exist_ok=True)
            result = process_image(upload["path"], config, out_dir)
            summary = result.summary
            rows.append(job_summary_row(image_id, summary))
            job = read_job(job_id)
            image_record = next((item for item in job["images"] if item["image_id"] == image_id), None)
            if image_record is not None:
                image_record.update(
                    {
                        "status": "done",
                        "summary": summary,
                        "processed_at": now_iso(),
                        "thumbnail_url": image_file_url(job_id, image_id, "00_original.png"),
                        "final_overlay_url": image_file_url(job_id, image_id, "10_final_overlay.png"),
                    }
                )
        except Exception as exc:  # keep batch jobs moving
            job = read_job(job_id)
            image_record = next((item for item in job["images"] if item["image_id"] == image_id), None)
            if image_record is not None:
                image_record.update({"status": "error", "error": f"{exc.__class__.__name__}: {exc}"})
            job.setdefault("errors", []).append({"image_id": image_id, "message": f"{exc.__class__.__name__}: {exc}"})
        finally:
            job["processed_images"] = idx
            write_job(job_path, job)

    job = read_job(job_id)
    job["status"] = "done" if not job.get("errors") else "done_with_errors"
    job["finished_at"] = now_iso()
    job["current_image"] = None
    write_run_summary(base / "outputs", rows)
    write_job(job_path, job)


def safe_output_file(job_id: str, image_id: str, filename: str) -> Path:
    if Path(filename).name != filename:
        raise HTTPException(status_code=403, detail="Invalid filename")
    if Path(filename).suffix.lower() not in DOWNLOAD_EXTENSIONS:
        raise HTTPException(status_code=403, detail="Unsupported file")
    path = (job_dir(job_id) / "outputs" / image_dir_name(image_id) / filename).resolve()
    outputs = (job_dir(job_id) / "outputs").resolve()
    if outputs not in path.parents:
        raise HTTPException(status_code=403, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return path


def zip_directory(root: Path, archive_name: str) -> StreamingResponse:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(root.parent))
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    preset: str = Form("default"),
    parameters: str = Form("{}"),
) -> JSONResponse:
    ensure_web_runs_dir()
    overrides = parse_parameters(parameters)
    load_preset_config(preset, overrides)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    base = job_dir(job_id)
    uploads_dir = base / "uploads"
    outputs_dir = base / "outputs"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    uploads = []
    images = []
    seen_ids: set[str] = set()
    for idx, file in enumerate(files, start=1):
        original_name = Path(file.filename or f"image_{idx}").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported image extension: {original_name}")
        stem = safe_image_id(Path(original_name))
        image_id = stem
        if image_id in seen_ids:
            image_id = f"{stem}_{idx:03d}"
        seen_ids.add(image_id)
        upload_path = uploads_dir / f"{image_id}{suffix}"
        with upload_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        uploads.append({"image_id": image_id, "original_name": original_name, "path": str(upload_path)})
        images.append(
            {
                "image_id": image_id,
                "original_name": original_name,
                "status": "queued",
                "thumbnail_url": None,
                "final_overlay_url": None,
                "summary": None,
                "error": None,
            }
        )

    job = {
        "job_id": job_id,
        "status": "queued",
        "preset": preset,
        "parameters": overrides,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "total_images": len(images),
        "processed_images": 0,
        "current_image": None,
        "uploads": uploads,
        "images": images,
        "errors": [],
    }
    write_job(base / "job.json", job)
    background_tasks.add_task(process_job, job_id)
    return JSONResponse({"job_id": job_id, "status": "queued"})


@app.get("/api/jobs")
def list_jobs() -> dict:
    ensure_web_runs_dir()
    jobs = []
    for path in WEB_RUNS_DIR.glob("*/job.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        images = job.get("images", [])
        first = images[0] if images else {}
        jobs.append(
            {
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "preset": job.get("preset"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "finished_at": job.get("finished_at"),
                "total_images": job.get("total_images", len(images)),
                "processed_images": job.get("processed_images", 0),
                "thumbnail_url": first.get("thumbnail_url"),
                "first_image_name": first.get("original_name"),
                "images": images,
            }
        )
    jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"jobs": jobs}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return read_job(job_id)


@app.get("/api/jobs/{job_id}/images/{image_id}")
def get_image(job_id: str, image_id: str) -> dict:
    job = read_job(job_id)
    image = next((item for item in job.get("images", []) if item.get("image_id") == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    output_dir = job_dir(job_id) / "outputs" / image_dir_name(image_id)
    files = sorted(path.name for path in output_dir.iterdir() if path.is_file()) if output_dir.exists() else []
    qc_text = ""
    qc_path = output_dir / "qc_report.txt"
    if qc_path.exists():
        qc_text = qc_path.read_text(encoding="utf-8")
    return {"job": job, "image": image, "files": files, "qc_report": qc_text}


@app.get("/api/files/{job_id}/{image_id}/{filename}")
def get_file(job_id: str, image_id: str, filename: str) -> FileResponse:
    return FileResponse(safe_output_file(job_id, image_id, filename))


@app.get("/api/download/{job_id}")
def download_job(job_id: str) -> StreamingResponse:
    base = job_dir(job_id)
    if not base.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return zip_directory(base, f"{job_id}.zip")


@app.get("/api/download/{job_id}/{image_id}")
def download_image(job_id: str, image_id: str) -> StreamingResponse:
    image_dir = job_dir(job_id) / "outputs" / image_dir_name(image_id)
    if not image_dir.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return zip_directory(image_dir, f"{image_id}.zip")


@app.get("/api/download/{job_id}/{image_id}/{filename}")
def download_file(job_id: str, image_id: str, filename: str) -> FileResponse:
    path = safe_output_file(job_id, image_id, filename)
    return FileResponse(path, filename=path.name)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


def main() -> None:
    import uvicorn

    url = "http://127.0.0.1:8000"
    print(f"IRI Analyzer Web UI: {url}")
    if os.environ.get("IRI_ANALYZER_NO_AUTO_OPEN") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run("iri_analyzer.web:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
