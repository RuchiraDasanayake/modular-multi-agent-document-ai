import { Link, useParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui";
import { mockProjects } from "@/lib/mockData";
import { ProjectContextCard } from "@/components/project-dashboard/ProjectContextCard";
import { ProjectRunSummaryCards } from "@/components/project-dashboard/ProjectRunSummaryCards";
import { RecentRunsTable } from "@/components/project-dashboard/RecentRunsTable";
import { ReviewQueueCard } from "@/components/project-dashboard/ReviewQueueCard";
import { StrategyPerformancePanel } from "@/components/project-dashboard/StrategyPerformancePanel";
import { NextActionsPanel } from "@/components/project-dashboard/NextActionsPanel";

export default function ProjectDashboardPage() {
  const { id } = useParams();
  const project = mockProjects.find((p) => p.id === id) ?? mockProjects[0];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            {project.name}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">{project.description}</p>
        </div>
        <Button variant="primary" asChild>
          <Link to={`/projects/${id}/jobs/new`}>
            <Plus className="mr-1.5 h-4 w-4" />
            Create Job
          </Link>
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-7xl mx-auto space-y-5 animate-fade-in" style={{ animationDelay: "0.05s" }}>

          <ProjectRunSummaryCards />

          <div className="grid grid-cols-5 gap-5">
            <div className="col-span-3">
              <ProjectContextCard projectId={id} />
            </div>
            <div className="col-span-2">
              <ReviewQueueCard projectId={id} />
            </div>
          </div>

          <RecentRunsTable projectId={id} />

          <div className="grid grid-cols-5 gap-5">
            <div className="col-span-3">
              <StrategyPerformancePanel />
            </div>
            <div className="col-span-2">
              <NextActionsPanel projectId={id} />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
