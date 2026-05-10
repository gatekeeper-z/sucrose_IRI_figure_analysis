import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import HistoryGrid from "../components/HistoryGrid";
import type { JobListItem } from "../types";

interface Props {
  onOpenJob: (jobId: string) => void;
}

export default function HistoryPage({ onOpenJob }: Props) {
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const response = await api.listJobs();
    setJobs(response.jobs);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="page-grid">
      <div className="page-head">
        <div>
          <h1>历史</h1>
          <p>按处理时间排序</p>
        </div>
        <button className="secondary-button" onClick={load}>
          <RefreshCw size={17} /> 刷新
        </button>
      </div>
      {loading ? <div className="empty-state">加载中</div> : <HistoryGrid jobs={jobs} onOpenJob={onOpenJob} />}
    </div>
  );
}
