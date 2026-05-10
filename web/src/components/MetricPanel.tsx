import type { ImageSummary } from "../types";

export default function MetricPanel({ image }: { image: ImageSummary }) {
  const summary = image.summary || {};
  const cards: Array<[string, unknown]> = [
    ["实例", summary.n_accepted_instances],
    ["总面积", summary.accepted_total_actual_area_px2],
    ["中位面积", summary.accepted_median_area_px2],
    ["QC", summary.n_qc_warning],
    ["方形", summary.n_accepted_square_instances],
    ["粘连", summary.n_accepted_cluster_split_instances]
  ];
  return (
    <div className="metric-grid">
      {cards.map(([label, value]) => (
        <div className="metric-card" key={label as string}>
          <span>{label}</span>
          <strong>{formatValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(1);
  return String(value);
}
