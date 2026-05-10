import type { ImageDetail, Job, JobListItem, Parameters, Preset } from "./types";

export const api = {
  async createJob(files: File[], preset: Preset, parameters: Parameters) {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("preset", preset);
    form.append("parameters", JSON.stringify(toApiParameters(parameters)));
    const response = await fetch("/api/jobs", { method: "POST", body: form });
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as { job_id: string; status: string };
  },

  async listJobs() {
    const response = await fetch("/api/jobs");
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as { jobs: JobListItem[] };
  },

  async getJob(jobId: string) {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as Job;
  },

  async getImage(jobId: string, imageId: string) {
    const response = await fetch(`/api/jobs/${jobId}/images/${imageId}`);
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as ImageDetail;
  }
};

export function fileUrl(jobId: string, imageId: string, filename: string) {
  return `/api/files/${jobId}/${imageId}/${filename}`;
}

export function downloadJobUrl(jobId: string) {
  return `/api/download/${jobId}`;
}

export function downloadImageUrl(jobId: string, imageId: string) {
  return `/api/download/${jobId}/${imageId}`;
}

export function downloadFileUrl(jobId: string, imageId: string, filename: string) {
  return `/api/download/${jobId}/${imageId}/${filename}`;
}

function toApiParameters(parameters: Parameters) {
  return {
    pixel_size_um: parameters.pixel_size_um === "" ? null : Number(parameters.pixel_size_um),
    exclude_edge_touching: parameters.exclude_edge_touching,
    square_strategy_enabled: parameters.square_strategy_enabled,
    adhesion_strategy_enabled: parameters.adhesion_strategy_enabled,
    background_sigma_px: Number(parameters.background_sigma_px),
    target_protect_mask_fraction_max: Number(parameters.target_protect_mask_fraction_max),
    hough_param2: Number(parameters.hough_param2),
    min_radius_px: Number(parameters.min_radius_px),
    max_radius_px: Number(parameters.max_radius_px),
    min_edge_coverage_fraction: Number(parameters.min_edge_coverage_fraction),
    ring_gradient_noise_ratio_min: Number(parameters.ring_gradient_noise_ratio_min),
    min_reliable_ray_fraction: Number(parameters.min_reliable_ray_fraction),
    radial_search_max_scale: Number(parameters.radial_search_max_scale),
    min_area_px2: Number(parameters.min_area_px2),
    max_area_px2: parameters.max_area_px2 === "" ? null : Number(parameters.max_area_px2),
    square_candidate_min_area_px2: Number(parameters.square_candidate_min_area_px2),
    square_candidate_max_area_px2: Number(parameters.square_candidate_max_area_px2),
    square_min_boundary_gradient_noise_ratio: Number(parameters.square_min_boundary_gradient_noise_ratio),
    square_refine_min_boundary_support: Number(parameters.square_refine_min_boundary_support),
    adhesion_min_split_confidence: Number(parameters.adhesion_min_split_confidence)
  };
}
