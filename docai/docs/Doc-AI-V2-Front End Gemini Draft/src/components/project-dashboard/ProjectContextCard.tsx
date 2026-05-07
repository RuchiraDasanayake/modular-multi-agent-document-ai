import { Link } from "react-router-dom";
import { Target, Database, Settings } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";
import { mockProjects, mockJobContext, mockProjectSchemaByProjectId } from "@/lib/mockData";

interface ProjectContextCardProps {
  projectId: string | undefined;
}

export function ProjectContextCard({ projectId }: ProjectContextCardProps) {
  const project = mockProjects.find((p) => p.id === projectId) ?? mockProjects[0];
  const schema =
    mockProjectSchemaByProjectId[project.id] ?? mockProjectSchemaByProjectId["proj-1"];

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
            <Link to={`/projects/${project.id}/schema`}>
              <Settings className="h-3 w-3 mr-1" />
              Configure Schema
            </Link>
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Domain</p>
            <p className="text-xs font-medium text-slate-200">{project.domain}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Document Type</p>
            <p className="text-xs font-medium text-slate-200">{project.documentType}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Extraction Goal</p>
            <p className="text-xs font-medium text-slate-200">{project.extractionGoal}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Precision / Speed</p>
            <p className="text-xs font-medium text-slate-200">{project.precisionSpeedPreference}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">Local Model</p>
            <p className="text-xs font-mono text-cyan-400">{mockJobContext.selectedModel}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">OCR Preference</p>
            <p className="text-xs font-medium text-slate-200">{mockJobContext.selectedOcrPreference}</p>
          </div>
        </div>

        <div className="pt-3 border-t border-white/5 flex items-start gap-2">
          <Database className="h-3.5 w-3.5 text-cyan-400/50 mt-0.5 shrink-0" />
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">
              Extraction Schema
            </p>
            <p className="text-xs font-medium text-slate-200">
              {schema.name}{" "}
              <span className="text-slate-500 font-mono">{schema.version}</span>
            </p>
            <p className="text-[10px] font-mono text-slate-500 mt-0.5">
              {schema.fieldCount} fields · {schema.tableCount} tables
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
