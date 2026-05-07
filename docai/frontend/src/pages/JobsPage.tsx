import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button, Card } from "@/components/ui";
import { JobsTable } from "@/components/jobs/JobsTable";
import { listJobs, JobOut } from "@/lib/docaiApi";

export default function JobsPage() {
  const { id: projectId } = useParams();
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    loadJobs();
  }, [projectId]);

  async function loadJobs() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listJobs(projectId);
      setJobs(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            Extraction Jobs
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            Manage training and production extraction runs for this project.
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
          {error && <Card className="p-4 text-red-400">{error}</Card>}
          {loading ? (
            <Card className="p-8 text-center text-slate-400">Loading jobs...</Card>
          ) : (
            <JobsTable jobs={jobs} projectId={projectId} />
          )}
        </div>
      </div>
    </div>
  );
}
