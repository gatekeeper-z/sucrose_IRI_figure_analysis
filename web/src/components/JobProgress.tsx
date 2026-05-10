import { Loader2 } from "lucide-react";
import type { Job } from "../types";

export default function JobProgress({ job }: { job: Job | null }) {
  if (!job) return null;
  const total = Math.max(job.total_images || 0, 1);
  const percent = Math.round(((job.processed_images || 0) / total) * 100);
  return (
    <section className="panel progress-panel">
      <div className="progress-header">
        <div>
          <strong>{job.status}</strong>
          <span>{job.current_image || "等待任务"}</span>
        </div>
        {job.status === "running" || job.status === "queued" ? <Loader2 className="spin" size={20} /> : null}
      </div>
      <div className="progress-track">
        <div style={{ width: `${percent}%` }} />
      </div>
      <div className="progress-foot">
        <span>{job.processed_images}/{job.total_images}</span>
        <span>{percent}%</span>
      </div>
    </section>
  );
}
