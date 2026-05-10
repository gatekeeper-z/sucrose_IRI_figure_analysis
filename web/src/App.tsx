import { Activity, Clock3, FlaskConical, Info } from "lucide-react";
import { useEffect, useState } from "react";
import InfoModal from "./components/InfoModal";
import { defaultParameters } from "./components/ParameterPanel";
import AnalyzePage from "./pages/AnalyzePage";
import HistoryPage from "./pages/HistoryPage";
import ResultPage from "./pages/ResultPage";
import type { Job, Page, Parameters, Preset } from "./types";

export default function App() {
  const [page, setPage] = useState<Page>("analyze");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [analyzeFiles, setAnalyzeFiles] = useState<File[]>([]);
  const [analyzePreset, setAnalyzePreset] = useState<Preset>("default");
  const [analyzeActivePreset, setAnalyzeActivePreset] = useState<Preset | null>("default");
  const [analyzeParameters, setAnalyzeParameters] = useState<Parameters>({ ...defaultParameters });
  const [analyzeJob, setAnalyzeJob] = useState<Job | null>(null);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash.startsWith("job/")) {
      setCurrentJobId(hash.slice(4));
      setPage("result");
    } else if (hash === "history") {
      setPage("history");
    }
  }, []);

  function openResult(jobId: string) {
    setCurrentJobId(jobId);
    setPage("result");
    window.location.hash = `job/${jobId}`;
  }

  function go(next: Page) {
    setPage(next);
    window.location.hash = next === "history" ? "history" : "";
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <FlaskConical size={22} />
          </div>
          <div>
            <strong>IRI Analyzer</strong>
            <span>Contour Area</span>
          </div>
        </div>
        <nav>
          <button className={page === "analyze" ? "active" : ""} onClick={() => go("analyze")}>
            <Activity size={18} /> 分析
          </button>
          <button className={page === "history" ? "active" : ""} onClick={() => go("history")}>
            <Clock3 size={18} /> 历史
          </button>
        </nav>
        <button
          className="info-button"
          aria-label="使用说明"
          title="使用说明"
          onClick={() => setInfoOpen(true)}
        >
          <Info size={20} />
        </button>
      </aside>
      <main className="main">
        {page === "analyze" && (
          <AnalyzePage
            onOpenJob={openResult}
            files={analyzeFiles}
            onFiles={setAnalyzeFiles}
            preset={analyzePreset}
            onPreset={setAnalyzePreset}
            activePreset={analyzeActivePreset}
            onActivePreset={setAnalyzeActivePreset}
            parameters={analyzeParameters}
            onParameters={setAnalyzeParameters}
            job={analyzeJob}
            onJob={setAnalyzeJob}
          />
        )}
        {page === "history" && <HistoryPage onOpenJob={openResult} />}
        {page === "result" && currentJobId && <ResultPage jobId={currentJobId} onOpenJob={openResult} />}
      </main>
      <InfoModal open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
}
