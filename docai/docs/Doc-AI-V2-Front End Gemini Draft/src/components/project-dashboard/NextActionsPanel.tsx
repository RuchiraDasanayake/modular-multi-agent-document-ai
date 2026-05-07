import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Monitor, Plus, ListChecks, ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui";

interface Action {
  icon: ReactNode;
  label: string;
  description: string;
  to: string;
  colorClass: string;
  borderClass: string;
}

interface NextActionsPanelProps {
  projectId: string | undefined;
}

export function NextActionsPanel({ projectId }: NextActionsPanelProps) {
  const actions: Action[] = [
    {
      icon: <AlertTriangle className="h-4 w-4" />,
      label: "Review Documents",
      description: "Open the review console for documents needing attention.",
      to: `/projects/${projectId}/jobs/job-1/document/doc-2`,
      colorClass: "text-amber-400",
      borderClass: "border-amber-500/20 hover:border-amber-500/40 hover:bg-amber-500/5",
    },
    {
      icon: <Monitor className="h-4 w-4" />,
      label: "Open Latest Run Console",
      description: "View artifacts, extracted data, and run details.",
      to: `/projects/${projectId}/jobs/job-1`,
      colorClass: "text-cyan-400",
      borderClass: "border-cyan-500/20 hover:border-cyan-500/40 hover:bg-cyan-500/5",
    },
    {
      icon: <Plus className="h-4 w-4" />,
      label: "Create Training Run",
      description: "Stage a new batch for extraction and review.",
      to: `/projects/${projectId}/jobs/new`,
      colorClass: "text-violet-400",
      borderClass: "border-violet-500/20 hover:border-violet-500/40 hover:bg-violet-500/5",
    },
    {
      icon: <ListChecks className="h-4 w-4" />,
      label: "View All Jobs",
      description: "See the full jobs list for this project.",
      to: `/projects/${projectId}/jobs`,
      colorClass: "text-slate-400",
      borderClass: "border-white/10 hover:border-white/20 hover:bg-slate-800/40",
    },
  ];

  return (
    <Card className="border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-4">
          Next Actions
        </h3>
        <div className="space-y-2">
          {actions.map((action) => (
            <Link
              key={action.label}
              to={action.to}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors ${action.borderClass}`}
            >
              <span className={action.colorClass}>{action.icon}</span>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-semibold ${action.colorClass}`}>{action.label}</p>
                <p className="text-[10px] text-slate-500 mt-0.5">{action.description}</p>
              </div>
              <ChevronRight className="h-3.5 w-3.5 text-slate-600 shrink-0" />
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
