import { Link } from "react-router-dom";
import { Plus, Folder } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import { mockProjects } from "@/lib/mockData";

export default function ProjectsPage() {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">Projects</h1>
        <Button variant="primary">
          <Plus className="mr-1.5 h-4 w-4" />
          Create Project
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-5xl mx-auto space-y-6 animate-fade-in" style={{animationDelay: '0.1s'}}>
          <Card className="overflow-hidden border-white/5 relative glass-card">
            <CardContent className="p-0">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 backdrop-blur border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-5 py-3 font-semibold">Name</th>
                <th className="px-5 py-3 font-semibold">Description</th>
                <th className="px-5 py-3 font-semibold text-center">Jobs</th>
                <th className="px-5 py-3 font-semibold text-right">Last Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/30">
              {mockProjects.map((project) => (
                <tr key={project.id} className="hover:bg-slate-800/50 transition-colors group">
                  <td className="px-5 py-3">
                    <Link to={`/projects/${project.id}`} className="flex items-center gap-3 font-medium text-slate-200 group-hover:text-cyan-400">
                      <Folder className="h-4 w-4 text-cyan-500/50" />
                      {project.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-slate-400">{project.description}</td>
                  <td className="px-5 py-3 text-slate-300 text-center">{project.jobCount}</td>
                  <td className="px-5 py-3 text-slate-500 text-right text-xs font-mono">{project.updatedAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
        </div>
      </div>
    </div>
  );
}
