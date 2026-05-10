import { Download, Eye } from "lucide-react";
import { downloadImageUrl } from "../api";
import type { JobListItem } from "../types";

interface Props {
  jobs: JobListItem[];
  onOpenJob: (jobId: string) => void;
}

export default function HistoryGrid({ jobs, onOpenJob }: Props) {
  const rows = jobs
    .flatMap((job) =>
      job.images.map((image) => ({
        job,
        image,
        time: image.processed_at || job.finished_at || job.created_at
      }))
    )
    .sort((a, b) => (b.time || "").localeCompare(a.time || ""));

  if (!rows.length) {
    return <div className="empty-state">暂无历史结果</div>;
  }

  return (
    <div className="history-grid">
      {rows.map(({ job, image, time }) => (
        <article className="history-card" key={`${job.job_id}-${image.image_id}`}>
          <div className="history-thumb">
            {image.thumbnail_url ? <img src={image.thumbnail_url} alt={image.original_name} /> : <div />}
          </div>
          <div className="history-body">
            <strong>{image.original_name}</strong>
            <span>{formatTime(time)}</span>
          </div>
          <div className="history-actions">
            <button className="icon-button" onClick={() => onOpenJob(job.job_id)}>
              <Eye size={16} />
            </button>
            <a className="icon-button" href={downloadImageUrl(job.job_id, image.image_id)}>
              <Download size={16} />
            </a>
          </div>
        </article>
      ))}
    </div>
  );
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}
