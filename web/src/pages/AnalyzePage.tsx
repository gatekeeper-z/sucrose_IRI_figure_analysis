import { Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import ImageUploader from "../components/ImageUploader";
import JobProgress from "../components/JobProgress";
import ParameterPanel, { presetParameterDefaults } from "../components/ParameterPanel";
import type { Job, Parameters, Preset } from "../types";

interface Props {
  onOpenJob: (jobId: string) => void;
  files: File[];
  onFiles: (files: File[]) => void;
  preset: Preset;
  onPreset: (preset: Preset) => void;
  activePreset: Preset | null;
  onActivePreset: (preset: Preset | null) => void;
  parameters: Parameters;
  onParameters: (parameters: Parameters) => void;
  job: Job | null;
  onJob: (job: Job | null) => void;
}

export default function AnalyzePage({
  onOpenJob,
  files,
  onFiles,
  preset,
  onPreset,
  activePreset,
  onActivePreset,
  parameters,
  onParameters,
  job,
  onJob
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!job || ["done", "done_with_errors", "error"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      const fresh = await api.getJob(job.job_id);
      onJob(fresh);
      if (["done", "done_with_errors"].includes(fresh.status)) {
        window.clearInterval(timer);
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  async function start() {
    if (!files.length) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createJob(files, preset, parameters);
      const fresh = await api.getJob(created.job_id);
      onJob(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function changePreset(nextPreset: Preset) {
    onPreset(nextPreset);
    onActivePreset(nextPreset);
    onParameters({ ...presetParameterDefaults[nextPreset] });
  }

  function changeParameters(nextParameters: Parameters) {
    onActivePreset(null);
    onParameters(nextParameters);
  }

  return (
    <div className="page-grid analyze-layout">
      <div className="page-head">
        <div>
          <h1>分析</h1>
          <p>批量处理显微图并生成完整中间产物</p>
        </div>
        {job && ["done", "done_with_errors"].includes(job.status) && (
          <button className="primary-button" onClick={() => onOpenJob(job.job_id)}>查看结果</button>
        )}
      </div>

      <ImageUploader files={files} onFiles={onFiles} />
      <ParameterPanel
        activePreset={activePreset}
        parameters={parameters}
        onPreset={changePreset}
        onParameters={changeParameters}
      />

      <section className="panel action-panel">
        <button className="primary-button large" disabled={!files.length || busy} onClick={start}>
          <Play size={18} /> 开始分析
        </button>
        <button className="secondary-button" onClick={() => { onFiles([]); onJob(null); setError(""); }}>
          <RotateCcw size={17} /> 重置
        </button>
        {error && <div className="error-box">{error}</div>}
      </section>

      <JobProgress job={job} />
    </div>
  );
}
