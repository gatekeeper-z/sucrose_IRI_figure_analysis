import { Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api, downloadImageUrl, downloadJobUrl } from "../api";
import ImagePreviewModal from "../components/ImagePreviewModal";
import MetricPanel from "../components/MetricPanel";
import ResultGallery from "../components/ResultGallery";
import type { ImageDetail, Job } from "../types";

interface Props {
  jobId: string;
  onOpenJob: (jobId: string) => void;
}

export default function ResultPage({ jobId }: Props) {
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ImageDetail | null>(null);
  const [preview, setPreview] = useState<{ src: string; title: string; downloadUrl: string } | null>(null);

  async function loadJob() {
    const next = await api.getJob(jobId);
    setJob(next);
    const firstDone = next.images.find((image) => image.status === "done") || next.images[0];
    setSelected((current) => current || firstDone?.image_id || null);
  }

  useEffect(() => {
    loadJob();
  }, [jobId]);

  useEffect(() => {
    if (!selected) return;
    api.getImage(jobId, selected).then(setDetail);
  }, [jobId, selected]);

  if (!job) return <div className="empty-state">加载中</div>;
  const image = detail?.image || job.images.find((item) => item.image_id === selected) || job.images[0];

  return (
    <div className="result-layout">
      <div className="page-head">
        <div>
          <h1>结果</h1>
          <p>{job.created_at}</p>
        </div>
        <div className="head-actions">
          <button className="secondary-button" onClick={loadJob}>
            <RefreshCw size={17} /> 刷新
          </button>
          <a className="primary-button" href={downloadJobUrl(job.job_id)}>
            <Download size={17} /> 下载整批
          </a>
        </div>
      </div>

      <aside className="image-rail panel">
        {job.images.map((item) => (
          <button
            key={item.image_id}
            className={item.image_id === selected ? "selected" : ""}
            onClick={() => setSelected(item.image_id)}
          >
            {item.thumbnail_url ? <img src={item.thumbnail_url} alt={item.original_name} /> : <div />}
            <span>{item.original_name}</span>
          </button>
        ))}
      </aside>

      <section className="result-main">
        {image && (
          <>
            <div className="result-title">
              <div>
                <h2>{image.original_name}</h2>
                <span>{image.status}</span>
              </div>
              <a className="secondary-button" href={downloadImageUrl(job.job_id, image.image_id)}>
                <Download size={17} /> 下载单图
              </a>
            </div>
            <MetricPanel image={image} />
            {detail && (
              <>
                <ResultGallery
                  jobId={job.job_id}
                  imageId={image.image_id}
                  files={detail.files}
                  onPreview={(src, title, downloadUrl) => setPreview({ src, title, downloadUrl })}
                />
                {detail.qc_report && (
                  <section className="panel qc-panel">
                    <div className="panel-title">
                      <span>QC 报告</span>
                    </div>
                    <pre>{detail.qc_report}</pre>
                  </section>
                )}
              </>
            )}
          </>
        )}
      </section>

      <ImagePreviewModal
        src={preview?.src || null}
        title={preview?.title || ""}
        downloadUrl={preview?.downloadUrl}
        onClose={() => setPreview(null)}
      />
    </div>
  );
}
