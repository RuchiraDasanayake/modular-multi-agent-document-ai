import Link from "next/link";

const docaiFrontendUrl = process.env.NEXT_PUBLIC_DOCAI_FRONTEND_URL?.trim() || "";
const docaiApiBaseUrl = process.env.NEXT_PUBLIC_DOCAI_API_BASE_URL?.trim() || "";

export default function DocAIWorkspaceMountPage() {
  const hasFrontendUrl = docaiFrontendUrl.length > 0;
  const hasApiBaseUrl = docaiApiBaseUrl.length > 0;
  const healthUrl = hasApiBaseUrl ? `${docaiApiBaseUrl.replace(/\/+$/, "")}/health` : "";

  return (
    <div className="max-w-4xl 3xl:max-w-5xl mx-auto">
      <div className="glass-panel rounded-2xl p-8 space-y-7">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">DocAI Workspace Launcher</h1>
          <p className="text-sm text-slate-500 dark:text-gray-400">
            This route stays inside the protected legacy dashboard shell and opens the standalone DocAI workspace.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-gray-800 bg-slate-50/70 dark:bg-gray-900/50 p-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-gray-500">
            Frontend URL (`NEXT_PUBLIC_DOCAI_FRONTEND_URL`)
          </p>
          <p className="text-xs text-slate-600 dark:text-gray-300 break-all">
            {hasFrontendUrl ? docaiFrontendUrl : "Not configured"}
          </p>
          {hasFrontendUrl ? (
            <div className="space-y-3">
              <a
                href={docaiFrontendUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center px-5 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold transition-colors"
              >
                Open DocAI Workspace
              </a>
              <p className="text-xs text-slate-500 dark:text-gray-400">
                Workflow: schema → job → upload → run → review → export
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <p className="text-sm text-amber-700 dark:text-amber-300">
                Set `NEXT_PUBLIC_DOCAI_FRONTEND_URL` to enable the launcher CTA.
              </p>
              <p className="text-xs text-slate-500 dark:text-gray-400">
                Dev example: `http://localhost:3000`
              </p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-gray-800 bg-slate-50/70 dark:bg-gray-900/50 p-4 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-gray-500">
            Optional Backend Health (`NEXT_PUBLIC_DOCAI_API_BASE_URL`)
          </p>
          <p className="text-xs text-slate-600 dark:text-gray-300 break-all">
            {hasApiBaseUrl ? docaiApiBaseUrl : "Not configured"}
          </p>
          {hasApiBaseUrl ? (
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={healthUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center px-4 py-2 rounded-lg border border-slate-300 dark:border-gray-700 text-sm font-medium text-slate-700 dark:text-gray-300 hover:bg-slate-100 dark:hover:bg-gray-800 transition-colors"
              >
                Open /health Endpoint
              </a>
            </div>
          ) : (
            <p className="text-sm text-slate-500 dark:text-gray-400">
              Set `NEXT_PUBLIC_DOCAI_API_BASE_URL` to enable the backend health link.
            </p>
          )}
        </div>

        <div className="text-xs text-slate-500 dark:text-gray-500">
          Legacy AHMN/admin/public/auth routes are unchanged.
          <span className="mx-1">|</span>
          <Link href="/dashboard/idpo/jobs" className="underline hover:text-slate-700 dark:hover:text-gray-300">
            Open legacy IDPO jobs
          </Link>
        </div>
      </div>
    </div>
  );
}
