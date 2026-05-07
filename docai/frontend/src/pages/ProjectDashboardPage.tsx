import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button, Card } from "@/components/ui";
import { ProjectContextCard } from "@/components/project-dashboard/ProjectContextCard";
import { ProjectRunSummaryCards } from "@/components/project-dashboard/ProjectRunSummaryCards";
import { RecentRunsTable } from "@/components/project-dashboard/RecentRunsTable";
import { NextActionsPanel } from "@/components/project-dashboard/NextActionsPanel";
import {
  getAdaptiveRoutingAdvice,
  getProject,
  listJobs,
  listRuns,
  type AdaptiveRoutingAdviceOut,
  type JobOut,
  type ProjectOut,
} from "@/lib/docaiApi";

export default function ProjectDashboardPage() {
  const { id: projectId } = useParams();
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [completedRuns, setCompletedRuns] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adaptiveAdvice, setAdaptiveAdvice] = useState<AdaptiveRoutingAdviceOut | null>(null);
  const [adaptiveLoading, setAdaptiveLoading] = useState(false);
  const [adaptiveError, setAdaptiveError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    void loadDashboard(projectId);
    void loadAdaptiveAdvice(projectId);
  }, [projectId]);

  async function loadDashboard(id: string) {
    setLoading(true);
    setError(null);
    try {
      const [projectData, jobsData] = await Promise.all([
        getProject(id),
        listJobs(id),
      ]);
      setProject(projectData);
      setJobs(jobsData);

      const runsByJob = await Promise.all(
        jobsData.map(async (job) => {
          try {
            return await listRuns(job.job_id);
          } catch {
            return [];
          }
        }),
      );
      const completedCount = runsByJob.flat().filter((run) => run.status === "completed").length;
      setCompletedRuns(completedCount);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project dashboard");
      setProject(null);
      setJobs([]);
      setCompletedRuns(0);
    } finally {
      setLoading(false);
    }
  }

  async function loadAdaptiveAdvice(id: string) {
    setAdaptiveLoading(true);
    setAdaptiveError(null);
    try {
      const advice = await getAdaptiveRoutingAdvice(id);
      setAdaptiveAdvice(advice);
    } catch (e) {
      setAdaptiveError(e instanceof Error ? e.message : "Could not load routing advice.");
      setAdaptiveAdvice(null);
    } finally {
      setAdaptiveLoading(false);
    }
  }

  const queuedJobs = jobs.filter((job) => job.status === "queued").length;
  const visibleRecommendations =
    adaptiveAdvice?.status === "insufficient_evidence"
      ? adaptiveAdvice.recommendations.filter((item) => item.type === "insufficient_evidence")
      : adaptiveAdvice?.recommendations ?? [];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            {project?.name ?? "Project Dashboard"}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {project
              ? `project_id: ${project.project_id} - status: ${project.status}`
              : "Load real project/job data for this project."}
          </p>
        </div>
        <Button variant="primary" asChild>
          <Link to={`/projects/${projectId}/jobs/new`}>
            <Plus className="mr-1.5 h-4 w-4" />
            Create Job
          </Link>
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-7xl mx-auto space-y-5 animate-fade-in" style={{ animationDelay: "0.05s" }}>
          {error && <Card className="p-4 text-red-300">{error}</Card>}
          {loading && <Card className="p-4 text-slate-400">Loading project dashboard...</Card>}

          {!loading && !error && (
            <>
              <ProjectRunSummaryCards
                totalJobs={jobs.length}
                queuedJobs={queuedJobs}
                completedRuns={completedRuns}
              />

              <div className="grid grid-cols-5 gap-5">
                <div className="col-span-3">
                  <ProjectContextCard projectId={projectId} project={project} />
                </div>
                <div className="col-span-2">
                  <NextActionsPanel projectId={projectId} />
                </div>
              </div>

              <RecentRunsTable projectId={projectId} jobs={jobs} />

              <Card className="border-white/5">
                <div className="p-5 space-y-3">
                  <div>
                    <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">Adaptive Routing</h2>
                    <p className="text-xs text-slate-500">
                      Review evidence. Read-only.
                    </p>
                  </div>

                  {adaptiveLoading && (
                    <p className="text-sm text-slate-400">Loading routing advice...</p>
                  )}

                  {!adaptiveLoading && adaptiveError && (
                    <p className="text-sm text-red-300">{adaptiveError}</p>
                  )}

                  {!adaptiveLoading && !adaptiveError && adaptiveAdvice && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                        <div><span className="text-slate-500">evidence_count:</span> <span className="text-slate-200 font-mono">{adaptiveAdvice.evidence_count}</span></div>
                        <div><span className="text-slate-500">minimum_required:</span> <span className="text-slate-200 font-mono">{adaptiveAdvice.minimum_required}</span></div>
                        <div><span className="text-slate-500">status:</span> <span className="text-slate-200">{adaptiveAdvice.status}</span></div>
                        <div><span className="text-slate-500">generated_by:</span> <span className="text-slate-200 font-mono">{adaptiveAdvice.generated_by}</span></div>
                        <div><span className="text-slate-500">Read-only:</span> <span className="text-slate-200">{adaptiveAdvice.is_read_only ? "Yes" : "No"}</span></div>
                        <div><span className="text-slate-500">No automatic action taken:</span> <span className="text-slate-200">{adaptiveAdvice.automatic_action_taken ? "No" : "Yes"}</span></div>
                      </div>

                      {adaptiveAdvice.status === "insufficient_evidence" && (
                        <p className="text-xs text-slate-400">
                          Not enough reviewed evidence yet.
                        </p>
                      )}

                      {visibleRecommendations.length === 0 ? (
                        <p className="text-xs text-slate-400">No recommendation available.</p>
                      ) : (
                        <div className="space-y-2">
                          {visibleRecommendations.map((rec) => (
                            <div key={rec.recommendation_id} className="border border-white/10 rounded p-3 text-xs space-y-1">
                              <div className="flex flex-wrap gap-2 items-center">
                                <span className="text-slate-300 font-semibold">Recommendation</span>
                                <span className={`px-1.5 py-0.5 rounded border ${
                                  rec.severity === "warning"
                                    ? "border-amber-500/40 text-amber-300 bg-amber-500/10"
                                    : "border-cyan-500/40 text-cyan-300 bg-cyan-500/10"
                                }`}>
                                  {rec.severity}
                                </span>
                                <span className="text-slate-400">{rec.type}</span>
                              </div>
                              <p className="text-slate-300">{rec.message}</p>
                              <p className="text-slate-400">suggested_action: {rec.suggested_action}</p>
                              <p className="text-slate-500 font-mono">
                                evidence_count={rec.evidence_count}
                                {rec.field_name ? ` | field_name=${rec.field_name}` : ""}
                                {rec.schema_id ? ` | schema_id=${rec.schema_id}` : ""}
                                {rec.correction_rate !== null && rec.correction_rate !== undefined ? ` | correction_rate=${rec.correction_rate}` : ""}
                                {" | "}
                                automatic_action_taken={rec.automatic_action_taken ? "true" : "false"}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
