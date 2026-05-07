import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Folder, AlertCircle } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import { listProjects, createProject, ProjectOut } from "@/lib/docaiApi";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateProject() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createProject(newName);
      setNewName("");
      setShowCreate(false);
      await loadProjects();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">Projects</h1>
        <Button variant="primary" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Create Project
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-5xl mx-auto space-y-6 animate-fade-in" style={{animationDelay: '0.1s'}}>
          {showCreate && (
            <Card className="border-white/5 glass-card p-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Project name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="flex-1 px-3 py-2 bg-slate-900/50 border border-white/10 rounded text-white placeholder-slate-500"
                  disabled={creating}
                />
                <Button variant="primary" onClick={handleCreateProject} disabled={creating || !newName.trim()}>
                  {creating ? "Creating..." : "Create"}
                </Button>
                <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </Card>
          )}

          {error && (
            <Card className="border-red-500/30 bg-red-500/10 p-4">
              <div className="flex items-center gap-3 text-red-400">
                <AlertCircle className="h-5 w-5" />
                <span>{error}</span>
              </div>
            </Card>
          )}

          {loading ? (
            <Card className="p-8 text-center text-slate-400">Loading projects...</Card>
          ) : projects.length === 0 ? (
            <Card className="p-8 text-center text-slate-400">No projects yet. Create one to get started.</Card>
          ) : (
            <Card className="overflow-hidden border-white/5 relative glass-card">
              <CardContent className="p-0">
                <table className="w-full text-sm text-left border-collapse">
                  <thead className="bg-slate-900/80 backdrop-blur border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Name</th>
                      <th className="px-5 py-3 font-semibold">Description</th>
                      <th className="px-5 py-3 font-semibold text-right">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 bg-slate-800/30">
                    {projects.map((project) => (
                      <tr key={project.project_id} className="hover:bg-slate-800/50 transition-colors group">
                        <td className="px-5 py-3">
                          <Link to={`/projects/${project.project_id}`} className="flex items-center gap-3 font-medium text-slate-200 group-hover:text-cyan-400">
                            <Folder className="h-4 w-4 text-cyan-500/50" />
                            {project.name}
                          </Link>
                        </td>
                        <td className="px-5 py-3 text-slate-400">{project.description || "-"}</td>
                        <td className="px-5 py-3 text-slate-500 text-right text-xs font-mono">{new Date(project.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
