import json

from fastapi.testclient import TestClient

from iri_analyzer import web


def test_web_parameter_overrides_are_applied():
    config = web.load_preset_config(
        "default",
        {
            "hough_param2": 57,
            "min_reliable_ray_fraction": 0.62,
            "radial_search_max_scale": 1.22,
            "max_area_px2": None,
            "square_strategy_enabled": "false",
            "ignored_key": 123,
        },
    )
    assert config["hough_param2"] == 57
    assert config["min_reliable_ray_fraction"] == 0.62
    assert config["radial_search_max_scale"] == 1.22
    assert config["max_area_px2"] is None
    assert config["square_strategy_enabled"] == "false"
    assert "ignored_key" not in config


def test_web_create_job_and_history(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "WEB_RUNS_DIR", tmp_path / "web_runs")

    def fake_process_job(job_id: str):
        job = web.read_job(job_id)
        job["status"] = "done"
        job["processed_images"] = job["total_images"]
        for image in job["images"]:
            image["status"] = "done"
            image["processed_at"] = web.now_iso()
        web.write_job(web.job_dir(job_id) / "job.json", job)

    monkeypatch.setattr(web, "process_job", fake_process_job)
    client = TestClient(web.app)
    response = client.post(
        "/api/jobs",
        data={"preset": "default", "parameters": "{}"},
        files={"files": ("sample.bmp", b"fake-bmp", "image/bmp")},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done"
    history = client.get("/api/jobs").json()
    assert history["jobs"][0]["job_id"] == job_id


def test_web_file_download_stays_inside_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "WEB_RUNS_DIR", tmp_path / "web_runs")
    job_id = "20260510_120000_test"
    image_id = "0.2_PVA_test"
    out_dir = web.WEB_RUNS_DIR / job_id / "outputs" / image_id
    out_dir.mkdir(parents=True)
    (out_dir / "summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (web.WEB_RUNS_DIR / job_id / "job.json").write_text(json.dumps({"job_id": job_id, "images": []}), encoding="utf-8")

    client = TestClient(web.app)
    ok = client.get(f"/api/download/{job_id}/{image_id}/summary.json")
    assert ok.status_code == 200
    blocked = client.get(f"/api/download/{job_id}/{image_id}/..%2Fjob.json")
    assert blocked.status_code in {403, 404}
