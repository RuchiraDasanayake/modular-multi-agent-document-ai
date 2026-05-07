import { Folder, Home, LayoutTemplate, Briefcase, BarChart2 } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ReactNode } from "react";

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const location = useLocation();
  
  // Extract project ID if we are inside a project
  const projectIdMatch = location.pathname.match(/^\/projects\/([^\/]+)/);
  const projectId = projectIdMatch ? projectIdMatch[1] : null;

  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-100 font-sans overflow-hidden relative">
      {/* Background blobs & grid */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none mix-blend-overlay" style={{backgroundImage: "url('data:image/svg+xml,%3Csvg width=\\'60\\' height=\\'60\\' viewBox=\\'0 0 60 60\\' xmlns=\\'http://www.w3.org/2000/svg\\'%3E%3Cg fill=\\'none\\' fill-rule=\\'evenodd\\'%3E%3Cg fill=\\'%23ffffff\\' fill-opacity=\\'1\\'%3E%3Cpath d=\\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E')"}}></div>
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-brand-600/20 blur-[120px] pointer-events-none animate-pulse-slow"></div>
      <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-violet-600/20 blur-[120px] pointer-events-none animate-pulse-slow" style={{animationDelay: '1s'}}></div>
      
      {/* Sidebar Navigation */}
      <aside className="w-60 border-r border-white/10 glass-panel z-10 flex flex-col shrink-0">
        <div className="p-6 flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-brand-400 to-cyan-600 flex items-center justify-center text-white font-bold text-sm shadow-[0_0_15px_rgba(6,182,212,0.5)] animate-float" style={{animationDuration: '4s'}}>
            D
          </div>
          <span className="font-semibold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">DocAI</span>
        </div>
        
        <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
          <Link
            to="/"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all",
              location.pathname === "/" ? "bg-white/10 text-white font-semibold shadow-sm border border-white/10" : "text-slate-400 hover:bg-white/5 hover:text-white font-medium"
            )}
          >
            <Folder className="w-5 h-5" />
            <span className="text-sm">Projects</span>
          </Link>
          {projectId && (
            <div className="pt-4 mt-4 border-t border-white/10">
              <div className="px-3 mb-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Current Project
              </div>
              <div className="space-y-1">
                <Link
                  to={`/projects/${projectId}`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all",
                    location.pathname === `/projects/${projectId}` ? "bg-white/10 text-white font-semibold shadow-sm border border-white/10" : "text-slate-400 hover:bg-white/5 hover:text-white font-medium"
                  )}
                >
                  <Home className="w-5 h-5" />
                  <span className="text-sm">Dashboard</span>
                </Link>
                <Link
                  to={`/projects/${projectId}/schema`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all",
                    location.pathname.includes('/schema') ? "bg-white/10 text-white font-semibold shadow-sm border border-white/10" : "text-slate-400 hover:bg-white/5 hover:text-white font-medium"
                  )}
                >
                  <LayoutTemplate className="w-5 h-5" />
                  <span className="text-sm">Extraction Schema</span>
                </Link>
                <Link
                  to={`/projects/${projectId}/jobs`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all",
                    location.pathname.includes('/jobs') ? "bg-white/10 text-white font-semibold shadow-sm border border-white/10" : "text-slate-400 hover:bg-white/5 hover:text-white font-medium"
                  )}
                >
                  <Briefcase className="w-5 h-5" />
                  <span className="text-sm">Jobs</span>
                </Link>
                <Link
                  to={`/projects/${projectId}/metrics`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-all",
                    location.pathname.includes('/metrics') ? "bg-white/10 text-white font-semibold shadow-sm border border-white/10" : "text-slate-400 hover:bg-white/5 hover:text-white font-medium"
                  )}
                >
                  <BarChart2 className="w-5 h-5" />
                  <span className="text-sm">Metrics</span>
                </Link>
              </div>
            </div>
          )}
        </nav>
        
        <div className="p-4 border-t border-white/10 mt-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-800 border border-white/10"></div>
            <div className="overflow-hidden">
              <p className="text-xs font-semibold text-slate-200 truncate">Local Operator</p>
              <p className="text-[10px] text-slate-500 truncate">DocAI Workspace</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10">
        {children}
      </main>
    </div>
  );
}
