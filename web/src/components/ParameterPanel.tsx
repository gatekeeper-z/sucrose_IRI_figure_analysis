import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import type { Parameters, Preset, StrategyMode } from "../types";

interface Props {
  activePreset: Preset | null;
  parameters: Parameters;
  onPreset: (preset: Preset) => void;
  onParameters: (parameters: Parameters) => void;
}

export const defaultParameters: Parameters = {
  pixel_size_um: "",
  exclude_edge_touching: true,
  square_strategy_enabled: "auto",
  adhesion_strategy_enabled: "auto",
  background_sigma_px: 80,
  target_protect_mask_fraction_max: 0.45,
  hough_param2: 40,
  min_radius_px: 5,
  max_radius_px: 35,
  min_edge_coverage_fraction: 0.45,
  ring_gradient_noise_ratio_min: 1.5,
  min_reliable_ray_fraction: 0.55,
  radial_search_max_scale: 1.45,
  min_area_px2: 20,
  max_area_px2: "",
  square_candidate_min_area_px2: 40,
  square_candidate_max_area_px2: 2500,
  square_min_boundary_gradient_noise_ratio: 1.4,
  square_refine_min_boundary_support: 0.45,
  adhesion_min_split_confidence: 0.55
};

export const presetParameterDefaults: Record<Preset, Parameters> = {
  default: defaultParameters,
  pva_01_round: {
    ...defaultParameters,
    hough_param2: 46,
    max_radius_px: 30,
    radial_search_max_scale: 1.16,
    max_area_px2: "3200"
  },
  pva_02_square: {
    ...defaultParameters,
    hough_param2: 46,
    max_radius_px: 30,
    min_edge_coverage_fraction: 0.5,
    ring_gradient_noise_ratio_min: 1.6,
    min_reliable_ray_fraction: 0.58,
    radial_search_max_scale: 1.12,
    min_area_px2: 40,
    max_area_px2: "3200",
    square_candidate_min_area_px2: 55,
    square_candidate_max_area_px2: 2200,
    square_min_boundary_gradient_noise_ratio: 1.25,
    square_refine_min_boundary_support: 0.36,
    adhesion_min_split_confidence: 0.56
  }
};

export default function ParameterPanel({ activePreset, parameters, onPreset, onParameters }: Props) {
  const [advanced, setAdvanced] = useState(false);

  function patch(values: Partial<Parameters>) {
    onParameters({ ...parameters, ...values });
  }

  return (
    <section className="panel parameter-panel">
      <div className="panel-title">
        <SlidersHorizontal size={18} />
        <span>参数</span>
      </div>

      <div className="control-group">
        <label>配置预设</label>
        <div className="segmented">
          <button className={activePreset === "default" ? "selected" : ""} onClick={() => onPreset("default")}>默认</button>
          <button className={activePreset === "pva_01_round" ? "selected" : ""} onClick={() => onPreset("pva_01_round")}>0.1 PVA</button>
          <button className={activePreset === "pva_02_square" ? "selected" : ""} onClick={() => onPreset("pva_02_square")}>0.2 PVA</button>
        </div>
      </div>

      <div className="form-grid">
        <label>
          <span>像素尺寸 um/px</span>
          <input value={parameters.pixel_size_um} placeholder="可留空" onChange={(e) => patch({ pixel_size_um: e.target.value })} />
        </label>
        <label className="switch-row">
          <span>排除贴边对象</span>
          <input type="checkbox" checked={parameters.exclude_edge_touching} onChange={(e) => patch({ exclude_edge_touching: e.target.checked })} />
        </label>
      </div>

      <ModeControl label="方形策略" value={parameters.square_strategy_enabled} onChange={(value) => patch({ square_strategy_enabled: value })} />
      <ModeControl label="粘连分裂" value={parameters.adhesion_strategy_enabled} onChange={(value) => patch({ adhesion_strategy_enabled: value })} />

      <button className="text-button" onClick={() => setAdvanced(!advanced)}>
        {advanced ? "收起高级参数" : "高级参数"}
      </button>

      {advanced && (
        <div className="advanced-grid">
          <Range label="背景尺度" min={40} max={140} step={5} value={parameters.background_sigma_px} onChange={(value) => patch({ background_sigma_px: value })} />
          <Range label="保护上限" min={0.25} max={0.55} step={0.01} value={parameters.target_protect_mask_fraction_max} onChange={(value) => patch({ target_protect_mask_fraction_max: value })} />
          <Range label="Hough 阈值" min={25} max={65} step={1} value={parameters.hough_param2} onChange={(value) => patch({ hough_param2: value })} />
          <NumberBox label="最小半径" value={parameters.min_radius_px} onChange={(value) => patch({ min_radius_px: value })} />
          <NumberBox label="最大半径" value={parameters.max_radius_px} onChange={(value) => patch({ max_radius_px: value })} />
          <Range label="边缘覆盖" min={0.25} max={0.75} step={0.01} value={parameters.min_edge_coverage_fraction} onChange={(value) => patch({ min_edge_coverage_fraction: value })} />
          <Range label="边噪比" min={1.0} max={2.5} step={0.05} value={parameters.ring_gradient_noise_ratio_min} onChange={(value) => patch({ ring_gradient_noise_ratio_min: value })} />
          <Range label="可靠射线" min={0.35} max={0.75} step={0.01} value={parameters.min_reliable_ray_fraction} onChange={(value) => patch({ min_reliable_ray_fraction: value })} />
          <Range label="径向外扩" min={1.0} max={1.8} step={0.01} value={parameters.radial_search_max_scale} onChange={(value) => patch({ radial_search_max_scale: value })} />
          <NumberBox label="最小面积" value={parameters.min_area_px2} onChange={(value) => patch({ min_area_px2: value })} />
          <OptionalNumberBox label="最大面积" value={parameters.max_area_px2} placeholder="不限" onChange={(value) => patch({ max_area_px2: value })} />
          <NumberBox label="方形最小面积" value={parameters.square_candidate_min_area_px2} onChange={(value) => patch({ square_candidate_min_area_px2: value })} />
          <NumberBox label="方形最大面积" value={parameters.square_candidate_max_area_px2} onChange={(value) => patch({ square_candidate_max_area_px2: value })} />
          <Range label="方形边界" min={1.0} max={1.8} step={0.01} value={parameters.square_min_boundary_gradient_noise_ratio} onChange={(value) => patch({ square_min_boundary_gradient_noise_ratio: value })} />
          <Range label="方形支撑" min={0.25} max={0.65} step={0.01} value={parameters.square_refine_min_boundary_support} onChange={(value) => patch({ square_refine_min_boundary_support: value })} />
          <Range label="粘连置信" min={0.4} max={0.8} step={0.01} value={parameters.adhesion_min_split_confidence} onChange={(value) => patch({ adhesion_min_split_confidence: value })} />
        </div>
      )}
    </section>
  );
}

function ModeControl({ label, value, onChange }: { label: string; value: StrategyMode; onChange: (value: StrategyMode) => void }) {
  return (
    <div className="control-group">
      <label>{label}</label>
      <div className="segmented compact">
        <button className={value === "auto" ? "selected" : ""} onClick={() => onChange("auto")}>自动</button>
        <button className={value === "true" ? "selected" : ""} onClick={() => onChange("true")}>开启</button>
        <button className={value === "false" ? "selected" : ""} onClick={() => onChange("false")}>关闭</button>
      </div>
    </div>
  );
}

function Range({ label, min, max, step, value, onChange }: { label: string; min: number; max: number; step: number; value: number; onChange: (value: number) => void }) {
  return (
    <label className="range-row">
      <span>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <em>{value}</em>
    </label>
  );
}

function NumberBox({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

function OptionalNumberBox({ label, value, placeholder, onChange }: { label: string; value: string; placeholder: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
