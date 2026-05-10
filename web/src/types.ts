export type Preset = "default" | "pva_01_round" | "pva_02_square";
export type StrategyMode = "auto" | "true" | "false";
export type Page = "analyze" | "history" | "result";

export interface Parameters {
  pixel_size_um: string;
  exclude_edge_touching: boolean;
  square_strategy_enabled: StrategyMode;
  adhesion_strategy_enabled: StrategyMode;
  background_sigma_px: number;
  target_protect_mask_fraction_max: number;
  hough_param2: number;
  min_radius_px: number;
  max_radius_px: number;
  min_edge_coverage_fraction: number;
  ring_gradient_noise_ratio_min: number;
  min_reliable_ray_fraction: number;
  radial_search_max_scale: number;
  min_area_px2: number;
  max_area_px2: string;
  square_candidate_min_area_px2: number;
  square_candidate_max_area_px2: number;
  square_min_boundary_gradient_noise_ratio: number;
  square_refine_min_boundary_support: number;
  adhesion_min_split_confidence: number;
}

export interface ImageSummary {
  image_id: string;
  original_name: string;
  status: string;
  thumbnail_url?: string | null;
  final_overlay_url?: string | null;
  processed_at?: string | null;
  error?: string | null;
  summary?: Record<string, unknown> | null;
}

export interface Job {
  job_id: string;
  status: string;
  preset: Preset;
  parameters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  total_images: number;
  processed_images: number;
  current_image?: string | null;
  images: ImageSummary[];
  errors: Array<{ image_id?: string; message: string }>;
}

export interface JobListItem {
  job_id: string;
  status: string;
  preset: Preset;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
  total_images: number;
  processed_images: number;
  thumbnail_url?: string | null;
  first_image_name?: string | null;
  images: ImageSummary[];
}

export interface ImageDetail {
  job: Job;
  image: ImageSummary;
  files: string[];
  qc_report: string;
}
