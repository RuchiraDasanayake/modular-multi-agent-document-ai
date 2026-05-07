import { Link } from "react-router-dom";
import { Info, Settings, Target } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import type { ProjectOut } from "@/lib/docaiApi";

interface ProjectContextCardProps {
  projectId: string | undefined;
  project: ProjectOut | null;
}

export function ProjectContextCard({ projectId, project }: ProjectContextCardProps) {
  const createdAt = project?.created_at
    ? new Date(project.created_at).toLocaleString()
    : "Unknown";

  return (
    <Card className="glass-card border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Target className="h-4 w-4 opacity-70" />
            Project Context
          </h3>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs border-white/10 text-slate-400 hover:text-cyan-400 hover:border-cyan-500/30"
            asChild
          >
            <Link to={`/projects/${projectId}/schema`}>
              <Settings className="h-3 w-3 mr-1" />
              Configure Schema
            </Link>
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Project ID</p>
            <p className="text-xs font-mono text-slate-300">{project?.project_id ?? projectId ?? "Unknown"}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Status</p>
            <p className="text-xs font-medium text-slate-200">{project?.status ?? "Unknown"}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Created</p>
            <p className="text-xs font-medium text-slate-200">{createdAt}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Description</p>
            <p className="text-xs font-medium text-slate-200">{project?.description || "No description set."}</p>
          </div>
        </div>

        <div className="pt-3 border-t border-white/5 flex items-start gap-2">
          <Info className="h-3.5 w-3.5 text-cyan-400/50 mt-0.5 shrink-0" />
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">
              Project Context Configuration
            </p>
            <p className="text-xs font-medium text-slate-200">Project context is not configured yet.</p>
            <p className="text-[10px] font-mono text-slate-500 mt-0.5">
              No domain/schema/model metadata is exposed by API yet.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
