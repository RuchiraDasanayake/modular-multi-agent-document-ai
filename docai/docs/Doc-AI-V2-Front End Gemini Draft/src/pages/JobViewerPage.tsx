import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, Play } from "lucide-react";
import { Button } from "@/components/ui";
import JobOverviewTab from "@/components/job-viewer/JobOverviewTab";
import DocumentQueueTab from "@/components/job-viewer/DocumentQueueTab";
import ExtractedDataTab from "@/components/job-viewer/ExtractedDataTab";
import ReviewTab from "@/components/job-viewer/ReviewTab";
import ArtifactsTab from "@/components/job-viewer/ArtifactsTab";
import LearningSummaryTab from "@/components/job-viewer/LearningSummaryTab";
import { mockJobContext } from "@/lib/mockData";

type Tab = "overview" | "queue" | "extracted_data" | "review" | "artifacts" | "learning";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "queue", label: "Document Queue" },
  { id: "extracted_data", label: "Extracted Data" },
  { id: "review", label: "Review" },
  { id: "artifacts", label: "Artifacts" },
  { id: "learning", label: "Learning Summary" },
];

export default function JobViewerPage() {
  const { project_id, job_id } = useParams();
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-bold text-slate-500 mb-1 uppercase tracking-wider">
            <Link to={`/projects/${project_id}/jobs`} className="hover:text-cyan-400 transition-colors">
              Jobs
            </Link>
            <span>/</span>
            <span>{job_id}</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            {mockJobContext.jobName}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <Download className="mr-1.5 h-4 w-4" />
            Export Results
          </Button>
          <Button variant="outline" disabled title="Mock only — no real extraction available">
            <Play className="mr-1.5 h-4 w-4" />
            Start Run (Mock)
          </Button>
        </div>
      </header>

      <div className="px-6 border-b border-white/10 glass-panel pt-2">
        <nav className="flex gap-6 overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? "border-cyan-400 text-cyan-400 shadow-[0_4px_15px_rgba(6,182,212,0.5)]"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-5xl mx-auto space-y-6">
          {activeTab === "overview" && <JobOverviewTab projectId={project_id} jobId={job_id} />}
          {activeTab === "queue" && <DocumentQueueTab projectId={project_id} jobId={job_id} />}
          {activeTab === "extracted_data" && <ExtractedDataTab />}
          {activeTab === "review" && <ReviewTab projectId={project_id} jobId={job_id} />}
          {activeTab === "artifacts" && <ArtifactsTab />}
          {activeTab === "learning" && <LearningSummaryTab />}
        </div>
      </div>
    </div>
  );
}
